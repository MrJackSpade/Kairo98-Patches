"""English for MicroCabin's PIYO engine (pc98tl/piyo.py: Maison Ikkoku): strings.json in, a patched
image out.

Strings:
* m (message, PIYO.LBC): broken between words at the message window's width (game.json "width",
  half-width cells), `\\n` a forced new line.  PIYO.LBC is written anew, every message's place set in
  PIYO.LDY's table.
* u (menu: the commands) and n (name: things and people, shown in the menus and the messages): any
  length up to the menu's room (game.json "menu_cells"); a changed one goes at PIYO.LDY's end, its
  table entry pointed at it.
* l (line, inside PIYO.LDY's script code): in place, its bytes the room.
* e (PIYO.EXE's notices): in place, its bytes the room.
English goes out as ASCII: the text layer writer (PIYO.EXE) draws a one-byte character as a
half-width cell itself.
"""
import json
import os

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import piyo as P, engine_strings
from .text import pseudo

PREFIX = {"msg": "m", "menu": "u", "name": "n", "line": "l", "engine": "e"}
SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-",
         "…": "..."}


def show(b):
    return b.decode("cp932", "replace")


def cells(text):
    return len(encode(text))


def encode(text):
    """ASCII, anything else Shift-JIS when it has it, else '?'."""
    out = b""
    for ch in "".join(SUBST.get(c, c) for c in text):
        if ch == "\n" or 0x20 <= ord(ch) < 0x7F:
            out += ch.encode("ascii")
            continue
        try:
            out += ch.encode("cp932")
        except UnicodeEncodeError:
            out += b"?"
    return out


def wrap(text, width):
    """[line] of the English broken between words at `width` cells."""
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = word if not line else line + " " + word
            if cells(cand) <= width or not line:
                line = cand
                while cells(line) > width:
                    out.append(line[:width])
                    line = line[width:]
                continue
            out.append(line)
            line = word
        out.append(line)
    return out


def _vol(src):
    return DiskImage(src)


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _vol(src).volumes[0]
    ldy, lbc = vol.read("PIYO.LDY"), vol.read("PIYO.LBC")
    width, menu = cfg["width"], cfg["menu_cells"]
    merged, order = {}, []

    def add(kind, jp, ref, room, note):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
        order.append(key)

    for n, t in enumerate(P.messages(ldy, lbc)):
        add("msg", show(t), "PIYO.LBC:%d" % n, width * cfg["window_lines"],
            "a message: broken between words at %d half-width cells, \\n a new line" % width)
    for name, kind in (("menu", "menu"), ("names", "name")):
        for n, (_p, t) in enumerate(P.strings(ldy, name)):
            add(kind, show(t), "PIYO.LDY:%s:%d" % (name, n), menu,
                {"menu": "a command in the menu: one line, its room the menu's width",
                 "name": "a thing's or a person's name, shown in the menus (one line, the menu's width) "
                         "and in messages"}[kind])
    for s, e in P.inline(ldy):
        add("line", show(ldy[s:e]), "PIYO.LDY:%04x" % s, e - s,
            "a string inside the script's code: written in place, its room (max_cells) the Japanese's bytes")
    exe = vol.read("PIYO.EXE")
    for s, e, t in engine_strings.find(exe):
        add("engine", t, "PIYO.EXE:%05x" % s, e - s,
            "a notice of the program's: written in place, its room the Japanese's bytes")
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
        return "\n".join(pseudo(e["id"], len(line.encode("cp932"))) for line in e["jp"].split("\n"))
    return pseudo(e["id"], e["max_cells"], 1.0)[:e["max_cells"]]


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _vol(src)
    vol = img.volumes[0]
    width, rows = cfg["width"], cfg["window_lines"]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    ldy, lbc = vol.read("PIYO.LDY"), vol.read("PIYO.LBC")
    texts = P.messages(ldy, lbc)
    changed = False
    for n in range(len(texts)):
        en = by_ref.get("PIYO.LBC:%d" % n)
        if en is None:
            continue
        lines = wrap(en, width)
        if len(lines) > rows:
            warn.append("%s: %d lines, the window shows %d" % (ids["PIYO.LBC:%d" % n]["id"], len(lines), rows))
        texts[n] = encode("\n".join(lines))
        changed = True
    new_strings = {}
    for name in ("menu", "names"):
        for n, (_p, t) in enumerate(P.strings(ldy, name)):
            ref = "PIYO.LDY:%s:%d" % (name, n)
            en = by_ref.get(ref)
            if en is None:
                continue
            b = encode(" ".join(en.split("\n")))
            if len(b) > cfg["menu_cells"]:
                warn.append("%s: %d cells, the menu's room %d" % (ids[ref]["id"], len(b), cfg["menu_cells"]))
            new_strings[(name, n)] = b
    inline_texts = {}
    for s, e in P.inline(ldy):
        ref = "PIYO.LDY:%04x" % s
        en = by_ref.get(ref)
        if en is None:
            continue
        b = encode(en)
        if len(b) > e - s:
            warn.append("%s: %d bytes, room for %d" % (ids[ref]["id"], len(b), e - s))
            b = b[:e - s]
        inline_texts[s] = b.ljust(e - s, b" ")
    if changed or new_strings or inline_texts:
        try:
            new_lbc, places = P.build_lbc(texts)
            new_ldy = P.build_ldy(ldy, places, new_strings, inline_texts)
        except ValueError as ex:
            raise SystemExit("%s; shorten the English" % ex)
        vol.write("PIYO.LBC", new_lbc)
        vol.write("PIYO.LDY", new_ldy)
    exe = vol.read("PIYO.EXE")
    runs = list(engine_strings.find(exe))
    values = {}
    for s, e, _t in runs:
        ref = "PIYO.EXE:%05x" % s
        if ref in by_ref:
            values[s] = encode(" ".join(by_ref[ref].split("\n")))
    if values:
        new, cut = engine_strings.apply(exe, runs, values)
        for s, need, room in cut:
            warn.append("%s: %d bytes, the program has room for %d" % (ids["PIYO.EXE:%05x" % s]["id"], need, room))
        vol.write("PIYO.EXE", new)
    vol.create("MTL_NOTE.TXT", MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
