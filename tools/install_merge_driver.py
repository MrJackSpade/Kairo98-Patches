"""Register tools/merge_strings.py as this clone's git merge driver for strings.json.

.gitattributes routes games/*/strings.json to the `strings-jp` driver, but git keeps driver
commands in each clone's own config, so run this once per clone: python tools/install_merge_driver.py
Without it, git falls back to its line-based merge for those files.
"""

import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
script = repo / "tools" / "merge_strings.py"
command = f'"{sys.executable}" "{script}" %O %A %B %P'


def git_config(key, value):
    subprocess.run(["git", "-C", str(repo), "config", key, value], check=True)


git_config("merge.strings-jp.name", "strings.json three-way merge matching entries by Japanese text")
git_config("merge.strings-jp.driver", command)
print(f"merge.strings-jp.driver = {command}")
