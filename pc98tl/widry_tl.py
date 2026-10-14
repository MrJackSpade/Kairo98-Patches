"""English for Wizard and the Princess (pc98tl/widry.py): strings.json in, a patched disk out.

Strings:
* m (message): a message of a room's (RDA), of the game's common record (MDA) or of the engine's,
  printed through its span printer.  Any length: printed a word at a time, the engine breaking lines
  between words at 79 columns and waiting for a key after four lines; \\n a new line.  The same
  Japanese is one string (the engine finds its English by the Japanese).  Some messages are pieces
  the game prints one after another (a verb's ending after an object's name): their English follows
  on the same line.
* e (engine): a string the engine prints at a length of its own (its function keys' labels, the save
  slot prompt, the key prompt): written in place, max_cells letters, padded with spaces.

A build with English adds the table WIDRY.ENG (loaded by M98 at 3000h:0), lengthens WIDRY.ASM by its
helper and makes its span printer go through it, and makes M98 load the table; the data files stay as
they are, so the parser still takes the game's own (katakana) words.
"""
import json
import os

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .n88disk import N88Image
from . import n88prog as P
from . import widry as W
from .text import pseudo

PREFIX = {"msg": "m", "engine": "e"}
NOTE = {"msg": "a message: any length, printed a word at a time (lines broken between words at 79 columns, "
               "a key waited for after four lines); \\n a new line; a piece of a longer message follows on the "
               "same line",
        "engine": "a string of the engine's printed at its own length: written in place, max_cells letters"}


def _image(src):
    return N88Image([src])


def show(b):
    return b.split(b"\0", 1)[0].decode("cp932", "replace")


def found(vol, cfg):
    """[(ref, kind, Japanese bytes, room)]."""
    out = []
    for name in cfg["data"]:
        data = vol.read(name)
        for s, e in W.strings(data):
            out.append(("%s:%05x" % (name, s), "msg", data[s:e], None))
        for s, e in W.descriptions(data):
            out.append(("%s:d%05x" % (name, s), "msg", data[s:e], None))
    eng = vol.read(cfg["engine"])
    org, body = W.bsave(eng)
    for s, e in W.engine_spans(eng):
        out.append(("E:%04x" % s, "msg", body[s - org:e - org], None))
    for s, n in W.engine_fixed(eng):
        out.append(("F:%04x" % s, "engine", body[s - org:s - org + n], n))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    merged, order = {}, []
    for ref, kind, jp_b, room in found(vol, cfg):
        jp = show(jp_b)
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            continue
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref],
                       "max_cells": room if kind == "engine" else 79 * 4, "note": NOTE[kind]}
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
    if e["kind"] == "engine":
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"]]
    return pseudo(e["id"], 2 * len(e["jp"]))


def _defseg(seg):
    return b"\x98\x01\xe4\xf1\x0c" + bytes([seg & 0xFF, seg >> 8])


def _bload(name):
    return b"\x82\x01\x22" + name.encode("ascii") + b"\x22"


def patch_loader(prog, engine_name, pool_name, seg):
    """M98 with the table BLOADed (at POOL:0) right after the engine: :DEF SEG=pool:BLOAD "table":DEF
    SEG=engine's segment, put after the engine's BLOAD."""
    lines, tail = P.read(prog)
    tag = _bload(engine_name)
    out, done = [], False
    for num, body in lines:
        k = body.find(tag)
        if k >= 0 and not done:
            e = k + len(tag)
            ins = b":" + _defseg(W.POOL) + b":" + _bload(pool_name) + b":" + _defseg(seg)
            body = body[:e] + ins + body[e:]
            done = True
        out.append((num, body))
    if not done:
        raise SystemExit("M98: no BLOAD of %s" % engine_name)
    return P.write(out, tail)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    entries = []
    eng = vol.read(cfg["engine"])
    org, body = W.bsave(eng)
    body = bytearray(body)
    for ref, kind, jp_b, room in found(vol, cfg):
        en = by_ref.get(ref)
        if en is None:
            continue
        if kind == "msg" and ":d" in ref:
            parts = W.chunks(jp_b)
            entries.append((parts[0], W.encode(en)))
            entries += [(p_, b"") for p_ in parts[1:]]
        elif kind == "msg":
            entries.append((jp_b, W.encode(en)))
        else:
            s = int(ref[2:], 16)
            b = W.encode(" ".join(en.split("\n")))
            if len(b) > room:
                warn.append("%s: %d letters, room for %d" % (ids[ref]["id"], len(b), room))
                b = b[:room]
            body[s - org:s - org + room] = b.ljust(room, b" ")
    if entries or bytes(body) != W.bsave(eng)[1]:
        vol.write(cfg["engine"], W.patch_engine(W.make_bsave(org, bytes(body))))
        attr = vol.find(cfg["engine"])["attr"]
        vol.disks[0].create(cfg["pool"], W.pool(entries), attr)
        vol.write(cfg["loader"], patch_loader(vol.read(cfg["loader"]), cfg["engine"], cfg["pool"], cfg["segment"]))
    vol.create("MTL_NOTE.TXT", MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
