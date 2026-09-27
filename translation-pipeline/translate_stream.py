"""One continuous, constrained llama.cpp JSON translation stream."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llama_dll import DirectLlama
from translate import SYSTEM, TOKEN, JSON_STRING_GRAMMAR, compact, en_spans, write_bytes, write_json

ROOT = Path(__file__).resolve().parent
# A token may contain the field's closing quote plus fixed JSON that follows.
# Permit that tail, then verify its bytes against the fixed source span.
STRING_END = JSON_STRING_GRAMMAR


def fit_gpu_settings(model_path, context_tokens):
    """Use llama.cpp's own fit command for this model and context."""
    tool = ROOT / "runtime" / "llama" / "llama-fit-params.exe"
    command = [str(tool), "-m", str(model_path), "-c", str(context_tokens),
               "-fitc", str(context_tokens), "-ctk", "q8_0", "-ctv", "q8_0",
               "-nkvo", "-fa", "on", "-b", "2048", "-ub", "512"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("llama-fit-params failed: " + result.stderr[-2000:])
    args = shlex.split(result.stdout)
    try:
        fitted_context = int(args[args.index("-c") + 1])
        layers = int(args[args.index("-ngl") + 1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError(f"unrecognized llama-fit-params output: {result.stdout!r}") from exc
    if fitted_context != context_tokens:
        raise RuntimeError(f"GPU fit reduced context to {fitted_context}; whole-file stream needs "
                           f"the requested {context_tokens}")
    overrides = []
    if "-ot" in args:
        raw_overrides = args[args.index("-ot") + 1]
        for item in raw_overrides.split(","):
            pattern, buffer_type = item.rsplit("=", 1)
            if buffer_type != "CPU":
                raise RuntimeError(f"unsupported fitted tensor buffer: {buffer_type}")
            overrides.append(pattern)
    if len(args) != 4 + (2 if overrides else 0):
        raise RuntimeError(f"unhandled llama-fit-params arguments: {result.stdout!r}")
    print(f"llama.cpp GPU fit: {layers} layers, {len(overrides)} CPU tensor overrides "
          f"at {fitted_context} context", flush=True)
    return layers, overrides


def payload(doc):
    return {"game": doc.get("game", ""), "strings": [
        {"id": row["id"], "jp": row["jp"], "en": row["en"]}
        for row in doc["strings"]]}


def splice_candidate(raw, doc, english):
    source = raw.decode("utf-8-sig")
    spans = en_spans(source)
    if len(spans) != len(doc["strings"]):
        raise ValueError("source en positions differ from parsed strings")
    parts, cursor = [], 0
    for row, (start, end) in zip(doc["strings"], spans):
        parts.extend((source[cursor:start],
                      json.dumps(english.get(row["id"], row["en"]), ensure_ascii=False)))
        cursor = end
    parts.append(source[cursor:])
    result = "".join(parts)
    candidate = json.loads(result)
    for old, new in zip(doc["strings"], candidate["strings"]):
        if {k: v for k, v in old.items() if k != "en"} != {
                k: v for k, v in new.items() if k != "en"}:
            raise ValueError(f"non-English source data changed at {old['id']}")
    return (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + result.encode("utf-8")


def translate_stream(model, doc, raw, checkpoint, model_tag, max_field_tokens,
                     output, limit=0):
    source_hash = hashlib.sha256(raw).hexdigest()
    saved = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if saved and (saved.get("source_sha256") != source_hash or
                  saved.get("model_tag") != model_tag):
        raise ValueError("checkpoint belongs to another source or model")
    english = saved.get("english", {})
    entries = doc["strings"]
    ids = [row["id"] for row in entries]
    if len(ids) != len(set(ids)) or set(english) - set(ids):
        raise ValueError("duplicate or unknown source IDs")
    for row in entries:
        if not all(isinstance(row.get(key), str) for key in ("id", "jp", "en")):
            raise ValueError("every string needs id, jp, and en text")
    untranslated = [row for row in entries if not row["en"]]
    for row in untranslated:
        if row["id"] in english:
            value = english[row["id"]]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"invalid saved English at {row['id']}")
    source_payload = compact(payload(doc))
    spans = en_spans(source_payload)
    if len(spans) != len(entries):
        raise ValueError("compact en positions differ from parsed strings")
    instruction = ("You will be given untranslated JSON. Return the same JSON with the English "
                   "en fields filled in. The harness supplies every byte outside en and generates "
                   "only one en JSON string at a time. Preserve character names, voice, Japanese "
                   "meaning, line breaks, and runtime tokens. Existing English is a style reference. "
                   "Return only JSON.\nUntranslated JSON:\n" + source_payload)
    prefix = model.chat_prompt(SYSTEM, instruction)
    # Reserve room for the output before allocating a long-lived context. This
    # estimate is a lower bound; each field is checked against the real limit.
    fixed_tokens = len(model.tokenize(prefix, add_special=True)) + len(model.tokenize(source_payload))
    pending = [row for row in untranslated if row["id"] not in english]
    reserve = sum(max(12, len(model.tokenize(row["jp"])) // 2) for row in pending)
    print(f"{len(entries)} rows; {len(pending)} pending; fixed prompt/output ~{fixed_tokens} "
          f"tokens; minimum English reserve ~{reserve}; context {model.context_tokens}", flush=True)
    if fixed_tokens + reserve + 64 >= model.context_tokens:
        raise ValueError("whole-file stream will exceed context; increase --context-tokens")
    model.reset()
    model.prefill(prefix + source_payload[:spans[0][0] + 1], initial=True)
    rendered = source_payload[:spans[0][0] + 1]
    generated_count = 0
    for index, (row, (start, end)) in enumerate(zip(entries, spans)):
        key = row["id"]
        if row["en"] or key in english:
            value = json.dumps(row["en"] or english[key], ensure_ascii=False)
            model.prefill(value[1:])
            rendered += value[1:]
            tail = b""
        else:
            value, tail = model.sample_json_string(STRING_END, max_field_tokens)
            translated = json.loads(value)
            if not isinstance(translated, str) or not translated.strip():
                raise ValueError(f"empty English at {key}")
            if sorted(TOKEN.findall(translated)) != sorted(TOKEN.findall(row["jp"])):
                raise ValueError(f"runtime token mismatch at {key}: {translated!r}")
            english[key] = translated
            rendered += value[1:]
            generated_count += 1
            write_json(checkpoint, {"source_sha256": source_hash,
                                    "model_tag": model_tag, "english": english})
            print(f"{generated_count}/{len(pending)} generated: {key}; "
                  f"context {model.tokens_used}/{model.context_tokens}", flush=True)
        next_start = spans[index + 1][0] + 1 if index + 1 < len(spans) else len(source_payload)
        suffix = source_payload[end:next_start]
        if not suffix.encode("utf-8").startswith(tail):
            raise ValueError(f"generated token crossed fixed JSON at {key}: {tail!r}")
        rendered += suffix
        remaining = suffix.encode("utf-8")[len(tail):]
        if remaining:
            model.prefill(remaining.decode("utf-8"))
        if limit and generated_count >= limit:
            break
    if limit and generated_count >= limit:
        print("stopped at requested field limit; checkpoint is resumable", flush=True)
        return
    finished = json.loads(rendered)
    if len(finished["strings"]) != len(entries):
        raise ValueError("forced output lost strings")
    for source, result in zip(entries, finished["strings"]):
        if result["id"] != source["id"] or result["jp"] != source["jp"]:
            raise ValueError(f"forced JSON changed source text at {source['id']}")
    write_bytes(output, splice_candidate(raw, doc, english))
    print(f"candidate: {output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--model", type=Path, default=Path(r"F:\Models") /
                        "DeepSeek-V4-Flash-0731-UD-Q3_K_M-00001-of-00004.gguf")
    parser.add_argument("--model-tag", default="deepseek-v4-flash-q3km")
    parser.add_argument("--context-tokens", type=int, default=262144)
    parser.add_argument("--gpu-layers", type=int, help="override llama.cpp GPU fit")
    parser.add_argument("--max-field-tokens", type=int, default=3000)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=0, help="generate at most N fields")
    args = parser.parse_args()
    game_metadata = args.input.parent / "game.json"
    age_screening_path = ROOT.parent / "research" / "age_screening.json"
    if game_metadata.exists() and age_screening_path.exists():
        game_key = json.loads(game_metadata.read_text(encoding="utf-8"))["key"]
        screening = json.loads(age_screening_path.read_text(encoding="utf-8")).get(game_key)
        if screening and screening.get("translation_disposition") == "Wont do":
            parser.error(f"{game_key}: Wont do ({screening['classification']}); "
                         f"see {age_screening_path}")
    raw = args.input.read_bytes()
    doc = json.loads(raw.decode("utf-8-sig"))
    work = args.work or ROOT / "work" / args.input.parent.name / args.model_tag
    work.mkdir(parents=True, exist_ok=True)
    checkpoint = work / "stream-checkpoint.json"
    output = args.output or work / "strings.translated.json"
    gpu_layers, cpu_patterns = ((args.gpu_layers, []) if args.gpu_layers is not None
                                else fit_gpu_settings(args.model, args.context_tokens))
    model = DirectLlama(args.model, args.context_tokens, kv_on_gpu=False,
                        gpu_layers=gpu_layers, cpu_tensor_patterns=cpu_patterns)
    try:
        translate_stream(model, doc, raw, checkpoint, args.model_tag,
                         args.max_field_tokens, output, args.limit)
    finally:
        model.close()


if __name__ == "__main__":
    main()
