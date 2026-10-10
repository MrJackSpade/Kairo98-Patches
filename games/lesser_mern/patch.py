"""Patch a copy of the image:  python patch.py IN OUT [--pseudo]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from pc98tl.lmern_tl import run_patch  # noqa: E402

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_patch(os.path.dirname(os.path.abspath(__file__)), args[0], args[1],
              "pseudo" if "--pseudo" in sys.argv else "en")
