"""Verify that every games/<title>/ script rebuilds byte-for-byte unmodified.

    python tools/verify_roundtrip.py [folder ...]
"""
import glob
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from pc98tl.disk import DiskImage  # noqa: E402
from pc98tl.alice_game import _games  # noqa: E402


def main():
    names = sys.argv[1:] or [os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(ROOT, "games", "*", "game.json"))]
    bad = 0
    for name in sorted(names):
        here = os.path.join(ROOT, "games", name)
        cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
        img = DiskImage(os.path.join(os.environ.get("PC98_ROOT", r"C:\PC98"), cfg["image"]))
        _cfg, _vol, games = _games(here, img)
        ok, pages = True, 0
        for g in games:
            new = []
            for i in range(len(g.adisk.links)):
                page = g.pages.get(i)
                if page is None:
                    new.append(g.adisk.page_data[i])
                    continue
                ok &= not page.validate()
                new.append(page.assemble())
                pages += 1
            rebuilt = g.adisk.build(new)
            ok &= all(rebuilt[n] == g.adisk.files[n] for n in g.scope)
        print("%-20s %4d pages  %s" % (name, pages, "byte-identical" if ok else "MISMATCH"))
        bad += not ok
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
