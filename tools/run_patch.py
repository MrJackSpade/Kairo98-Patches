"""Standard patch runner behind every games/<title>/PATCH.BAT.

    python tools/run_patch.py <game folder> [source image]

* Source image: the argument if given (e.g. an image dropped on PATCH.BAT),
  otherwise the collection copy named in game.json ("image", relative to
  C:\\PC98 or the PC98_ROOT environment variable).
* Output: <game folder>/output/<title> (English MTL).hdi, plus a copy of the
  game's notes and MTL notice next to it.
* Runs the game's own patch.py (contract: patch.py IN OUT [--pseudo]).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg):
    print("\nERROR: " + msg)
    sys.exit(1)


def main():
    here = os.path.abspath(sys.argv[1])
    cfg_path = os.path.join(here, "game.json")
    if not os.path.exists(cfg_path):
        fail("no game.json in %s" % here)
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    title = cfg["title"]
    root = os.environ.get("PC98_ROOT", r"C:\PC98")
    src = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else os.path.join(root, cfg["image"])
    print("%s - English patch (machine translation)" % title)
    print("source: %s" % src)
    if not os.path.exists(src):
        fail("source image not found. Drop the game's %s onto PATCH.BAT, or set PC98_ROOT."
             % os.path.basename(cfg["image"]))
    try:
        import keystone  # noqa: F401
    except ImportError:
        fail("missing Python package: run  pip install -r requirements.txt  in the repository folder")
    strings = os.path.join(here, "strings.json")
    if os.path.exists(strings):
        want = json.load(open(strings, encoding="utf-8")).get("source_image_sha256")
        if want and sha256(src) != want:
            print("warning: this image is not the exact dump the script was extracted from; "
                  "the patch may not match")
    out_dir = os.path.join(here, "output")
    os.makedirs(out_dir, exist_ok=True)
    safe = "".join(c for c in title if c not in '<>:"/\\|?*')
    dst = os.path.join(out_dir, "%s (English MTL).hdi" % safe)
    rc = subprocess.call([sys.executable, os.path.join(here, "patch.py"), src, dst], cwd=here)
    if rc != 0:
        fail("patching failed (see messages above)")
    notes = os.path.join(here, "notes.md")
    if os.path.exists(notes):
        shutil.copy(notes, os.path.join(out_dir, "notes.md"))
    print("\nDone: %s" % dst)


if __name__ == "__main__":
    main()
