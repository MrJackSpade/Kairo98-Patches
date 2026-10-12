"""English for Youjuu Senki (pc98tl/yjwar.py): strings.json in, a patched image out.

Strings (refs FILE:offset, ARCHIVE/FILE:offset or FILE:line):

* "msg": a scene's message (a *.TXB entry): any length; `max_cells` its window's width in half-width
  cells (`WIDTH` by the entry's kind).  The program breaks a line at the window's edge mid-word and
  draws a fifth line over the screen; the patcher breaks the English between words, filling a line's
  end with spaces, and a text of more than `ROWS` lines becomes several entries (pages, a click
  each).  The opening's pages (kind 6) are centred line by line as the Japanese is.  `\\n` forces a
  new line.
* "scene": an animated scene's message (*.SC op 24h): as "msg" (its pages several commands),
  `max_cells` `SCENE`.
* "profile": a line of a soldier's profile (*.SC op 29h, at a fixed place): one line, `max_cells`
  `PROFILE`; past it reported.
* "battle": a map's battle line (*.MSG): broken between words at `BATTLE` cells; at most `BATTLE_ROOM`
  bytes (the longest Japanese line), past it cut and reported.
* "doc": a paragraph of a data page (DATA_*.TXT): any length, broken between words at the page's
  width (`DOC` cells) with the Japanese's indents.
* "name": a unit's name (UNIT.DAT and the program's copy): at most 19 bytes, past it cut and reported;
  `max_cells` the panels' room (the longest Japanese name), past it reported.
* "label": a string of the program's: in place, `max_cells` its room in bytes; past it cut and
  reported.  `%s`/`%d` marks are kept.

English is ASCII (half-width, the program draws it itself); another character is written full-width
when Shift-JIS has it, else `?`.  Changed files are written back (an archive anew, its directory's
sizes set).
"""
import json
import os
import re

from . import yjwar as Y
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "scene": "s", "profile": "p", "battle": "b", "doc": "d", "name": "n", "label": "l"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}
WIDTH = {1: 70, 2: 70, 3: 70, 5: 70, 6: 70, 7: 70, 8: 70, 9: 70}
SCENE = 70
ROWS = 4                        # a message window's lines
PROFILE = 36
BATTLE = 28
BATTLE_ROOM = 78
DOC = 62
NAME_CELLS = 16                 # a name's room in the panels (the longest Japanese)
PROG_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                      rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*\x00")
KANA = re.compile(r"[ぁ-ヶ一-龠]")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def cells(text):
    return max((sum(1 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 2 for c in line)
                for line in text.split("\n")), default=0)


def encode(text):
    out = bytearray()
    for ch in text:
        for c in SUBST.get(ch, ch):
            if " " <= c <= "~":
                out.append(ord(c))
            else:
                try:
                    out += c.encode("cp932")
                except UnicodeEncodeError:
                    out += b"?"
    return bytes(out)


def wrap(text, width, first=0, rest=0):
    """The English's lines, broken between words: the first line's indent `first`, the others' `rest`."""
    out = []
    for para in text.split("\n"):
        line, col = [], first if not out else rest
        start = col
        for word in para.split(" "):
            w = cells(word)
            if line and col + 1 + w > width:
                out.append((start, " ".join(line)))
                line, col = [], rest
                start = rest
            line.append(word)
            col += w + (1 if len(line) > 1 else 0)
        out.append((start, " ".join(line)))
    return out


def filled(text, width):
    """The English as one run the program breaks itself: each line filled with spaces to the edge."""
    lines = wrap(text, width)
    return "".join(s + " " * (width - cells(s)) if k < len(lines) - 1 else s
                   for k, (_i, s) in enumerate(lines))


def pages(text, width, centre=False):
    """The English as the window's pages (ROWS lines each; the program draws a fifth line over the
    screen): each a run of lines filled to the edge, or centred (the opening's)."""
    lines = [s for _i, s in wrap(text, width)]
    out = []
    for k in range(0, len(lines), ROWS):
        page = lines[k:k + ROWS]
        if centre:
            out.append("".join(" " * ((width - cells(s)) // 2) + s + " " * (width - cells(s) - (width - cells(s)) // 2)
                               for s in page))
        else:
            out.append("".join(s + " " * (width - cells(s)) if j < len(page) - 1 else s for j, s in enumerate(page)))
    return out


def lines(raw):
    return raw.decode("cp932", "replace").split("\r\n")


def paragraphs(text_lines):
    """[(first line's number, last's, first's indent cells, the others', the text)]."""
    out, k = [], 0
    while k < len(text_lines):
        if not text_lines[k].strip("　 "):
            k += 1
            continue
        j = k
        while j + 1 < len(text_lines) and text_lines[j + 1].strip("　 "):
            j += 1
        block = text_lines[k:j + 1]
        ind = [cells(x) - cells(x.lstrip("　 ")) for x in block]
        out.append((k, j, ind[0], ind[1] if len(ind) > 1 else ind[0], "".join(x.lstrip("　 ") for x in block)))
        k = j + 1
    return out


def prog_strings(exe):
    """[(start, end)]: the program's NUL-ended strings with Japanese, in its data (after its code); its
    character tables (the voiced kana's, the characters no line starts with) and its save data's mark
    left out."""
    return [(m.start(), m.end() - 1) for m in PROG_STR.finditer(exe, 0x28000)
            if KANA.search(m.group()[:-1].decode("cp932", "replace")) and m.end() - m.start() > 3
            and not m.group().startswith(TABLES)]


TABLES = ("＊ヴガギ".encode("cp932"), "＊パピ".encode("cp932"), "！、。".encode("cp932"),
          "妖獣戦記SaveData".encode("cp932"))


def unit_names(exe):
    """[(start, end)] of the program's unit table's names (50-byte records, as UNIT.DAT's 48 and two)."""
    out = []
    i = exe.find(b"\x83\x41\x83\x8b\x83\x74\x83\x40\x00", 0x28000)          # アルファ, the first record
    while i > 0 and exe[i] >= 0x81:
        out.append((i, i + exe[i:i + Y.NAME].index(0)))
        i += 50
    return out


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
    for f, b in Y.nca(vol.read(gd + "/SYSDATA.NCA")):
        nm = Y.name(f)
        if nm.endswith(".TXB"):
            for s, e, face, kind in Y.txb(b):
                jp = Y.inv(b[s:e]).decode("cp932", "replace")
                if kind == 6:
                    jp = " ".join(x for x in jp.split("　") if x)
                add("msg", jp.rstrip("　"), "SYSDATA.NCA/%s:%04x" % (nm, s), WIDTH[kind],
                    "the opening's page, centred" if kind == 6 else None)
    for f, b in Y.nca(vol.read(gd + "/ANMSC.NCA")):
        nm = Y.name(f)
        for i, op, s, e in Y.sc(b):
            if s is None:
                continue
            jp = Y.inv(b[s:e]).decode("cp932", "replace")
            if op == 0x24:
                add("scene", jp, "ANMSC.NCA/%s:%04x" % (nm, s), SCENE)
            else:
                add("profile", jp, "ANMSC.NCA/%s:%04x" % (nm, s), PROFILE, "one line of a profile, at a fixed place")
    for n, _e in vol.walk():
        base = n[len(gd) + 1:]
        if n.startswith(gd + "/") and n.endswith(".MSG"):
            for k, line in enumerate(lines(vol.read(n))):
                if line.strip("　 "):
                    add("battle", line, "%s:%d" % (base, k), BATTLE,
                        "a battle line: broken at %d cells, at most %d bytes" % (BATTLE, BATTLE_ROOM))
        elif n.startswith(gd + "/DATA_") and n.endswith(".TXT"):
            for k, j, i0, i1, text in paragraphs(lines(vol.read(n))):
                add("doc", text, "%s:%d-%d" % (base, k, j), DOC - i1, "a data page's paragraph")
    unit = vol.read(gd + "/UNIT.DAT")
    for r in range(0, len(unit), Y.UNIT):
        jp = unit[r:r + Y.NAME].split(b"\0")[0].decode("cp932", "replace")
        if jp:
            add("name", jp, "UNIT.DAT:%04x" % r, NAME_CELLS, "a unit's name: at most 19 bytes")
    for s, e in unit_names(prog):
        add("name", prog[s:e].decode("cp932", "replace"), "%s:%05x" % (cfg["program"], s), NAME_CELLS,
            "a unit's name: at most 19 bytes")
    named = {s for s, _e in unit_names(prog)}
    for s, e in prog_strings(prog):
        if s not in named:
            add("label", prog[s:e].decode("cp932", "replace"), "%s:%05x" % (cfg["program"], s), e - s,
                "a string of the program's: its room in bytes (a letter one, a full-width character two)")
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
    if e["kind"] in ("label", "name", "profile"):
        return pseudo(e["id"], e["max_cells"], 1.0)[:max(2, e["max_cells"])]
    return pseudo(e["id"], cells(e["jp"]))


def _cut(b, room):
    b = b[:room]
    while b and len(b.decode("cp932", "ignore").encode("cp932")) != len(b):
        b = b[:-1]
    return b


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"]
    by_ref, ids, rooms = {}, {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            rooms[r] = e["max_cells"]
            if text:
                by_ref[r] = text
    warn = []

    def put(path, data):
        if data != vol.read(path):
            vol.write(path, data)
    raw = vol.read(gd + "/SYSDATA.NCA")
    new = {}
    for f, b in Y.nca(raw):
        nm = Y.name(f)
        if not nm.endswith(".TXB"):
            continue
        texts = {}
        for s, e, face, kind in Y.txb(b):
            en = by_ref.get("SYSDATA.NCA/%s:%04x" % (nm, s))
            if en is not None:
                texts[s] = [Y.inv(encode(p)) for p in pages(en, WIDTH[kind], kind == 6)]
        if texts:
            new[nm] = Y.txb_build(b, texts)
    put(gd + "/SYSDATA.NCA", Y.nca_build(raw, new))
    raw = vol.read(gd + "/ANMSC.NCA")
    new = {}
    for f, b in Y.nca(raw):
        nm = Y.name(f)
        texts = {}
        for i, op, s, e in Y.sc(b):
            if s is None:
                continue
            ref = "ANMSC.NCA/%s:%04x" % (nm, s)
            en = by_ref.get(ref)
            if en is None:
                continue
            if op == 0x24:
                texts[s] = [Y.inv(encode(p)) for p in pages(en, SCENE)]
            else:
                if cells(en) > PROFILE:
                    warn.append("%s: %d cells, past its line (%d)" % (ids[ref], cells(en), PROFILE))
                texts[s] = [Y.inv(encode(en))]
        if texts:
            new[nm] = Y.sc_build(b, texts)
    put(gd + "/ANMSC.NCA", Y.nca_build(raw, new))
    for n, _e in vol.walk():
        base = n[len(gd) + 1:]
        if n.startswith(gd + "/") and n.endswith(".MSG"):
            ls = lines(vol.read(n))
            out = []
            for k, line in enumerate(ls):
                ref = "%s:%d" % (base, k)
                en = by_ref.get(ref)
                if en is None:
                    out.append(line.encode("cp932"))
                    continue
                b = encode(filled(en, BATTLE))
                if len(b) > BATTLE_ROOM:
                    warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), BATTLE_ROOM))
                    b = _cut(b, BATTLE_ROOM)
                out.append(b)
            put(n, b"\r\n".join(out))
        elif n.startswith(gd + "/DATA_") and n.endswith(".TXT"):
            ls = lines(vol.read(n))
            out, at = [], 0
            for k, j, i0, i1, _t in paragraphs(ls):
                out += [x.encode("cp932") for x in ls[at:k]]
                en = by_ref.get("%s:%d-%d" % (base, k, j))
                if en is None:
                    out += [x.encode("cp932") for x in ls[k:j + 1]]
                else:
                    out += [encode(" " * ind + s) for ind, s in wrap(en, DOC, i0, i1)]
                at = j + 1
            out += [x.encode("cp932") for x in ls[at:]]
            put(n, b"\r\n".join(out))
    unit = bytearray(vol.read(gd + "/UNIT.DAT"))
    for r in range(0, len(unit), Y.UNIT):
        ref = "UNIT.DAT:%04x" % r
        en = by_ref.get(ref)
        if en is not None:
            b = encode(en)
            if len(b) > Y.NAME - 1:
                warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), Y.NAME - 1))
                b = _cut(b, Y.NAME - 1)
            elif cells(en) > rooms[ref]:
                warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
            unit[r:r + Y.NAME] = b.ljust(Y.NAME, b"\0")
    put(gd + "/UNIT.DAT", bytes(unit))
    prog_path = gd + "/" + cfg["program"]
    prog = vol.read(prog_path)
    out = bytearray(prog)
    named = unit_names(prog)
    for s, e in named + [x for x in prog_strings(prog) if x[0] not in {y[0] for y in named}]:
        ref = "%s:%05x" % (cfg["program"], s)
        en = by_ref.get(ref)
        if en is None:
            continue
        room = Y.NAME - 1 if (s, e) in named else e - s
        b = encode(en)
        if len(b) > room:
            warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), room))
            b = _cut(b, room)
        elif (s, e) in named and cells(en) > rooms[ref]:
            warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
        out[s:s + room] = b.ljust(room, b"\0")
    put(prog_path, bytes(out))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
