"""Scaffold games/<folder>/ for an Alice Soft System 3 title from the index.

    python tools/new_alice_game.py <folder> "<index key>" [image substring]

Picks the title's HDI (optionally the one whose name contains the substring),
finds the directory holding ADISK.DAT, writes game.json, extract.py, patch.py
and a notes.md stub.
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from pc98tl.disk import DiskImage  # noqa: E402

COLLECTION = r"C:\PC98"
EXTRACT = '''"""Extract the script to strings.json:  python extract.py IMAGE.hdi"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from pc98tl.alice_game import run_extract  # noqa: E402

if __name__ == "__main__":
    run_extract(os.path.dirname(os.path.abspath(__file__)), sys.argv[1])
'''
PATCH = '''"""Patch a copy of the image:  python patch.py IN.hdi OUT.hdi [--pseudo]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from pc98tl.alice_game import run_patch  # noqa: E402

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_patch(os.path.dirname(os.path.abspath(__file__)), args[0], args[1],
              "pseudo" if "--pseudo" in sys.argv else "en")
'''


def main():
    folder, key = sys.argv[1], sys.argv[2]
    want = sys.argv[3] if len(sys.argv) > 3 else ""
    titles = json.load(open(os.path.join(ROOT, "index", "index.json"), encoding="utf-8"))["titles"]
    t = next(x for x in titles if x["key"] == key)
    hdis = [i for i in t["images"] if i.get("path", "").lower().endswith(".hdi") and want in i["image"]]
    img = hdis[0]
    vol = DiskImage(os.path.join(COLLECTION, img["path"])).volumes[0]
    adisk = next(p for p, _e in vol.walk() if p.upper() == "ADISK.DAT" or p.upper().endswith("/ADISK.DAT"))
    game_dir = adisk.rsplit("/", 1)[0] if "/" in adisk else ""
    here = os.path.join(ROOT, "games", folder)
    os.makedirs(here, exist_ok=True)
    cfg = {"title": t["title"], "key": key, "image": img["path"],
           "game_dir": game_dir, "version": 3, "encoding": "halfkana",
           "config": {"menu_fit_jp": True}}
    json.dump(cfg, open(os.path.join(here, "game.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for name, body in (("extract.py", EXTRACT), ("patch.py", PATCH)):
        open(os.path.join(here, name), "w", encoding="utf-8").write(body)
    # every game folder carries the identical standard PATCH.BAT
    bat = open(os.path.join(ROOT, "tools", "PATCH.BAT.template"), encoding="utf-8").read()
    open(os.path.join(here, "PATCH.BAT"), "w", encoding="utf-8", newline=chr(13) + chr(10)).write(bat)
    print(os.path.join(COLLECTION, img["path"]))


if __name__ == "__main__":
    main()
