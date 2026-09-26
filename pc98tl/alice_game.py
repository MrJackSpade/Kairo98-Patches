"""Shared extract/patch driver for Alice Soft System 2/3 games.

A game folder holds game.json:
  {"title": ..., "key": "<index key>", "game_dir": "BEE", "version": 3,
   "encoding": "halfkana", "config": {...optional Sys2Game overrides}}
and thin extract.py / patch.py wrappers that call run_extract / run_patch.
"""
import json
import os
import re

from .disk import DiskImage
from .alice_sys2_tl import Sys2Game, sha256, set_kana_table
from . import alice3_font

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""


def kana_table(adv):
    """ADV.COM's half-width kana -> displayed full-width table (64 words)."""
    at = adv.find(bytes.fromhex("4081428175817681418145"))
    if at < 0:
        return None
    t = adv[at:at + 128]
    return [bytes([t[i + 1], t[i]]).decode("cp932", "replace") for i in range(0, 128, 2)]


def _game(here, img):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = img.volumes[0]
    conf = dict(cfg.get("config", {}))
    conf.setdefault("encoding", cfg["encoding"])
    return cfg, vol, Sys2Game(vol, cfg["game_dir"], version=cfg["version"], config=conf)


def run_extract(here, src):
    out = os.path.join(here, "strings.json")
    img = DiskImage(src)
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    table = kana_table(img.volumes[0].read(cfg["game_dir"] + "/ADV.COM"))
    if table:
        set_kana_table(table)
    cfg, vol, game = _game(here, img)
    doc = game.extract(cfg["title"], sha256(src))
    if os.path.exists(out):  # keep translations and hand-tuned fields
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


def run_patch(here, src, dst, mode="en"):
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    cfg, vol, game = _game(here, img)
    report = game.patch(doc, mode=mode)
    adv_path = cfg["game_dir"] + "/ADV.COM"
    if cfg["encoding"] == "halfkana":
        vol.write(adv_path, alice3_font.build(vol.read(adv_path)))
    vol.create(cfg["game_dir"] + "/MTL_NOTE.TXT",
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    img.save(dst)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
    for line in report:
        print("  " + line)
