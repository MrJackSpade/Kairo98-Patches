"""Check that every games/<title>/ folder meets the standard layout.

    python tools/check_games.py

Required in each game folder:
  game.json      title, key, image (relative to the collection root), ...
  extract.py     image -> strings.json
  patch.py       contract: patch.py IN OUT [--pseudo]
  strings.json   the extracted script
  notes.md       must carry the machine-translation notice
  PATCH.BAT      byte-identical to tools/PATCH.BAT.template
Exits non-zero if anything is missing.
"""
import glob
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REQUIRED = ["game.json", "extract.py", "patch.py", "strings.json", "notes.md", "PATCH.BAT"]


def main():
    template = open(os.path.join(ROOT, "tools", "PATCH.BAT.template"), "rb").read()
    problems = 0
    for here in sorted(glob.glob(os.path.join(ROOT, "games", "*", ""))):
        name = os.path.basename(os.path.dirname(here))
        issues = [f for f in REQUIRED if not os.path.exists(os.path.join(here, f))]
        bat = os.path.join(here, "PATCH.BAT")
        if os.path.exists(bat) and open(bat, "rb").read() != template:
            issues.append("PATCH.BAT differs from tools/PATCH.BAT.template")
        cfg = os.path.join(here, "game.json")
        if os.path.exists(cfg):
            missing = [k for k in ("title", "key", "image") if k not in json.load(open(cfg, encoding="utf-8"))]
            if missing:
                issues.append("game.json lacks " + ", ".join(missing))
        notes = os.path.join(here, "notes.md")
        if os.path.exists(notes) and "machine translation" not in open(notes, encoding="utf-8").read().lower():
            issues.append("notes.md lacks the machine-translation notice")
        print("%-20s %s" % (name, "ok" if not issues else "; ".join(issues)))
        problems += len(issues)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
