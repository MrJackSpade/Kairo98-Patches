"""English for K. Hoshino's AVG and ANIME SYSTEM (pc98tl/aas.py: Rookies): strings.json in, a patched image
out.

The program writes its text to the text layer as JIS characters (two cells each).  The patched ANI.EXE
(`patch_program`) also draws letter pairs: two half-width ANK letters in the two cells of one character's
place.  In a script a pair is a word (the first letter + 1, the second + 81h: never a JIS code); in the
program's strings it is pc98tl/illusion_font24.py's pair (a first byte A0h-DFh), which its Shift-JIS
conversion turns into the script's form.

Strings (refs FILE.SCP:place, the text's place in the unpacked script; ANI.EXE:place for the program's):

* "msg": a message.  The window (the script's last "0C" operation) is `max_cells` letters wide (two a
  cell) and three lines high; the program breaks a line at its edge and waits for a key when the
  window is full.  The patcher breaks the English between words, ending a
  line with the patched drawer's new-line word (21h A0h).  {N} is
  the player's name, {Snn} a speaker's name (drawn "【name】" on a line of its own).
* "item": a choice's item (after "05"): one line, `max_cells` its room in letters; past it reported.
* "name": a speaker's name (the program's table), "label": the program's menus and notices: in place,
  `max_cells` their room in letters (a letter a byte); past it cut and reported.
* "console": a notice printed through DOS: in place, plain ASCII.

English is ASCII (pairs); another character is written full-width when Shift-JIS has it, else `?`.
A script may take any length: its jumps and calls are moved, and one past its 64 KB segment is cut
into further files going on with 0E (pc98tl/aas.py `split`).
"""
import json
import os
import re
import struct

from . import aas as A
from . import lz96
from .alice_sys2_tl import sha256
from .illusion_font24 import encode_en
from .text import pseudo

PREFIX = {"msg": "m", "item": "i", "name": "n", "label": "l", "console": "t"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}
DEFAULT_WINDOW = (5, 0x14, 0x22, 0x17)
TOKEN = re.compile(r"\{N\}|\{S\d\d\}")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def jis_to_sjis(j1, j2):
    s1 = (j1 + 1) // 2 + (0x70 if j1 < 0x5F else 0xB0)
    s2 = j2 + (0x1F if j1 % 2 else 0x7E)
    if j1 % 2 and s2 >= 0x7F:
        s2 += 1
    return bytes([s1, s2])


def sjis_to_jis(b):
    s1, s2 = b[0], b[1]
    j1 = (s1 - (0x70 if s1 < 0xA0 else 0xB0)) * 2
    if s2 < 0x9F:
        j1 -= 1
        j2 = s2 - (0x1F if s2 < 0x7F else 0x20)
    else:
        j2 = s2 - 0x7E
    return j1, j2


def show(b):
    out, i = "", 0
    while i + 1 < len(b):
        w0, w1 = b[i], b[i + 1]
        if w0 == 0x80:
            out += "{N}" if w1 == 0 else "{S%02d}" % w1
        else:
            out += jis_to_sjis(w1, w0).decode("cp932", "replace")
        i += 2
    return out


def scripts(vol, cfg):
    gd = cfg["game_dir"] + "/"
    return {n[len(gd):]: n for n, _e in vol.walk() if n.upper().startswith(gd.upper()) and n.upper().endswith(".SCP")}


def texts(d):
    """[(place, bytes, kind, window cells)]: the script's text, "item" for a choice's items."""
    win, items, out = DEFAULT_WINDOW, 0, []
    for a, op, b in A.parse(d):
        if op == 0x0C:
            win = tuple(b[1:5])
        elif op == 0x05:
            items = b[1]
        elif op == A.TEXT:
            out.append((a, b, "item" if items else "msg", win[2] - win[0]))
            if items:
                items -= 1
    return out


PROG_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e\n])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                      rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e\n])*(?=\x00)")
KANA = re.compile(rb"[\x82\x83][\x40-\xfc]|\x81[\x5b\x45]")


def _calls(image, ds, off):
    """The near call targets after each "push/mov offset" naming a DS string (the next call within 40
    bytes)."""
    out = []
    imm = struct.pack("<H", off)
    for op in (b"\x68", b"\xb8", b"\xbe", b"\xbf"):
        i = 0
        while True:
            i = image.find(op + imm, i, ds)
            if i < 0:
                break
            j = image.find(b"\xe8", i + 3, i + 40)
            if j >= 0:
                out.append((j + 3 + struct.unpack_from("<h", image, j + 1)[0]) & 0xFFFF)
            i += 1
    return out


def program_strings(image, ds, names):
    """[(image place, bytes, kind)]: the program's strings in its data segment: the speakers' names
    (`names`: the table's DS place, its records' size and count), the strings passed to its printf
    (the routine its notices ending in a new line go to: "console"), the rest (drawn on the text layer
    two bytes at a time: "label"); a table of ASCII bytes left out."""
    found = []
    lo, step, count = names
    for m in PROG_STR.finditer(image, ds):
        s = m.group()
        if len(s) < 4 or not re.search(rb"[\x81-\x9f\xe0-\xef]", s) or 0x21 <= s[0] < 0x7F:
            continue
        found.append((m.start(), s))
    nl = {}
    for at, s in found:
        if s.endswith(b"\n"):
            for t in _calls(image, ds, at - ds):
                nl[t] = nl.get(t, 0) + 1
    printf = max(nl, key=nl.get) if nl else None
    out = []
    for at, s in found:
        off = at - ds
        if lo <= off < lo + step * count and (off - lo) % step == 0:
            out.append((at, s, "name"))
        elif s.endswith(b"\n") or printf in _calls(image, ds, off):
            out.append((at, s, "console"))
        elif KANA.search(s) and (len(s) - len(s.lstrip(b" "))) % 2 == 0:
            out.append((at, s, "label"))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    merged, order = {}, []

    def add(kind, jp, ref, room, note):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
        order.append(key)
    for f, path in sorted(scripts(vol, cfg).items()):
        d = lz96.unpack(vol.read(path))
        for at, b, kind, cells in texts(d):
            jp = show(b)
            ref = "%s:%04x" % (f, at)
            if kind == "msg":
                add("msg", jp, ref, 2 * cells, "a message: broken between words at %d letters (the window's "
                    "%d cells), three lines a window; {N} the player's name, {Snn} a speaker's" % (2 * cells, cells))
            else:
                add("item", jp, ref, 2 * cells, "a choice's item: one line, its room in letters")
    exe = vol.read(cfg["game_dir"] + "/" + cfg["program"])
    image, ds = _program(exe)
    for at, s, kind in program_strings(image, ds, cfg["names"]):
        jp = s.decode("cp932", "replace")
        add(kind, jp, "%s:%05x" % (cfg["program"], at), cfg["names"][1] - 1 if kind == "name" else len(s),
            {"name": "a speaker's name: in place, its room in letters",
             "label": "a string of the program's (a menu, a notice): in place, its room in letters",
             "console": "a notice printed through DOS: in place, plain ASCII"}[kind])
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


def _program(exe):
    h = struct.unpack_from("<14H", exe, 0)
    base = h[4] * 16
    image = exe[base:]
    entry = h[11] * 16 + h[10]
    if image[entry] != 0xBA:
        raise ValueError("no DGROUP load at the entry point")
    return image, struct.unpack_from("<H", image, entry + 1)[0] * 16


# ---- English

def _units(text):
    """[(kind, value)]: "a" a letter, "j" a full-width character's script word, "t" a name token's."""
    out, pos = [], 0
    for m in list(TOKEN.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        for ch in text[pos:end]:
            for c in SUBST.get(ch, ch):
                if " " <= c <= "~":
                    out.append(("a", c))
                else:
                    try:
                        j1, j2 = sjis_to_jis(c.encode("cp932"))
                        out.append(("j", bytes([j2, j1])))
                    except (UnicodeEncodeError, IndexError):
                        out.append(("a", "?"))
        if m:
            t = m.group()
            out.append(("t", b"\x80\x00" if t == "{N}" else bytes([0x80, int(t[2:4])])))
            pos = m.end()
    return out


def _pairs(letters):
    if len(letters) % 2:
        letters += " "
    return b"".join(bytes([ord(letters[k]) + 1, ord(letters[k + 1]) + 0x81]) for k in range(0, len(letters), 2))


def encode_msg(text, width):
    """The message's script bytes: broken between words at `width` letters, a short line ended by
    NEWLINE; a name token on a line of its own (the program puts one there)."""
    out, line, col = [], [], 0

    def flush(pad):
        nonlocal line, col
        letters = ""
        for u in line:
            if u[0] == "a":
                letters += u[1]
            else:
                if len(letters) % 2:
                    letters += " "
                out.append(_pairs(letters))
                letters = ""
                out.append(u[1])
        if letters:
            out.append(_pairs(letters))
        if pad and col < width:                 # (a full line: the program goes on to the next)
            out.append(NEWLINE)
        line, col = [], 0
    words = re.split(r"( |\n)", text)
    for w in words:
        if w == "":
            continue
        if w == "\n":
            flush(True)
            continue
        us = _units(w)
        if us and us[0][0] == "t" and not col:
            out.append(us[0][1])               # (the name: the program ends the line after it)
            us = us[1:]
            if not us:
                continue
        if w == " ":
            if col and col < width:
                line.append(("a", " "))
                col += 1
            continue
        u = sum(1 if k == "a" else 2 for k, _v in us)
        if col and col + u > width:
            while line and line[-1] == ("a", " "):
                line.pop()
                col -= 1
            flush(True)
        line += us
        col += u
    flush(False)
    b = b"".join(out)
    return b if b else _pairs(" ")


def encode_item(text):
    return encode_msg(text, 999)


def encode_label(text, room):
    b = encode_en("".join(c if " " <= c <= "~" else "?" for c in "".join(SUBST.get(c, c) for c in text)))
    return b[:room & ~1]


# ---- the program

NEWLINE = bytes([0x21, 0xA0])       # (a word no character uses: the patched writer ends the line)
# the text drawer: mov al, [column]; inc byte [column]; ... call writer; ... mov al, [column]; cmp al, [right]
DRAWER = re.compile(rb"\xa0(..)\xfe\x06\1\xb4\x00\x50\xe8..\x83\xc4\x08\x83\x06..\x02\xa0\1\x3a\x06(..)", re.S)

CELL = re.compile(rb"\x55\x8b\xec\x83\xec\x02\x8b\x5e\x08\x8a\x46\x0a\xc0\xe0\x05\xfe\xc0\x88\x46\x0a\x8b\x46\x04"
                  rb"(\xc1\xe0\x02|\xd1\xe0)\x50\x8b\x46\x06\xba(..)\xf7\xea\x59\x03\xc8.{19}\xc4\x1e(..)", re.S)
CONVERT = re.compile(rb"\x55\x8b\xec\x83\xec\x02\x8b\x46\x04\x86\xe0\x02\xe4\x2c\x1f\x78\x04\x3c\x61\x14\xde"
                     rb"\x05\xa1\x1f\x25\x7f\x7f\x89\x46\xfe\x8b\x46\xfe\xc9\xc3")
CELL_SRC = """
        push bp
        mov bp, sp
        push di
        push es
        mov al, byte ptr [bp + 0xa]
        shl al, 5
        inc al
        mov dh, al
        imul di, word ptr [bp + 6], ROW
        mov ax, word ptr [bp + 4]
        shl ax, SHIFT
        add di, ax
        les bx, dword ptr [PTR]
        add di, bx
        mov bx, word ptr [bp + 8]
        cmp bh, 0xa0
        je nl
        cmp bh, 0xa1
        jae pr
        mov al, bh
        sub al, 0x20
        and al, 0x7f
        mov ah, bl
        mov word ptr es:[di], ax
        or al, 0x80
        mov word ptr es:[di + 2], ax
        jmp at
    pr:
        mov al, bl
        dec al
        xor ah, ah
        mov word ptr es:[di], ax
        mov al, bh
        sub al, 0x81
        mov word ptr es:[di + 2], ax
    at:
        mov byte ptr es:[di + 0x2000], dh
        mov byte ptr es:[di + 0x2002], dh
    out:
        pop es
        pop di
        pop bp
        .byte 0xc3
    nl:
        mov al, byte ptr [RIGHT]
        mov byte ptr [COLUMN], al
        jmp out
"""
CONVERT_SRC = """
        push bp
        mov bp, sp
        mov ax, word ptr [bp + 4]
        cmp al, 0xa0
        jb sj
        cmp al, 0xdf
        ja sj
        mov dl, al
        sub dl, 0xa0
        test ah, 0x80
        jz l1
        and ah, 0x7f
        add dl, 0x40
    l1:
        add dl, 0x20
        add ah, 0x81
        mov al, dl
        inc al
        pop bp
        .byte 0xc3
    sj:
        xchg al, ah
        add ah, ah
        sub al, 0x1f
        js s1
        cmp al, 0x61
        adc al, 0xde
    s1:
        add ax, 0x1fa1
        and ax, 0x7f7f
        pop bp
        .byte 0xc3
"""


def patch_program(exe, strings):
    """ANI.EXE with its two text-cell writers and its Shift-JIS conversion rewritten for letter pairs
    (all three written anew in the writers' room, the near calls moved), `strings` {image place: bytes}
    in place."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm
    h = struct.unpack_from("<14H", exe, 0)
    base = h[4] * 16
    out = bytearray(exe)
    image = bytes(exe[base:])
    cells = list(CELL.finditer(image))
    conv = CONVERT.search(image)
    if len(cells) != 2 or not conv:
        raise ValueError("the text-cell writers / the Shift-JIS conversion not found")
    start = cells[0].start()
    end = conv.end()
    if cells[1].start() < start or conv.start() < cells[1].start():
        raise ValueError("the writers and the conversion not laid out as expected")
    dr = DRAWER.search(image)
    if not dr:
        raise ValueError("the text drawer not found")
    column, right = struct.unpack("<H", dr.group(1))[0], struct.unpack("<H", dr.group(2))[0]
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    code, places = bytearray(), {}
    for m in cells:
        src = CELL_SRC.replace("RIGHT", "0x%x" % right).replace("COLUMN", "0x%x" % column).replace("ROW", "0x%x" % struct.unpack("<H", m.group(2))[0]) \
                      .replace("SHIFT", "2" if m.group(1) == b"\xc1\xe0\x02" else "1") \
                      .replace("PTR", "0x%x" % struct.unpack("<H", m.group(3))[0])
        places[m.start()] = start + len(code)
        c, _l = _asm(ks, src, start + len(code), ())
        code += c
    places[conv.start()] = start + len(code)
    c, _l = _asm(ks, CONVERT_SRC, start + len(code), ())
    code += c
    if len(code) > end - start:
        raise ValueError("the new text routines too long")
    code_end = h[11] * 16 if h[11] * 16 > start else len(image)
    moved = 0
    for m in re.finditer(rb"\xe8(..)", image[:start], re.S):
        t = (m.start() + 3 + struct.unpack("<h", m.group(1))[0]) & 0xFFFF
        if t in places and t != places[t]:
            struct.pack_into("<H", out, base + m.start() + 1, (places[t] - (m.start() + 3)) & 0xFFFF)
            moved += 1
    for m in re.finditer(rb"\xe8(..)", image[end:code_end], re.S):
        at = end + m.start()
        t = (at + 3 + struct.unpack("<h", m.group(1))[0]) & 0xFFFF
        if t in places and t != places[t]:
            struct.pack_into("<H", out, base + at + 1, (places[t] - (at + 3)) & 0xFFFF)
            moved += 1
    out[base + start:base + end] = code + bytes(end - start - len(code))
    for at, b in strings.items():
        out[base + at:base + at + len(b)] = b
    return bytes(out)


def _pseudo(e):
    if e["kind"] in ("msg", "item"):
        lead = "".join(TOKEN.findall(e["jp"][:5]))
        return lead + pseudo(e["id"], 2 * len(TOKEN.sub("", e["jp"])))
    return pseudo(e["id"], e["max_cells"], 1.0)[:e["max_cells"]]


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
    names = scripts(vol, cfg)
    for f, path in sorted(names.items()):
        d = lz96.unpack(vol.read(path))
        new = {}
        for at, _b, kind, cells in texts(d):
            ref = "%s:%04x" % (f, at)
            if ref not in by_ref:
                continue
            if kind == "msg":
                new[at] = encode_msg(by_ref[ref], 2 * cells)
            else:
                b = encode_item(by_ref[ref])
                if len(b) > ids[ref]["max_cells"]:
                    warn.append("%s: %d letters, room for %d" % (ids[ref]["id"], len(b), ids[ref]["max_cells"]))
                new[at] = b
        if new:
            stem = f.rsplit(".", 1)[0]
            try:
                parts = A.split(d, new, lambda i: f if i == 0 else "%s%d.SCP" % (stem[:7], i + 1))
            except ValueError as ex:
                raise SystemExit("%s: %s; shorten these strings: %s" % (f, ex, ", ".join(
                    sorted({ids["%s:%04x" % (f, a)]["id"] for a in new}))))
            if len(parts) > 1:
                warn.append("%s: split into %s" % (f, ", ".join(p for p, _d in parts)))
            for p, data in parts:
                if p == f:
                    vol.write(path, lz96.pack(data))
                elif p.upper() in {n.upper() for n in names}:
                    raise SystemExit("%s: its part's name %s is taken" % (f, p))
                else:
                    vol.create(path.rsplit("/", 1)[0] + "/" + p, lz96.pack(data))
    if by_ref:                                  # (no English: the program as it was)
        prog = cfg["game_dir"] + "/" + cfg["program"]
        exe = vol.read(prog)
        image, ds = _program(exe)
        strings = {}
        for at, s, kind in program_strings(image, ds, cfg["names"]):
            ref = "%s:%05x" % (cfg["program"], at)
            if ref not in by_ref:
                continue
            e = ids[ref]
            if kind == "console":
                b = "".join(c if " " <= c <= "~" or c == "\n" else "?" for c in by_ref[ref]).encode("ascii")
                if not b.endswith(b"\n"):
                    b += b"\n"
            else:
                b = encode_label(by_ref[ref], 999)
            room = cfg["names"][1] - 1 if kind == "name" else len(s)
            if len(b) > room:
                warn.append("%s: %d bytes, room for %d (cut)" % (e["id"], len(b), room))
                b = b[:room & ~1] if kind != "console" else b[:room - 1] + b"\n"
            strings[at] = b.ljust(room, b"\0")
        vol.write(prog, patch_program(exe, strings))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
