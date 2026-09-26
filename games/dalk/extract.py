"""Extract Dalk's script text to strings.json.

    python extract.py "Dalk (v1.08) (uncensored).hdi"
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from pc98tl.disk import DiskImage  # noqa: E402
from pc98tl.alice_sys2_tl import Sys2Game, sha256, set_kana_table  # noqa: E402
import advhack  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = "DALK"


def kana_table(adv):
    """ADV.COM CS:1A29: 64 words, half-width byte A0-DF -> full-width SJIS."""
    t = adv[0x1A29 - 0x100:0x1A29 - 0x100 + 128]
    return [bytes([t[i + 1], t[i]]).decode("cp932", "replace") for i in range(0, 128, 2)]


def main():
    src = sys.argv[1]
    out = os.path.join(HERE, "strings.json")
    vol = DiskImage(src).volumes[0]
    set_kana_table(kana_table(vol.read(GAME_DIR + "/ADV.COM")))
    game = Sys2Game(vol, GAME_DIR)
    doc = game.extract("Dalk", sha256(src))
    for n, (addr, size, jp) in enumerate(advhack.exe_strings(vol.read(GAME_DIR + "/ADV.COM")), 1):
        doc["strings"].append({"id": "e%05d" % n, "kind": "exe", "jp": jp, "en": "",
                               "refs": ["adv:%04x" % addr], "max_bytes": size - 1})
    if os.path.exists(out):  # keep existing translations and hand-tuned fields
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in doc["strings"]:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                for k in ("en", "max_cells", "note"):
                    if k in prev:
                        e[k] = prev[k]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    kinds = {}
    for e in doc["strings"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print("wrote %s: %d strings %s" % (out, len(doc["strings"]), kinds))


if __name__ == "__main__":
    main()
