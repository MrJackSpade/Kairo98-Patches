"""Split strings.json into MTL batches and merge translations back.

    python tools/mtl.py split games/dalk/strings.json out_dir [--size 200] [--all]
        writes out_dir/batch_0001.json ... as {"id": "jp", ...}
        (only untranslated strings unless --all)

    python tools/mtl.py merge games/dalk/strings.json translated_dir_or_file ...
        reads {"id": "english", ...} files and fills the matching "en" fields

    python tools/mtl.py check games/dalk/strings.json
        reports progress and strings whose {X1}-style tokens don't match
"""
import glob
import json
import os
import re
import sys

TOKEN = re.compile(r"\{[A-Z]\d+\}")


def load(p):
    return json.load(open(p, encoding="utf-8"))


def save(doc, p):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


def split(path, out, size=200, everything=False):
    doc = load(path)
    todo = [e for e in doc["strings"] if everything or not e["en"]]
    os.makedirs(out, exist_ok=True)
    for n in range(0, len(todo), size):
        batch = {e["id"]: e["jp"] for e in todo[n:n + size]}
        save(batch, os.path.join(out, "batch_%04d.json" % (n // size + 1)))
    print("%d strings -> %d batches in %s" % (len(todo), (len(todo) + size - 1) // size, out))


def merge(path, sources):
    doc = load(path)
    by_id = {e["id"]: e for e in doc["strings"]}
    files = []
    for s in sources:
        files += sorted(glob.glob(os.path.join(s, "*.json"))) if os.path.isdir(s) else [s]
    n = unknown = 0
    for f in files:
        for k, v in load(f).items():
            if k in by_id and isinstance(v, str):
                by_id[k]["en"] = v
                n += 1
            else:
                unknown += 1
    save(doc, path)
    print("merged %d translations (%d unknown ids)" % (n, unknown))
    check(path)


def check(path):
    doc = load(path)
    done = [e for e in doc["strings"] if e["en"]]
    print("%d / %d translated" % (len(done), len(doc["strings"])))
    bad = [e for e in done if sorted(TOKEN.findall(e["jp"])) != sorted(TOKEN.findall(e["en"]))]
    for e in bad[:50]:
        print("  token mismatch %s: %r -> %r" % (e["id"], e["jp"], e["en"]))
    if len(bad) > 50:
        print("  ... %d more" % (len(bad) - 50))


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "split":
        size = int(args[args.index("--size") + 1]) if "--size" in args else 200
        pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--size")]
        split(pos[0], pos[1], size, "--all" in args)
    elif cmd == "merge":
        merge(args[0], args[1:])
    elif cmd == "check":
        check(args[0])
