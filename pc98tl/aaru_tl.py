"""English for Aaru's engine (pc98tl/aaru.py): strings.json in, a patched image out.

Strings (refs ARCHIVE/SCRIPT:offset or SCRIPT:offset in the (unpacked) script; the program's own strings
PROGRAM:offset in the program file):

* "msg": a message (op 00h's text, `\\n` its lines, `\\N` in the script): any length.  The program
  draws ASCII half-width, breaks a line at the window's edge and waits for a key when the window is
  full; the patcher breaks the English between words at `max_cells` (the window's width in half-width
  cells: game.json "window_cells", else 60) with the program's new line between them.  `\\n` in the
  English forces a new line.
* "item": a choice's item (op 01h's text): `max_cells` the choice's widest Japanese item; past it
  reported.
* "label": a string of the program's (its menus): in place, `max_cells` its room in bytes; past it cut
  and reported.

The program's controls are tokens (`CONTROL`, `TOKEN`), kept in the English: `{C7}` a colour (`\\(7)`),
`{S}` a key wait (`\\S`), `{G08-z}` a face picture (`\\G08-z.`) and `{G}` its end (`\\G.`).  English is
ASCII (half-width; a byte from 60h written one higher, see `encode`; `` ` { } ~ ``, which the program
does not draw, written `' ( ) -`); another character is written full-width in Shift-JIS when it has one,
else `?`.  A string of the program's keeps its room, filled with spaces (its menus read the strings one
after another).  `\\`, `%` and `|` (the program's controls) are written `/`, `pct` and `!`.  A changed
script is laid out anew with its jumps moved, compressed again when it was, and its archive (or its
file) written anew; the program reads a script of at most 65535 bytes, so a longer build is refused and
names its strings.
"""
import json
import os
import re

from . import aaru as A
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "item": "i", "label": "l"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "\\": "/", "%": "pct",
         "|": "!", "`": "'", "{": "(", "}": ")", "~": "-"}
ROOM = 0xFFFF
PROG_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                      rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*\x00")
WORDY = re.compile(r"[ぁ-ヿ一-鿿Ａ-ｚ]")
# the program's controls as strings.json shows them: `{C7}` a colour (\(7)), `{S}` a key wait (\S),
# `{G08-z}` a face picture shown (\G08-z.), `{G}` the picture taken away (\G.)
CONTROL = re.compile(r"\\\((\d+)\)|\\S|\\G([^.\\]*)\.")
TOKEN = re.compile(r"\{C(\d+)\}|\{S\}|\{G([^{}]*)\}")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def cells(text):
    text = TOKEN.sub("", text)
    return max((sum(1 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 2 for c in line)
                for line in text.split("\n")), default=0)


def _sjis(ch):
    try:
        return ch.encode("cp932")
    except UnicodeEncodeError:
        return b"?"


def encode(text):
    """The English as the program's bytes: ASCII, a byte from 60h written one higher (the program
    draws a byte as Shift-JIS 8540h plus it less 21h, and from 60h that steps over the code 857Fh,
    which Shift-JIS has not: a letter low); another character in Shift-JIS."""
    out, at = bytearray(), 0
    for m in list(TOKEN.finditer(text)) + [None]:
        for ch in text[at:m.start() if m else len(text)]:
            for c in SUBST.get(ch, ch):
                if c == "\n":
                    out += b"\\N"
                elif " " <= c <= "~":
                    out.append(ord(c) + (1 if ord(c) >= 0x60 else 0))
                else:
                    out += _sjis(c)
        if m is None:
            return bytes(out)
        at = m.end()
        if m.group(1) is not None:
            out += b"\\(" + m.group(1).encode() + b")"
        elif m.group() == "{S}":
            out += b"\\S"
        else:
            out += b"\\G" + m.group(2).encode("cp932") + b"."


def wrap(text, width):
    out = []
    for para in text.split("\n"):
        line, col = [], 0
        for word in para.split(" "):
            w = cells(word)
            if line and col + 1 + w > width:
                out.append(" ".join(line))
                line, col = [], 0
            line.append(word)
            col += w + (1 if len(line) > 1 else 0)
        out.append(" ".join(line))
    return out


def prog_strings(exe):
    """[(start, end)] in the program file: its strings, the largest run of them packed together (the
    menus' block; a lone kanji-like run in the code left out)."""
    hits = [(m.start(), m.end() - 1) for m in PROG_STR.finditer(exe)
            if WORDY.search(m.group()[:-1].decode("cp932", "replace")) and m.end() - m.start() > 4]
    groups, cur = [], []
    for s, e in hits:
        if cur and s - cur[-1][1] > 8:
            groups.append(cur)
            cur = []
        cur.append((s, e))
    if cur:
        groups.append(cur)
    return max(groups, key=len) if groups else []


def scripts(vol, gd):
    """[(file, name)]: a script in an FL1 archive (the archive's path, the script's name), or a file
    of its own (its path, None)."""
    out = []
    for n, e in vol.walk():
        if not n.upper().startswith(gd.upper() + "/"):
            continue
        if n.upper().endswith(".FL1"):
            raw = vol.read(n)
            for nm, off, sz in A.fl1(raw):
                if nm.upper().endswith(".AB"):
                    out.append((n, nm))
        elif n.upper().endswith(".AB"):
            out.append((n, None))
    return out


def _script(raw, nm):
    if nm is None:
        return (A.unlz(raw), True) if A.compressed(raw) else (raw, False)
    for name, off, sz in A.fl1(raw):
        if name == nm:
            d = raw[off:off + sz]
            return (A.unlz(d), True) if A.compressed(d) else (d, False)
    raise KeyError(nm)


def _rel(gd, arc, nm):
    return arc[len(gd) + 1:] if nm is None else "%s/%s" % (arc[len(gd) + 1:], nm)


def show(b):
    def tok(m):
        if m.group(1) is not None:
            return "{C%s}" % m.group(1)
        return "{S}" if m.group() == "\\S" else "{G%s}" % m.group(2)
    return CONTROL.sub(tok, b.decode("cp932", "replace")).replace("\\N", "\n")


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    gd = cfg["game_dir"]
    prog = vol.read(gd + "/" + cfg["program"])
    merged, order = {}, []

    def add(kind, jp, ref, cells_, note=None):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], cells_)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells_}
        if note:
            merged[key]["note"] = note
        order.append(key)
    for s, e in prog_strings(prog):
        jp = show(prog[s:e])
        add("label", jp, "%s:%05x" % (cfg["program"], s), e - s,
            "a string of the program's (its menus): its room in bytes (a letter one, a full-width character two)")
    raws = {}
    for arc, nm in scripts(vol, gd):
        raws.setdefault(arc, vol.read(arc))
        d, _c = _script(raws[arc], nm)
        _p, ev = A.walk(d)
        rel = _rel(gd, arc, nm)
        its = [e for e in ev if e[0] == "item"]
        room = max((cells(show(d[e[2]:e[3]])) for e in its), default=0)
        for e in ev:
            if e[0] == "text" and show(d[e[1]:e[2] - 1]).strip("　 \n"):
                add("msg", show(d[e[1]:e[2] - 1]), "%s:%04x" % (rel, e[1]), cfg.get("window_cells", A.LINE))
            elif e[0] == "item":
                add("item", show(d[e[2]:e[3]]), "%s:%04x" % (rel, e[1]), room,
                    "a choice's item (the script's widest Japanese item)")
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
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _pseudo(e):
    """Filler keeping the Japanese's leading and trailing controls (a colour, a face picture, a label's
    new line)."""
    lead = re.match(r"(?:\{[CSG][^{}]*\})*", e["jp"]).group()
    tail = re.search(r"(?:\{[CSG][^{}]*\}|\n)*$", e["jp"]).group()
    if e["kind"] == "label":
        room = e["max_cells"] - len(encode(lead + tail))
        return lead + pseudo(e["id"], e["max_cells"], 1.0)[:max(1, room)] + tail
    if e["kind"] == "item":
        return pseudo(e["id"], e["max_cells"], 1.0)[:max(2, e["max_cells"])]
    return lead + pseudo(e["id"], cells(e["jp"])) + tail


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"]
    prog_path = gd + "/" + cfg["program"]
    prog = vol.read(prog_path)
    by_ref, ids, rooms = {}, {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            rooms[r] = e["max_cells"]
            if text:
                by_ref[r] = text
    warn = []
    out_prog = bytearray(prog)
    for s, e in prog_strings(prog):
        ref = "%s:%05x" % (cfg["program"], s)
        en = by_ref.get(ref)
        if en is None:
            continue
        b = encode(en)
        if len(b) > e - s:
            warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), e - s))
            b = b[:e - s]
            while b and len(b.decode("cp932", "ignore").encode("cp932")) != len(b):
                b = b[:-1]
        out_prog[s:e] = b.ljust(e - s, b" ")     # (its menus read the strings one after another)
    if bytes(out_prog) != prog:
        vol.write(prog_path, bytes(out_prog))
    archives, rebuilt = {}, 0
    for arc, nm in scripts(vol, gd):
        raw = archives.get(arc) or vol.read(arc)
        archives.setdefault(arc, raw)
        d, comp = _script(vol.read(arc), nm)
        _p, ev = A.walk(d)
        rel = _rel(gd, arc, nm)
        texts, items = {}, {}
        for e in ev:
            if e[0] == "text":
                ref = "%s:%04x" % (rel, e[1])
                en = by_ref.get(ref)
                if en is not None:
                    texts[e[1]] = (e[2], b"\\N".join(encode(x) for x in wrap(en, rooms[ref])) + b"\0")
            elif e[0] == "item":
                ref = "%s:%04x" % (rel, e[1])
                en = by_ref.get(ref)
                if en is not None:
                    if cells(en) > rooms[ref]:
                        warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
                    items[e[1]] = encode(en)
        if not texts and not items:
            continue
        new = A.rebuild(d, texts, items)
        if len(new) > ROOM:
            raise SystemExit("%s: %d bytes with its English, the program reads %d; shorten these strings: %s" % (
                rel, len(new), ROOM, ", ".join(sorted({ids[r] for r in by_ref if r.startswith(rel + ":")}))))
        packed = A.lz(new) if comp else new
        archives[arc] = packed if nm is None else A.fl1_build(archives[arc], {nm: packed})
        rebuilt += 1
    for arc, raw in archives.items():
        if raw != vol.read(arc):
            vol.write(arc, raw)
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), rebuilt))
