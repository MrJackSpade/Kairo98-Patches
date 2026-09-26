"""Extract/patch driver for Illusion (tmexec engine) games.

game.json:
  {"title", "key", "image", "game_dir": "KAN", "engine": "GAME.EXE",
   "encoding": "illusion"}
Every file in game_dir holding "#nnnnn ... $" records is a message file
(pc98tl/illusion.py).  A string's ref is "<file>:<number>".
"""
import json
import os

from .disk import DiskImage
from .alice_sys2_tl import sha256
from . import illusion

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""


def _cells(text):
    return max((sum(1 if ord(c) < 0x80 else 2 for c in line) + 1) // 2 for line in text.split("\n"))


def _message_files(vol, game_dir):
    out = []
    ents = vol.listdir(vol.find(game_dir)["cluster"]) if game_dir else vol.listdir(0)
    for e in sorted(ents, key=lambda e: e["name"]):
        if e["is_dir"] or e["size"] > 300000:
            continue
        path = (game_dir + "/" if game_dir else "") + e["name"]
        data = vol.read(path)
        if illusion.is_message_file(data):
            out.append((e["name"], path, data))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for name, _path, data in _message_files(vol, cfg["game_dir"]):
        for num, text, _s, _e in illusion.parse(data):
            jp = text.decode("cp932", "replace").replace("\r\n", "\n")
            ref = "%s:%05d" % (name, num)
            if jp in merged:
                merged[jp]["refs"].append(ref)
                continue
            merged[jp] = {"kind": "msg", "jp": jp, "en": "", "refs": [ref], "max_cells": _cells(jp)}
            order.append(jp)
    strings = []
    for i, jp in enumerate(order, 1):
        e = merged[jp]
        strings.append({"id": "m%05d" % i, **e})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):  # keep translations and hand-tuned fields
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                for k in ("en", "max_cells", "note"):
                    if k in prev:
                        e[k] = prev[k]
    doc = {"game": cfg["title"], "source_image_sha256": sha256(src), "strings": strings}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))
