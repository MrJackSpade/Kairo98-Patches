"""Extract the script to strings.json:  python extract.py IMAGE"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from pc98tl.mapl_tl import run_extract  # noqa: E402

if __name__ == "__main__":
    run_extract(os.path.dirname(os.path.abspath(__file__)), sys.argv[1])
