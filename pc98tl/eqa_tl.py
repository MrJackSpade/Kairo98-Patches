"""Strings and English for O. Tomioka's EQAP32 engine (EQAP32.EXE, a DOS/4GW program: Love Escalator).

The scripts (pc98tl/eqa.py) are in the LOVE.EAR archive (pc98tl/ear.py).  Strings (refs FILE.EQA:place,
the operation's place in the script; an item's FILE.EQA:place:n; EQAP32.EXE:address for the program's):

* "msg": a message (op 00), drawn in the window (the script's last op 01; at a script's start the
  usual one, game.json "window": its column, row, width in cells and rows).  `max_cells` is its width
  in letters (a letter a cell, a full-width character two).  The program breaks a line at the window's
  edge itself; the patcher breaks the English between words (ending a shorter line with 81), and when
  the window is full ends the message there and goes on in a further one after a call of the routine
  the script calls after it (its click and cleared window; 80 84 where a script has none).
* "item": a menu's item (ops 0F, 10): one line, `max_cells` its room in letters (the menu's item
  width); past it reported.
* "name": a speaker's label or the hero's name, "slot": another string, put into a 16-byte slot by
  op 2D (a longer one runs on into the next slots): `max_cells` its room in bytes (the slots to the
  next one the script sets, or as many as the Japanese takes); past it cut and reported.
* "notice": one of the program's disk-error notices: in place, `max_cells` its room in bytes; past
  it cut and reported.

Tokens: {Xnn} a control byte: 80 wait for a click, 82 / 83 draw slowly / at once, 84 clear the window,
90-CF the string in slot nn - 90 (90 the hero's family name, 92 his given name, 94 his label, 96 on the
speakers' labels); "\\n" a new line (81).

The text is the text layer's code (a JIS character less 2020h, first byte first, two cells).  The
patched program also draws letter pairs: a word whose second byte is 80h or more is two ANK letters,
the first byte and the second less 80h, one cell each (the cell writer at 10720h rewritten).
"""
import json
import os
import re
import struct

from . import ear
from . import eqa as Q
from . import le as L
from .aas_tl import jis_to_sjis, sjis_to_jis
from .alice_sys2_tl import sha256
from .disk import DiskImage
from .text import pseudo

PREFIX = {"msg": "m", "item": "i", "name": "n", "slot": "s", "notice": "e"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}
TOKEN = re.compile(r"\{X([0-9A-F]{2})\}")
WAIT, NEWLINE, CLEAR = 0x80, 0x81, 0x84
SLOTS = 0x40
NAME_CELLS = {0x00: 16, 0x02: 16, 0x04: 20}  # (the name-entry screen: eight characters a name)
CELL_SIG = re.compile(re.escape(bytes.fromhex("668903") + bytes([0x0C, 0x80]) + bytes.fromhex("66894302"))
                      + rb"\x89\x8b\x00\x20\x00\x00")
KANA_TABLE = re.compile(rb"\x66\x8b\x0c\x4d(....)", re.S)
PAIR_SRC = """
    test ah, ah
    js pair
    mov word ptr [ebx], ax
    or al, 0x80
    mov word ptr [ebx + 2], ax
    ret
pair:
    push eax
    movzx eax, ah
    and al, 0x7f
    mov word ptr [ebx + 2], ax
    mov eax, dword ptr [esp]
    movzx eax, al
    mov word ptr [ebx], ax
    pop eax
    ret
"""


def show(b):
    """The text as it looks: full-width characters, a letter pair's two letters, \\n, {Xnn}."""
    out, i = "", 0
    while i < len(b):
        c = b[i]
        if c >= 0x80:
            out += "\n" if c == NEWLINE else "{X%02X}" % c
            i += 1
            continue
        c2 = b[i + 1]
        if c2 >= 0x80:
            out += chr(c) + chr(c2 & 0x7F)
        else:
            out += jis_to_sjis(c + 0x20, c2).decode("cp932", "replace")
        i += 2
    return out


def _vol(src):
    return DiskImage(src).volumes[0]


def _scripts(files):
    return [(n, d) for n, d in files if n.upper().endswith(".EQA")]


def _slot_rooms(ops):
    used = sorted({b[1] for _a, op, b in ops if op == 0x2D})
    rooms = {}
    for a, op, b in ops:
        if op != 0x2D:
            continue
        n = b[1]
        nxt = next((u for u in used if u > n), SLOTS)
        jp = len(b) - 3 + 1
        room = max(16 * (nxt - n), (jp + 15) // 16 * 16)
        rooms[a] = min(room, 16 * (SLOTS - n)) - 1
    return rooms


def texts(d, window):
    """[(op place, op, offset, bytes, kind, room, window)]: the script's strings."""
    ops = Q.parse(d)
    rooms = _slot_rooms(ops)
    out = []
    for a, op, b in ops:
        if op == 0x01:
            window = (b[1], b[2], b[3], b[4])
        for at, s, kind in Q.strings(op, b):
            if kind == "msg":
                out.append((a, op, at, s, "msg", window[2], window))
            elif kind == "item":
                out.append((a, op, at, s, "item", b[5], window))
            else:
                out.append((a, op, at, s, "name" if b[1] < 0x30 else "slot", rooms[a], b[1]))
    return out


def _data(exe):
    le = L.load(exe)
    return le, bytes(L.image(le)[1]), le["objects"][1]["base"]


def notices(exe):
    """[(address, bytes)]: the program's notices (text-layer strings ending in 80, a NUL after)."""
    le, data, base = _data(exe)
    code = bytes(L.image(le)[0])
    skip = set()
    for m in KANA_TABLE.finditer(code):
        t = int.from_bytes(m.group(1), "little")
        skip.add(t)
    out = []
    for m in re.finditer(rb"(?:[\x01-\x54][\x21-\x7e]){4,}\x80\x00", data):
        at = base + m.start()
        if any(t <= at < t + 0x400 for t in skip):
            continue
        s = m.group()[:-1]
        if any(s[k] in (0x04, 0x05) for k in range(0, len(s) - 1, 2)):
            out.append((at, s))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _vol(src)
    gd = cfg["game_dir"] + "/"
    files = ear.read(vol.read(gd + cfg["archive"]))
    merged, order = {}, []

    def add(kind, jp, ref, room, note):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
        order.append(key)
    for name, d in _scripts(files):
        count = {}
        for a, op, at, s, kind, room, extra in texts(d, tuple(cfg["window"])):
            jp = show(s)
            ref = "%s:%04x" % (name, a)
            if kind == "msg":
                add("msg", jp, ref, room, "a message: the window %d cells (letters) by %d lines; broken "
                    "between words, a click and a new page when the window is full" % (room, extra[3]))
            elif kind == "item":
                count[a] = count.get(a, 0) + 1
                add("item", jp, "%s:%d" % (ref, count[a]), room, "a menu's item: one line, its room in letters")
            elif kind == "name":
                add("name", jp, ref, room, "slot %02X (a speaker's label, {X%02X} in messages; the hero's "
                    "name): its room in bytes (a letter a byte)" % (extra, 0x90 + extra))
            else:
                add("slot", jp, ref, room, "slot %02X ({X%02X} in messages): its room in bytes (a letter "
                    "a byte)" % (extra, 0x90 + extra))
    exe = vol.read(gd + cfg["program"])
    for at, s in notices(exe):
        add("notice", show(s), "%s:%05x" % (cfg["program"], at), len(s),
            "a disk-error notice of the program's: in place, its room in bytes")
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


# ---- English

def _units(text, slotw):
    """[(kind, bytes, cells)]: "a" a letter, "j" a full-width character, "t" a control, "n" a new line."""
    out, pos = [], 0
    for m in list(TOKEN.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        for ch in text[pos:end]:
            if ch == "\n":
                out.append(("n", b"", 0))
                continue
            for c in SUBST.get(ch, ch):
                if " " <= c <= "~":
                    out.append(("a", c, 1))
                else:
                    try:
                        j1, j2 = sjis_to_jis(c.encode("cp932"))
                        out.append(("j", bytes([j1 - 0x20, j2]), 2))
                    except (UnicodeEncodeError, IndexError, ValueError):
                        out.append(("a", "?", 1))
        if m:
            c = int(m.group(1), 16)
            out.append(("t", bytes([c]), slotw.get(c - 0x90, 16) if c >= 0x90 else 0))
            pos = m.end()
    return out


def _line(units):
    """The line's chunks (letter pairs, words, controls) and its width in cells."""
    chunks, letters, col = [], "", 0

    def pairs():
        nonlocal letters, col
        if len(letters) % 2:
            letters += " "
        for k in range(0, len(letters), 2):
            chunks.append(bytes([ord(letters[k]), ord(letters[k + 1]) | 0x80]))
        col += len(letters)
        letters = ""
    for kind, v, cells in units:
        if kind == "a":
            letters += v
            continue
        pairs()
        chunks.append(v)
        col += cells
    pairs()
    return chunks, col


def _cells(units):
    return _line(units)[1]


def encode_msg(text, width, rows, slotw):
    """The message's pages, each a list of chunks: broken between words at `width` cells, a shorter
    line ended by 81, a new page when the window's `rows` are full."""
    pages, line, row = [[]], [], 0

    def limit(units):
        # (the last line: room for the click's cursor; a line with a slot's string, whose width is
        # known only when it is drawn: never full, so that its new line is always written)
        if row == rows - 1 or any(k == "t" and c for k, _v, c in units):
            return width - 2
        return width

    def flush(more):
        nonlocal line, row
        while line and line[-1] == ("a", " ", 1):
            line.pop()
        chunks, col = _line(line)
        pages[-1].extend(chunks)
        line = []
        if not more:
            return
        row += 1
        if row >= rows:
            pages.append([])
            row = 0
        elif col < width:
            pages[-1].append(bytes([NEWLINE]))
    words = []
    for part in re.split(r"(\{X84\})", text):
        words += [part] if part == "{X84}" else re.split(r"( |\n)", part)
    for w in words:
        if w == "":
            continue
        if w == "\n":
            flush(True)
            continue
        if w == "{X84}":                        # (the window cleared: a new page)
            flush(False)
            pages[-1].append(bytes([CLEAR]))
            row = 0
            continue
        us = _units(w, slotw)
        if w == " ":
            if line and _cells(line) < limit(line):
                line.append(("a", " ", 1))
            continue
        while us:
            if line and _cells(line + us) > limit(line + us):
                flush(True)
            take = us
            if _cells(take) > limit(line + take):     # (a word longer than a line: cut where it fills it)
                take = []
                for u in us:
                    if _cells(take + [u]) > limit(line + take + [u]):
                        break
                    take.append(u)
                take = take or us[:1]
            line += take
            us = us[len(take):]
            if us:
                flush(True)
    flush(False)
    return [p for p in pages if p] or [[bytes([0x20, 0xA0])]]


def joined(pages):
    """The pages as one string's chunks, a click and a cleared window between them (80 84)."""
    out = []
    for n, p in enumerate(pages):
        out += ([bytes([WAIT]), bytes([CLEAR])] if n else []) + p
    return out


def encode_line(text, slotw):
    """An item's or a slot's chunks: one line, no breaks."""
    return _line(_units(text.replace("\n", " "), slotw))[0] or [bytes([0x20, 0xA0])]


def _waits(ops):
    """{message's place: the routine it is followed by (the click and the cleared window: 15 after the
    message, else the one most messages of the script are followed by), or None}."""
    after = {}
    for k, (a, op, b) in enumerate(ops):
        if op == 0x00:
            nxt = ops[k + 1] if k + 1 < len(ops) else None
            after[a] = struct.unpack_from("<H", nxt[2], 1)[0] if nxt and nxt[1] == 0x15 else None
    seen = [t for t in after.values() if t is not None]
    usual = max(set(seen), key=seen.count) if seen else None
    return {a: (t if t is not None else usual) for a, t in after.items()}


def _cut(chunks, room):
    """The chunks within `room` bytes, the controls they end with kept; and their full length."""
    trail = []
    while chunks and len(chunks[-1]) == 1 and len(trail) < 2:
        trail.insert(0, chunks[-1])
        chunks = chunks[:-1]
    room -= sum(len(c) for c in trail)
    out, n = [], 0
    for c in chunks:
        if n + len(c) > room:
            break
        out.append(c)
        n += len(c)
    return b"".join(out + trail), sum(len(c) for c in chunks + trail)


# ---- the program

def patch_program(exe, notice_bytes):
    """The program with the pair drawer (and the notices in place: {address: bytes})."""
    import keystone
    le = L.load(exe)
    out = bytearray(exe)
    code = le["objects"][0]
    hits = [m.start() for m in CELL_SIG.finditer(bytes(code["data"]))]
    if len(hits) != 1:
        raise ValueError("the text layer's cell writer: %d matches" % len(hits))
    site = hits[0]
    cave = (code["size"] + 15) & ~15
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
    body = bytes(ks.asm(PAIR_SRC, code["base"] + cave)[0])
    if any(code["data"][cave:cave + len(body)]):
        raise ValueError("no room after the code object")
    rel = (cave - (site + 5)) & 0xFFFFFFFF
    L.poke(out, le, 0, site, bytes([0xE8]) + rel.to_bytes(4, "little") + b"\x90" * 4)
    L.poke(out, le, 0, cave, body)
    L.set_size(out, le, 0, cave + len(body))
    base = le["objects"][1]["base"]
    for at, b in notice_bytes.items():
        L.poke(out, le, 1, at - base, b)
    return bytes(out)


# ---- the patch

def _pseudo(e):
    jp = e["jp"]
    lead = re.match(r"(?:\{X[0-9A-F]{2}\})*", jp).group()
    body = TOKEN.sub("", jp)
    if e["kind"] == "msg":
        return lead + pseudo(e["id"], 2 * len(body))
    if e["kind"] in ("name", "slot"):
        tail = re.search(r"(?:\{X[0-9A-F]{2}\})*$", jp).group()
        return lead + pseudo(e["id"], 2 * len(body)) + tail
    return pseudo(e["id"], 2 * len(body))


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"] + "/"
    files = ear.read(vol.read(gd + cfg["archive"]))
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    found = [(name, d, texts(d, tuple(cfg["window"]))) for name, d in _scripts(files)]
    slotw = dict(NAME_CELLS)                    # (a slot's widest string, in cells)
    slot_bytes = {}
    for name, d, ts in found:
        for a, op, at, s, kind, room, extra in ts:
            if kind not in ("name", "slot"):
                continue
            ref = "%s:%04x" % (name, a)
            if ref in by_ref:
                b, full = _cut(encode_line(by_ref[ref], {}), room)
                if full > room:
                    warn.append("%s: %d bytes, room for %d (cut)" % (ids[ref]["id"], full, room))
                slot_bytes[ref] = b
                cells = _cells(_units(show(b), {}))
            else:
                cells = _cells(_units(show(s), {}))
            slotw[extra] = max(slotw.get(extra, 0), cells)
    out_files = {n: d for n, d in files}
    for name, d, ts in found:
        new, whole = {}, {}
        count = {}
        listed = Q.parse(d)
        ops = {a: (op, b) for a, op, b in listed}
        wait = _waits(listed)
        for a, op, at, s, kind, room, extra in ts:
            ref = "%s:%04x" % (name, a)
            if kind == "item":
                count[a] = count.get(a, 0) + 1
                ref = "%s:%d" % (ref, count[a])
            if ref not in by_ref:
                continue
            if kind == "msg":
                pages = encode_msg(by_ref[ref], room, extra[3], slotw)
                if len(pages) > 1 and wait.get(a) is not None:
                    call = b"\x15" + struct.pack("<H", wait[a])
                    whole[a] = call.join(b"\x00" + b"".join(p) + b"\x00" for p in pages)
                    continue
                b = b"".join(joined(pages))
            elif kind == "item":
                b = b"".join(encode_line(by_ref[ref], slotw))
                cells = _cells(_units(show(b), slotw))
                if cells > room:
                    warn.append("%s: %d letters, room for %d" % (ids[ref]["id"], cells, room))
            else:
                b = slot_bytes[ref]
            new.setdefault(a, {})[at] = b
        if not new and not whole:
            continue
        changed = {a: Q.with_strings(ops[a][0], ops[a][1], v) for a, v in new.items()}
        changed.update(whole)
        stem = name.rsplit(".", 1)[0]
        try:
            parts = Q.split(d, changed, lambda i: name if i == 0 else "%s%d.EQA" % (stem[:7], i + 1),
                            var=cfg["split_var"])
        except ValueError as ex:
            raise SystemExit("%s: %s; shorten these strings: %s" % (name, ex, ", ".join(
                sorted({ids[r]["id"] for r in ids if r.startswith(name + ":")}))))
        if len(parts) > 1:
            warn.append("%s: split into %s" % (name, ", ".join(p for p, _d in parts)))
        for p, data in parts:
            if p != name and p in out_files:
                raise SystemExit("%s: its part's name %s is taken" % (name, p))
            out_files[p] = data
    if by_ref:                                  # (no English: the archive and the program as they were)
        vol.write(gd + cfg["archive"], ear.write(list(out_files.items())))
        exe = vol.read(gd + cfg["program"])
        nb = {}
        for at, s in notices(exe):
            ref = "%s:%05x" % (cfg["program"], at)
            if ref not in by_ref:
                continue
            b, full = _cut(joined(encode_msg(by_ref[ref], 60, 4, slotw)), len(s))
            if full > len(s):
                warn.append("%s: %d bytes, room for %d (cut)" % (ids[ref]["id"], full, len(s)))
            nb[at] = b.ljust(len(s), b"\0")
        vol.write(gd + cfg["program"], patch_program(exe, nb))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
