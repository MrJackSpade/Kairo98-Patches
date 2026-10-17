"""English for Psy-O-Blade (pc98tl/psyo.py): strings.json in, a patched program disk out.

Strings (kind msg, id m): one message, as the screen shows it.  {XX} and {XX:args} are the game's
commands (window, clear, wait for a key, colour, choices, pauses...) and must be kept in the
English, in order; \\n is a new line.  Any length: lines are broken between words at the window's
right edge, and the window scrolls as in the game.  The same Japanese is one string everywhere (the
game finds its English by the Japanese).

A build with English writes the table onto the program disk's empty tracks, a start-up stub into
the program's zeros, and the hooks into the program; the data disk is copied unchanged next to
the patched disk, with MTL_NOTE.TXT (the disks have no file system).
"""
import json
import os
import re
import unicodedata

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from . import psyo as S
from .text import pseudo

NOTE = ("a message: any length (lines broken between words at the window's edge, the window scrolls); "
        "keep every {..} command, in order; \\n a new line")


def _at(cfg):
    return int(cfg["program_at"], 16)


def found(disk, cfg):
    """[(ref, Japanese bytes as stored)]."""
    at = _at(cfg)
    prog = S.program(disk, at)
    out = []
    # the program's own text is its start-up overlay's (from AEC0h to the filler after it); what
    # follows the filler on the disk is never used
    end = S.start_overlay_end(prog)
    for s, e in S.messages(prog[:end], 0):
        if s >= S.OVERLAY_AT:
            out.append(("P:%04x" % s, prog[s:e]))
    for off, (n, dst) in sorted(S.blocks(disk, prog).items()):
        body = disk[off:off + n]
        for s, e in S.messages(body, dst):
            out.append(("%05x:%04x" % (off, dst + s), body[s:e]))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    disk = open(src, "rb").read()
    table = S.kana_table(S.program(disk, _at(cfg)))
    merged, order = {}, []
    for ref, b in found(disk, cfg):
        if b in merged:
            merged[b]["refs"].append(ref)
            continue
        merged[b] = {"kind": "msg", "jp": S.show(b, table), "en": "", "refs": [ref], "max_cells": 2000, "note": NOTE}
        order.append(b)
    strings = []
    for n, b in enumerate(order, 1):
        strings.append({"id": "m%05d" % n, **merged[b]})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):
        old = {}
        for x in json.load(open(out, encoding="utf-8"))["strings"]:
            old.setdefault(x["jp"], x)
        for ent in strings:
            prev = old.get(ent["jp"])
            if prev:
                ent["en"] = prev.get("en", "")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _cols(t):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


def _pseudo(e):
    parts = re.split(r"(\{[^}]*\}|\n)", e["jp"])
    out = []
    for p in parts:
        if not p:
            continue
        if p == "\n" or p.startswith("{"):
            out.append(p)
        else:
            out.append(pseudo(e["id"], _cols(p)))
    return "".join(out)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    disk = open(src, "rb").read()
    by_ref = {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            by_ref[r] = (e, text)
    warn, entries, seen = [], [], set()
    for ref, b in found(disk, cfg):
        e, text = by_ref.get(ref, (None, ""))
        if not text or b in seen:
            continue
        seen.add(b)
        if S.tokens(text) != S.tokens(e["jp"]):
            warn.append("%s: the commands differ from the Japanese's" % e["id"])
        try:
            en = S.encode(text)
        except ValueError as x:
            raise SystemExit("%s: %s" % (e["id"], x))
        entries.append((b, en))
    if entries:
        disk, tracks = S.build(disk, _at(cfg), entries)
        print("English table: %d messages, %d tracks" % (len(entries), tracks))
    open(dst, "wb").write(disk)
    stem = os.path.splitext(dst)[0]
    for name in cfg.get("disks", []):
        data = open(os.path.join(os.path.dirname(os.path.abspath(src)), name), "rb").read()
        with open("%s - %s" % (stem, name), "wb") as f:
            f.write(data)
    # the disks have no file system: the notice goes next to them
    with open(os.path.join(os.path.dirname(os.path.abspath(dst)), "MTL_NOTE.TXT"), "w", encoding="ascii",
              newline="\r\n") as f:
        f.write(MTL_NOTE.format(title=cfg["title"]))
    for w in warn:
        print("warning:", w)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
