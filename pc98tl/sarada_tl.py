"""English for Salad no Kuni no Tomato-hime (pc98tl/sarada.py): strings.json in, a patched disk out.

Strings:
* m (message): a string the game prints (its messages, prompts and answers).  Any length: the English
  is broken between words at the screen's 80 columns (the last left free) from wherever the cursor
  is, \n a new line; the game shows 4 rows of text, and a key is waited for before a line not yet
  read would scroll out of them (max_cells: a windowful, 3 lines).
* n (name): an object's name in a chapter's inventory list (the names after it on the same line, a
  space between them).
The parser's word list (P0) is not extracted: it already takes English words.

A build with no English leaves the disk's files as they are; any English adds the tables (SARADA.T0-T4,
P0's strings and each chapter's), patches P0's string routine and each chapter's inventory, and makes
START load the tables (pc98tl/sarada.py).
"""
import json
import os

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .n88disk import N88Image
from . import sarada as S
from .text import pseudo

PREFIX = {"msg": "m", "name": "n"}
CHAPTERS = (1, 2, 3, 4)
NOTE = {"msg": "a message: any length; broken between words at the screen's width from where the cursor "
               "is, \\n a new line; a key waited for after each windowful (3 lines)",
        "name": "an object's name in the inventory list (one line, the names after it on the same line)"}


def _files():
    return ["SARADA.P0"] + ["SARADA.P%d" % n for n in CHAPTERS]


def kind_of(body, first):
    """name for an inventory record's name (after its flag's address, 01xxh), msg otherwise."""
    return "name" if body[first - 1] == 0x01 and body[first - 3] == 0x00 else "msg"


def found(vol):
    """[(file, address, start, end, kind, jp)]."""
    out = []
    for name in _files():
        data = vol.read(name)
        _st, body = S.bsave(data)
        for addr, s, e in S.strings(name, data):
            out.append((name, addr, s, e, kind_of(body, s), S.show(body[s:e])))
    return out


def run_extract(here, src):
    vol = N88Image([src]).volumes[0]
    merged, order = {}, []
    for name, addr, s, e, kind, jp in found(vol):
        key = (kind, jp)
        ref = "%s:%04x" % (name, addr)
        if key in merged:
            merged[key]["refs"].append(ref)
            continue
        room = 79 if kind == "name" else 79 * (S.WINDOW - 1)
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": NOTE[kind]}
        order.append(key)
    counts, strings = {}, []
    for key in order:
        ent = merged[key]
        counts[ent["kind"]] = counts.get(ent["kind"], 0) + 1
        strings.append({"id": "%s%05d" % (PREFIX[ent["kind"]], counts[ent["kind"]]), **ent})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):
        old = {(x["kind"], x["jp"]): x for x in json.load(open(out, encoding="utf-8"))["strings"]}
        for ent in strings:
            prev = old.get((ent["kind"], ent["jp"]))
            if prev:
                ent["en"] = prev.get("en", "")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _pseudo(e):
    if e["kind"] == "msg":
        return pseudo(e["id"], 2 * len(e["jp"].replace("\n", "")))
    return pseudo(e["id"], 2 * len(e["jp"]), 1.0).split(" ")[0]


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = N88Image([src])
    vol = img.volumes[0]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    tables = {name: [] for name in _files()}
    for name, addr, s, e, kind, _jp in found(vol):
        en = by_ref.get("%s:%04x" % (name, addr))
        if en is None:
            continue
        if kind == "name":
            en = " ".join(en.split("\n"))
            if len(en) > 79:
                warn.append("%s: %d letters, a line holds 79" % (ids["%s:%04x" % (name, addr)]["id"], len(en)))
        tables[name].append((addr, e - s, S.encode(en)))
    if any(tables.values()):
        p0 = vol.read("SARADA.P0")
        disk = img.disks[0]
        for n in (0,) + CHAPTERS:
            entries = tables["SARADA.P0"] + (tables["SARADA.P%d" % n] if n else [])
            disk.create("SARADA.T%d" % n, S.pool(p0, entries), 0x80)
        vol.write("SARADA.P0", S.patch_p0(p0))
        for n in CHAPTERS:
            vol.write("SARADA.P%d" % n, S.patch_chapter(vol.read("SARADA.P%d" % n)))
        vol.write("START", S.patch_start(vol.read("START"), CHAPTERS))
    vol.create("MTL_NOTE.TXT", MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
