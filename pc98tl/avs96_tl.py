"""English for Mink's AVS96 engine (pc98tl/avs96.py: Mashou no Kao): strings.json in, a patched image out.

The program draws only its own 24-dot font (the game's kana and kanji).  The patched program (`patch_exe`)
also draws English as letter pairs, as in pc98tl/illusion_font24.py: two letters in one cell (a first byte
A0h-DFh, never a Shift-JIS lead), shown as two kanji-ROM ANK letters 12 dots apart.  A cell is two
half-width letters.

Strings (refs FILE:place, the place of the string's operation in the unpacked script; an item adds :n,
its number in the menu; AVS96.EXE:place for the program's own):

* "msg": a message.  The window is `cols` cells (`2 * cols` letters) by two rows; the program breaks a
  line at the window's edge and waits for a click when the window is full.  The patcher breaks the English
  between words, padding a line to the window's edge.  {NAME} is the hero's name (＠００; counted as
  `name_cells` cells); `\\n` forces a new line.  `max_cells` is the letters a line holds.
* "item": a menu's item (system function 4): one line, `max_cells` its letters; past it reported.
* "name": a character's name (the hero's, as the game starts): `max_cells` its letters (the program
  keeps 20 bytes); past it cut and reported.
* "label": a string of the program's (its menu, the save slots): in place, `max_cells` its room in
  letters; past it cut and reported.

English is ASCII; another character is written full-width (a cell) when Shift-JIS has it, else `?`.
A script may take any length: its jumps and calls are moved, and one past its 64 KB segment is split
into further files (pc98tl/avs96.py `split`).
"""
import json
import os
import re
import struct

from . import avs96 as A
from . import exepack
from .alice_sys2_tl import sha256
from .illusion_font24 import encode_en
from .text import pseudo

PREFIX = {"msg": "m", "item": "i", "name": "n", "label": "l"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}
NAME = "＠００"
NAME_TOKEN = "{NAME}"
NAME_ROOM = 20
LABEL = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc])+\x00")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def show(b):
    return b.decode("cp932", "replace").replace(NAME, NAME_TOKEN)


def cells(text):
    return sum(1 if ord(c) < 0x80 else 2 for c in text.replace(NAME_TOKEN, ""))


def scripts(vol, cfg):
    gd = cfg["game_dir"]
    out = {}
    for n, _e in vol.walk():
        f = n[len(gd) + 1:]
        if n.upper().startswith(gd.upper() + "/") and f.upper().endswith(".BIN") and f.upper() not in cfg["unused"]:
            raw = vol.read(n)
            out[f.upper()] = (raw, raw if f.upper() == cfg["first"].upper() else A.unpack(raw))
    return out


def labels(img, cfg):
    """[(image place, bytes without the NUL)]: the program's strings in its menu's area."""
    lo, hi = cfg["labels"]
    return [(m.start(), m.group()[:-1]) for m in LABEL.finditer(img, lo, hi)]


# ---- English as letter pairs

def _units(text):
    """[(kind, value)]: "a" an ASCII letter, "j" a full-width character's bytes, "n" the name."""
    out, i = [], 0
    while i < len(text):
        if text.startswith(NAME_TOKEN, i):
            out.append(("n", NAME.encode("cp932")))
            i += len(NAME_TOKEN)
            continue
        for c in SUBST.get(text[i], text[i]):
            if " " <= c <= "~":
                out.append(("a", c))
            else:
                try:
                    out.append(("j", c.encode("cp932")))
                except UnicodeEncodeError:
                    out.append(("a", "?"))
        i += 1
    return out


def _width(unit, pos, name_cells):
    """(letters it takes from `pos`, with the space that puts a full-width one on a cell's start)."""
    kind, _v = unit
    if kind == "a":
        return 1
    return pos % 2 + (2 * name_cells if kind == "n" else 2)


def lay_out(text, width=None, name_cells=5):
    """The units in lines: a line broken between words at `width` letters (None: one line) and padded to
    it; a full-width unit put on a cell's start.  [(kind, value)] with the padding as spaces."""
    out, pos = [], 0

    def put(u):
        nonlocal pos
        if u[0] != "a" and pos % 2:
            out.append(("a", " "))
            pos += 1
        out.append(u)
        pos += 1 if u[0] == "a" else _width(u, pos, name_cells)

    def pad():
        nonlocal pos
        while pos % width:
            out.append(("a", " "))
            pos += 1
        pos = 0
    for n, para in enumerate(text.split("\n")):
        if n:
            pad()
        for m, word in enumerate(para.split(" ")):
            us = _units(word)
            w, p = 0, pos + (1 if m else 0)
            for u in us:
                d = _width(u, p, name_cells)
                w, p = w + d, p + d
            if width and pos and pos + (1 if m else 0) + w > width:
                pad()
            elif m:
                put(("a", " "))
            for u in us:
                put(u)
    return out


def encode(units):
    """The units' bytes: ASCII runs as letter pairs (an odd run ends with a space)."""
    out, run = bytearray(), []
    for kind, v in units + [("end", b"")]:
        if kind == "a":
            run.append(v)
            continue
        if run:
            out += encode_en("".join(run))
            run = []
        out += v
    return bytes(out)


def letters(units):
    return sum(1 if k == "a" else len(v) for k, v in units)


# ---- extract

def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    img = _image(src)
    vol = img.volumes[0]
    merged, order = {}, []

    def add(kind, jp, ref, room, note):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
        order.append(key)
    line = 2 * cfg["cols"]
    for f, (_raw, d) in sorted(scripts(vol, cfg).items()):
        ops = A.parse(d)
        count = {}
        for k, kind, _at, s in A.strings(ops):
            if not re.search(rb"[\x81-\x9f\xe0-\xef]", s):
                continue
            jp = show(s)
            ref = "%s:%04x" % (f, ops[k][0])
            if kind == "msg":
                add("msg", jp, ref, line, "a message: broken between words at %d letters (the window's "
                    "%d cells), paged by the program; {NAME} the hero's name" % (line, cfg["cols"]))
            elif kind == "item":
                count[k] = count.get(k, 0) + 1
                add("item", jp, "%s:%d" % (ref, count[k]), cfg["item_letters"],
                    "a menu's item: one line, its room in letters")
            else:
                add("name", jp, ref, NAME_ROOM, "a character's name: the program keeps %d letters" % NAME_ROOM)
    exe = exepack.unpack(vol.read(cfg["game_dir"] + "/" + cfg["program"]))
    image = exe[struct.unpack_from("<H", exe, 8)[0] * 16:]
    for at, s in labels(image, cfg):
        add("label", show(s), "%s:%05x" % (cfg["program"], at), len(s),
            "a string of the program's (its menu, a save slot): in place, its room in letters")
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


# ---- the program

HOOK = """
    pair:
        cmp al, 0xa0
        jb orig
        cmp al, 0xdf
        ja orig
        pusha
        push es
        mov dl, al
        mov dh, ah
        sub dl, 0xa0
        test dh, 0x80
        jz lo
        and dh, 0x7f
        add dl, 0x60
        jmp go
    lo:
        add dl, 0x20
    go:
        push ds
        pop es
        cld
        mov di, GLYPH
        mov cx, 36
        xor ax, ax
        rep stosw
        mov bl, dl
        mov di, GLYPH + 12
        CALLN ank
        mov bl, dh
        mov di, GLYPH + 13
        CALLN ank
        mov si, GLYPH + 12
        mov cx, 16
    sh:
        mov al, byte ptr [si]
        mov ah, byte ptr [si + 1]
        mov bl, al
        shr bl, 2
        mov byte ptr [si], bl
        mov bl, al
        shl bl, 6
        mov bh, ah
        shr bh, 6
        or bl, bh
        mov byte ptr [si + 1], bl
        shl ah, 2
        mov byte ptr [si + 2], ah
        add si, 3
        loop sh
        mov si, GLYPH
        mov di, COPY
        mov cx, 36
        rep movsw
        pop es
        popa
        push bp
        mov bp, sp
        add word ptr [bp + 2], 3
        pop bp
        .byte 0xc3
    orig:
        .byte 0xe9, 0, 0
    ank:
        xor al, al
        out 0xa1, al
        mov al, bl
        out 0xa3, al
        xor cx, cx
    a1:
        mov al, cl
        out 0xa5, al
        in al, 0xa9
        mov byte ptr [di], al
        add di, 3
        inc cx
        cmp cx, 16
        jb a1
        .byte 0xc3
"""
# the glyph lookup (push es; mov bx, ds; mov es, bx; mov di, table; mov cx, [count]; cld; repne scasw)
LOOKUP_SIG = re.compile(rb"\x06\x8c\xdb\x8e\xc3\xbf..\x8b\x0e..\xfc\xf2\xaf", re.S)
# the glyph fetch: ... mov si, GLYPH; mov di, COPY; mov cx, 24h; rep movsw
FETCH_END = re.compile(rb"\xbe(..)\xbf(..)\xb9\x24\x00\xf3\xa5\x07\xc3", re.S)


def patch_exe(orig, cfg):
    """AVS96.EXE (EXEPACK) with its glyph lookup's callers sent through the pair drawer: each "call
    lookup; call fetch" gets "call pair", which draws a pair into the glyph buffer and returns past the
    fetch (else goes on to the lookup).  The code goes into the zero-filled bytes before the entry point."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm
    plain = exepack.unpack(orig)
    base = struct.unpack_from("<H", plain, 8)[0] * 16
    image = bytearray(plain[base:])
    lk = LOOKUP_SIG.search(image, 0, 0x10000)
    fe = FETCH_END.search(image, 0, 0x10000)
    if not lk or not fe:
        raise ValueError("glyph lookup / fetch not found")
    lookup = lk.start()
    glyph, copy = struct.unpack("<HH", fe.group(1) + fe.group(2))
    fetch = image.rfind(b"\x06\x1e", 0, fe.start())          # (push es; push ds: the fetch's start)
    sites = []
    for at in range(0, 0x10000 - 6):
        if image[at] == 0xE8 and image[at + 3] == 0xE8 and \
                (at + 3 + struct.unpack_from("<h", image, at + 1)[0]) & 0xFFFF == lookup and \
                (at + 6 + struct.unpack_from("<h", image, at + 4)[0]) & 0xFFFF == fetch:
            sites.append(at)
    if not sites:
        raise ValueError("glyph lookup callers not found")
    entry = struct.unpack_from("<H", plain, 20)[0]
    cave = entry - 0x100
    if image[cave:entry] != bytes(0x100):
        raise ValueError("no free bytes before the entry point")
    src = HOOK.replace("GLYPH", "0x%x" % glyph).replace("COPY", "0x%x" % copy)
    code, labs = _asm(Ks(KS_ARCH_X86, KS_MODE_16), src, cave, ("pair", "orig"))
    code = bytearray(code)                      # (keystone's 16-bit jmp and ret carry a 32-bit prefix)
    at = labs["orig"] - cave
    code[at + 1:at + 3] = struct.pack("<H", (lookup - (labs["orig"] + 3)) & 0xFFFF)
    if len(code) > 0x100:
        raise ValueError("pair drawer too long")
    image[cave:cave + len(code)] = code
    for at in sites:
        image[at + 1:at + 3] = struct.pack("<H", (cave - (at + 3)) & 0xFFFF)
    return image, len(sites)


# ---- patch

def _pseudo(e, name_cells):
    if e["kind"] == "msg":
        return pseudo(e["id"], cells(e["jp"]))
    return pseudo(e["id"], e["max_cells"], 1.0)[:e["max_cells"]]


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"]
    width, name_cells = 2 * cfg["cols"], cfg["name_cells"]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e, name_cells) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []

    def enc(e, text):
        if e["kind"] == "msg":
            return encode(lay_out(text, width, name_cells))
        units = lay_out(text, None, name_cells)
        if letters(units) > e["max_cells"]:
            warn.append("%s: %d letters, room for %d" % (e["id"], letters(units), e["max_cells"]))
        b = encode(units)
        if e["kind"] in ("name", "label") and len(b) > e["max_cells"]:
            b = b[:e["max_cells"] & ~1]
        return b
    for f, (raw, d) in sorted(scripts(vol, cfg).items()):
        ops = A.parse(d)
        new, count = {}, {}
        for k, kind, at, _s in A.strings(ops):
            ref = "%s:%04x" % (f, ops[k][0])
            if kind == "item":
                count[k] = count.get(k, 0) + 1
                ref = "%s:%d" % (ref, count[k])
            if ref not in by_ref:
                continue
            new.setdefault(k, {})[at] = enc(ids[ref], by_ref[ref])
        if not new:
            continue
        changed = {k: A._with(ops[k][2], v) for k, v in new.items()}
        stem = f.rsplit(".", 1)[0]
        try:
            parts = A.build(f, ops, changed, cfg["var"], lambda i: f if i == 0 else "%s%s.BIN" % (stem, chr(64 + i)))
        except ValueError as ex:
            raise SystemExit("%s; shorten its strings" % ex)
        if len(parts) > 1:
            warn.append("%s: split into %s" % (f, ", ".join(p for p, _d in parts)))
        for p, data in parts:
            out = data if p.upper() == cfg["first"].upper() else A.pack(data)
            if len(out) > A.PACKED_LIMIT:
                raise SystemExit("%s: %d bytes packed, past its segment; shorten its strings" % (p, len(out)))
            path = gd + "/" + p
            if p == f:
                vol.write(path, out)
            else:
                vol.create(path, out)
    prog_path = gd + "/" + cfg["program"]
    orig = vol.read(prog_path)
    nsites = 0
    if by_ref:                                  # (no English: the program as it was)
        image, nsites = patch_exe(orig, cfg)
        for at, s in labels(bytes(image), cfg):
            ref = "%s:%05x" % (cfg["program"], at)
            if ref in by_ref:
                b = enc(ids[ref], by_ref[ref])
                image[at:at + len(s)] = b.ljust(len(s), b"\0")
        vol.write(prog_path, exepack.pack(orig, bytes(image)))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated; %d text drawers hooked)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), nsites))
