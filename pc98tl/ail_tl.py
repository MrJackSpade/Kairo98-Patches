"""English for Ail's ADV.EXE (pc98tl/ail.py): strings.json in, a patched image out.

Strings (refs SCENARIO:offset of the text in its text section; the program's own strings
ADV.EXE:offset in its data):

* "msg": a message: any length.  The program lays a message out two bytes at a time (a Shift-JIS
  character, or two ASCII letters, each drawn half-width from the kanji ROM) and breaks the line
  after 27 of them (54 cells) in a slot sub-op 00h fills (indented under the name), after 29 (58
  cells) in one sub-op 01h fills (from the window's edge): `max_cells` the narrower of its slots'.
  The patcher breaks the English between words by filling the line with spaces to that width, and
  the program pages by itself (four lines a page, the name the first page's first).  `\\n` in the English forces a new
  line.  `>` (the program's colour mark) is written `)` and `%` (its insert mark) `pct`.
* "name": a speaker's name (the texts in 【】): `max_cells` the Japanese's.
* "item": a choice's item (one line in the choice's box): `max_cells` the choice's widest Japanese
  item; past it reported.
* "title": a scene's title, shown with a choice: `max_cells` the Japanese's; past it reported.
* "label": a string of the program's (its menus, its prompts, its messages): in place, `max_cells`
  its room in bytes (a letter one, a full-width character two); past it cut and reported.
  `%s`-style marks in it are kept.

English is ASCII (half-width); another character is written full-width in Shift-JIS when it has one,
else `?`.  Every text is padded with a space to an even length (the program reads two bytes at a
time).  A changed scenario is packed again (`ail.pack`); unpacked it may take game.json's
"scenario_room" (the program's buffer: Kyouhaku's ADV.EXE unpacks a scenario to DS:8A98h, the C
library's string buffer at D214h after it: 18300 bytes); a longer build is refused and names the
scenario's strings.
"""
import json
import os
import re

from . import ail, exepack
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "item": "i", "title": "t", "label": "l"}
LINE = {0x00: 54, 0x01: 58}     # a message's line in a slot sub-op 00h or 01h fills
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", ">": ")", "%": "pct"}
# the program's strings: Shift-JIS (with ASCII) up to a NUL, in its data (after its code)
PROG_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                      rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*\x00")
FORMAT = re.compile(r"%[0-9]*[sdux]")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def _program(raw):
    """(plain MZ, its load image)."""
    exe = exepack.unpack(raw) if exepack.is_packed(raw) else raw
    hdr = int.from_bytes(exe[8:10], "little") * 16
    return exe, hdr


def _data_start(img):
    """Where the program's data starts: its data group, whose 8th byte starts the C library's
    copyright line."""
    i = img.find(b"MS Run-Time Library")
    if i < 8:
        raise ValueError("ADV.EXE: the data group not found")
    return i - 8


def prog_strings(exe, hdr):
    """[(start, end)] in the MZ file: the program's strings with Japanese in them (the line-break
    table of punctuation left out)."""
    img = exe[hdr:]
    ds = _data_start(img)
    out = []
    for m in PROG_STR.finditer(img, ds):
        s = m.group()[:-1]
        txt = s.decode("cp932", "replace")
        if re.fullmatch(r"[、。」』！）”ーっッぁァぃィぅゥぇェぉォゃャゅュょョゎヮヵヶ・？…‥，．\s]+", txt):
            continue
        out.append((hdr + m.start(), hdr + m.end() - 1))
    return out


def cells(text):
    return max((sum(1 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 2 for c in line)
                for line in text.split("\n")), default=0)


def _sjis(ch):
    try:
        e = ch.encode("cp932")
    except UnicodeEncodeError:
        return b"?"
    return e


def encode(text, width=None):
    """English as the program's bytes: ASCII as it is, another character in Shift-JIS (on an even
    place), the lines filled with spaces to width (a new line: the rest of the line filled), padded to
    an even length."""
    out = bytearray()
    t = "".join(SUBST.get(c, c) for c in text)
    lines = t.split("\n")
    for k, line in enumerate(lines):
        start = len(out)
        for ch in line:
            if " " <= ch <= "~":
                out.append(ord(ch))
            else:
                if len(out) & 1:
                    out.append(0x20)
                out += _sjis(ch)
        if width and k < len(lines) - 1:
            used = (len(out) - start) % width
            if used or len(out) == start:
                out += b" " * (width - used)
    if len(out) & 1:
        out.append(0x20)
    return bytes(out)


def wrap(text, width):
    """The English with new lines between words at width cells."""
    out = []
    for k, para in enumerate(text.split("\n")):
        if k:
            out.append("\n")
        col = 0
        for j, word in enumerate(para.split(" ")):
            w = cells(word)
            if j:
                if col + 1 + w > width and col:
                    out.append("\n")
                    col = 0
                else:
                    out.append(" ")
                    col += 1
            out.append(word)
            col += w
            while col > width:
                col -= width
    return "".join(out)


def _show(b):
    return b.decode("cp932", "replace")


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    gd = cfg["game_dir"]
    exe, hdr = _program(vol.read(gd + "/" + cfg["program"]))
    build = ail.Build(exe[hdr:])
    sc = ail.read_snl(vol.read(gd + "/" + cfg["scenarios"]))
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
    for s, e in prog_strings(exe, hdr):
        jp = _show(exe[s:e]).rstrip("$")
        if jp.strip("　 "):
            add("label", jp, "%s:%05x" % (cfg["program"], s - hdr), e - s,
                "a string of the program's (a menu, a prompt): its room in bytes (a letter one, a full-width "
                "character two); %s-style marks kept")
    for k, (mode, d) in enumerate(sc):
        if not d:
            continue
        kinds, rooms = classify(d, build)
        for off in sorted(kinds):
            jp = _show(ail.text_at(d, off))
            if not jp.strip("　 "):
                continue
            ref = "%d:%04x" % (k, off)
            kind = kinds[off]
            if kind == "msg":
                add("msg", jp, ref, rooms[off])
            elif kind == "name":
                add("name", jp, ref, cells(jp), "a speaker's name, shown above the message")
            elif kind == "item":
                add("item", jp, ref, rooms[off], "a choice's item: one line in its box (the choice's widest "
                    "Japanese item)")
            else:
                add("title", jp, ref, cells(jp), "a scene's title, shown with the choice (and kept with a "
                    "save): `max_cells` the Japanese's")
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


SHOW_MESSAGE = range(0x03, 0x08)     # the sub-ops showing the message box (the slots put before them)


def classify(d, build):
    """({offset: "msg", "name", "item" or "title"}, {offset: a message's line or an item's room}):
    the texts the slots hold (sub-ops 00h and 01h put a text in a slot) are a message's (slot 0 the
    speaker's name, in 【】) when a sub-op showing the message box comes after them, a choice's items
    when the choice (a sub-op with a text of its own, the scene's title) does."""
    kinds, rooms = {}, {}
    pending = []

    def settle(kind):
        if kind == "item":
            room = max(cells(_show(ail.text_at(d, o))) for o, _s in pending) if pending else 0
        for o, s in pending:
            jp = _show(ail.text_at(d, o))
            if kind == "item":
                kinds.setdefault(o, "item")
                rooms[o] = room
            else:
                kinds.setdefault(o, "name" if jp.startswith("【") and jp.endswith("】") else "msg")
                if kinds[o] == "msg":
                    rooms[o] = min(rooms.get(o, LINE[s]), LINE[s])
        pending.clear()
    for kind, _p, off, sub, _first in ail.events(d, build):
        if kind == "text" and sub in (0x00, 0x01):
            pending.append((off, sub))
        elif kind == "text":
            settle("item")
            kinds.setdefault(off, "title")
        elif sub in SHOW_MESSAGE:
            settle("msg")
    settle("msg")
    return kinds, rooms


def _pseudo(e):
    if e["kind"] in ("item", "title"):
        return pseudo(e["id"], e["max_cells"], 1.0)[:max(2, e["max_cells"])]
    if e["kind"] == "label":
        marks = FORMAT.findall(e["jp"])
        return (" ".join(marks) + " " if marks else "") + pseudo(e["id"], e["max_cells"], 1.0)[:max(
            1, e["max_cells"] - sum(len(m) + 1 for m in marks))]
    if e["kind"] == "name":
        return "[" + pseudo(e["id"], e["max_cells"], 1.0)[:max(1, e["max_cells"] - 2)] + "]"
    return pseudo(e["id"], cells(e["jp"]))


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"]
    prog_path = gd + "/" + cfg["program"]
    raw_prog = vol.read(prog_path)
    exe, hdr = _program(raw_prog)
    build = ail.Build(exe[hdr:])
    snl_path = gd + "/" + cfg["scenarios"]
    raw_snl = vol.read(snl_path)
    sc = ail.read_snl(raw_snl)
    by_ref, ids, rooms = {}, {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            rooms[r] = e["max_cells"]
            if text:
                by_ref[r] = text
    warn = []
    prog = bytearray(exe)
    for s, e in prog_strings(exe, hdr):
        ref = "%s:%05x" % (cfg["program"], s - hdr)
        en = by_ref.get(ref)
        if en is None:
            continue
        dollar = exe[s:e].endswith(b"$")
        room = e - s - dollar
        b = encode(en)
        if len(b) > room:
            warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), room))
            b = b[:room - (room & 1)]
        prog[s:e] = (b + b"$" * dollar).ljust(e - s, b"\0" if not dollar else b" ")
    raws = {k: blk for k, blk in enumerate(ail.blocks(raw_snl))}
    room = cfg["scenario_room"]
    changed = 0

    def build_one(d, refs, k, ratio):
        new = {}
        for _p, off in refs:
            ref = "%d:%04x" % (k, off)
            en = by_ref.get(ref)
            if en is None or off in new:
                continue
            if ratio < 1.0:
                en = en[:max(4, int(len(en) * ratio))]
            if ids[ref].startswith("m"):
                new[off] = encode(wrap(en, rooms[ref]), rooms[ref])
            else:
                b = encode(en)
                if ids[ref][0] in "it" and cells(en) > rooms[ref]:
                    warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
                new[off] = b
        return new, ail.rebuild(d, refs, new) if new else d
    for k, (m, d) in enumerate(sc):
        if not d:
            continue
        refs = ail.walk(d, build)
        new, out = build_one(d, refs, k, 1.0)
        if len(out) > room:
            if mode != "pseudo":
                raise SystemExit("scenario %d: %d bytes with its English, the program holds %d; shorten these "
                                 "strings: %s" % (k, len(out), room, ", ".join(sorted(
                                     {ids[r] for r in by_ref if r.startswith("%d:" % k)}))))
            ratio = 1.0
            while len(out) > room:
                ratio *= 0.9
                new, out = build_one(d, refs, k, ratio)
            warn.append("scenario %d: the filler was cut to %d%% to fit the program's %d bytes" % (
                k, int(ratio * 100), room))
        if new:
            sc[k] = (m, out)
            del raws[k]
            changed += 1
    if changed:
        vol.write(snl_path, ail.write_snl(sc, raws))
    if bytes(prog) != exe:
        vol.write(prog_path, bytes(prog))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scenarios rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), changed))
