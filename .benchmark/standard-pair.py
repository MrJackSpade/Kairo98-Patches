"""Compare the translation pipeline's fitted placement with a VRAM-matched expert cache."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
BENCH = Path(__file__).resolve().parent
MODEL = Path(r"F:\Models\DeepSeek-V4-Flash-0731-UD-Q3_K_M-00001-of-00004.gguf")
PROMPT = BENCH / "english-prompt.txt"
FIT = json.loads((BENCH / "standard-placement.json").read_text(encoding="utf-8"))
COMMON = ["-m", str(MODEL), "-f", str(PROMPT), "-n", "256", "-st",
          "-c", str(FIT["context"]), "-ctk", "q8_0", "-ctv", "q8_0",
          "-nkvo", "-fa", "on", "-b", "2048", "-ub", "512",
          "-t", "4", "-tb", "4", "--temp", "0", "-s", "42",
          "--ignore-eos", "--simple-io", "--no-display-prompt"]


def run(label, exe, placement):
    log = BENCH / f"standard-{label}.log"
    command = [str(exe), *COMMON, "-ngl", str(FIT["gpu_layers"]), *placement]
    print(f"Starting {label}: {log}", flush=True)
    started = time.monotonic()
    with log.open("wb") as output:
        result = subprocess.run(command, cwd=ROOT, stdout=output,
                                stderr=subprocess.STDOUT)
    data = log.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"\[ Prompt: ([\d.]+) t/s \| Generation: ([\d.]+) t/s \]", data)
    print(f"{label}: exit={result.returncode}, elapsed={time.monotonic() - started:.0f}s, "
          f"timing={match.group(0) if match else 'missing'}", flush=True)
    if result.returncode or not match:
        raise RuntimeError(f"{label} did not finish a valid benchmark; inspect {log}")


parser = argparse.ArgumentParser()
parser.add_argument("--only", choices=("current", "cache", "both"), default="both")
args = parser.parse_args()
baseline = ROOT / "translation-pipeline/runtime/llama/llama-cli.exe"
cache = BENCH / "llama-expert-pool/build-ninja/bin/llama-cli.exe"
overrides = ",".join(f"{pattern}=CPU" for pattern in FIT["cpu_patterns"])
if args.only in ("current", "both"):
    run("current", baseline, ["-ot", overrides])
if args.only in ("cache", "both"):
    run("cache", cache, ["-cmoe", "-mec", "28"])
