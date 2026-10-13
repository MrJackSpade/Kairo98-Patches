"""English for MBS Truse's MAPL system (pc98tl/mapl.py: Doop): strings.json in, a patched image out.

The program draws only Shift-JIS (16-dot kanji-ROM glyphs).  The patched MAPL.EXE (`patch_program`)
also draws English as letter pairs, as pc98tl/illusion_font24.py does: two letters in one cell (a first
byte A0h-DFh, marked a lead byte in the program's character table), shown as two kanji-ROM ANK letters
side by side.  A cell is two half-width letters.

Strings (refs FILE.MPX:place, the string's place in the scene's text):

* "msg": a message.  The window is 36 cells (72 letters) by four lines; the program breaks a line at
  its edge (mid-word) and waits for a click when the window is full.  The patcher breaks the English
  between words with "%N", a line after a "【name】" indented by the name's width as the program does.
  `max_cells` is the letters a line holds.  "%" commands ("%K", "%N", "%GF,file;" ...) are kept.
* "command": a menu's command (a place, a person, an action: the menu's items).  One line,
  `max_cells` its room in letters; past it reported.

English is ASCII (pairs); another character is written full-width (a cell) when Shift-JIS has it,
else `?`.  A scene's text may take 65520 bytes; a longer build is refused and names its strings.
"""
import json
import os
import re
import struct

from . import lzexe
from . import mapl as M
from . import mapl_op as OP
from .alice_sys2_tl import sha256
from .illusion_font24 import encode_en
from .text import pseudo

PREFIX = {"msg": "m", "command": "c", "label": "l", "dos": "d", "subtitle": "o", "opening": "p",
          "console": "t"}
KIND = {0x01: "command", 0x03: "command"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}
CMD = re.compile(r"%(?:[Gg][A-Za-z]|[A-Za-z])(?:,[^;]*;|\d+;)?")
NEWLINE = ("K", "N", "R")
JAPANESE = re.compile(r"[^\x00-\x7f]")
LINE = 72


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def show(b):
    return b.decode("cp932", "replace")


def scenes(vol, cfg):
    gd = cfg["game_dir"]
    return {n[len(gd) + 1:]: n for n, _e in vol.walk()
            if n.upper().startswith(gd.upper() + "/") and n.upper().endswith(".MPX")}


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    store = int(cfg["store"], 16)
    merged, order = {}, []
    for f, path in sorted(scenes(vol, cfg).items()):
        for at, s, op in M.strings(vol.read(path), store):
            jp = show(s)
            if not JAPANESE.search(CMD.sub("", jp)):
                continue
            kind = KIND.get(op, "msg")
            room = LINE if kind == "msg" else cfg["rooms"][kind]
            key = (kind, jp)
            ref = "%s:%04x" % (f, at)
            if key in merged:
                merged[key]["refs"].append(ref)
                continue
            note = {"msg": "a message: broken between words at %d letters (36 cells); %%-commands kept" % LINE,
                    "command": "a menu's command: one line, its room in letters"}[kind]
            merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
            order.append(key)

    def add(kind, jp, ref, room, note):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
        order.append(key)
    gd = cfg["game_dir"] + "/"
    for at, s, kind in program_strings(lzexe.unpack(vol.read(gd + cfg["program"]))):
        add(kind, show(s), "%s:%05x" % (cfg["program"], at), len(s),
            {"label": "a string of the program's (a notice, an error): in place, its room in letters; "
                      "%s and %%n kept",
             "dos": "a notice the program prints through DOS: in place, plain ASCII, its room in bytes"}[kind])
    if cfg.get("opening"):
        exe = vol.read(gd + cfg["opening"])
        for off, subs in OP.subtitles(exe):
            for k, s in enumerate(subs):
                jp = show_subtitle(s)
                if JAPANESE.search(jp):
                    add("subtitle", jp, "%s:%04x:%d" % (cfg["opening"], off, k), 2 * OP.LINE_CELLS,
                        "a subtitle of the opening: %d lines of %d letters at most, broken between words; "
                        "{#c} a colour" % (OP.ROWS, 2 * OP.LINE_CELLS))
    if cfg.get("opening_at"):
        p = lzexe.unpack(vol.read(gd + cfg["opening_at"]))
        ds = dgroup(p)
        texts = OP.at_texts(p["image"], ds)
        for at, s in texts:
            add("opening", OP.at_show(s), "%s:%04x" % (cfg["opening_at"], at), len(s),
                "a page of the opening: in place, its room in letters (a letter a byte); lines broken "
                "between words at %d letters; keep the @ commands" % OP.AT_LINE)
        skip = {ds + at for at, _s in texts}
        for at, s in console_strings(p["image"], skip):
            add("console", show(s), "%s:%05x" % (cfg["opening_at"], at), len(s),
                "a notice printed to the screen: in place, plain ASCII, its room in bytes")
    for prog in cfg.get("utilities", []):
        p = lzexe.unpack(vol.read(gd + prog))
        for at, s in console_strings(p["image"], set()):
            add("console", show(s), "%s:%05x" % (prog, at), len(s),
                "a notice printed to the screen: in place, plain ASCII, its room in bytes")
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


PROG_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                      rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*(?:\x00|\r\n\$)")
KANA = re.compile(rb"\x82[\x9f-\xf1]|\x83[\x40-\x96]")


def dgroup(p):
    """The data segment's image place (the entry point's "mov dx, DGROUP")."""
    entry = p["cs"] * 16 + p["ip"]
    if p["image"][entry] != 0xBA:
        raise ValueError("no DGROUP load at the entry point")
    return struct.unpack_from("<H", p["image"], entry + 1)[0] * 16


def program_strings(p):
    """[(image place, bytes, kind)]: the program's Japanese strings (two kana at least): NUL-ended ones
    in its data segment (drawn by its text renderer: "label"), "$"-ended ones (printed through DOS:
    "dos")."""
    image, ds = p["image"], dgroup(p)
    out = []
    for m in PROG_STR.finditer(image):
        s = m.group()
        if len(KANA.findall(s)) < 2:
            continue
        if s.endswith(b"\0"):
            if m.start() >= ds:
                out.append((m.start(), s[:-1], "label"))
        else:
            out.append((m.start(), s[:-3], "dos"))
    return out


CONSOLE_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e\r\n])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                         rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e\r\n])*(?=\x00)")


def console_strings(image, skip):
    """[(image place, bytes)]: a program's NUL-ended Japanese strings (two kana at least) printed to
    the screen through DOS, but those at `skip`."""
    return [(m.start(), m.group()) for m in CONSOLE_STR.finditer(image)
            if len(KANA.findall(m.group())) >= 2 and m.start() not in skip]


def encode_console(text, room):
    """Plain ASCII (another character "?"), cut to `room` bytes."""
    b = "".join(c if " " <= c <= "~" or c in "\r\n" else "?" for c in text).encode("ascii")
    return b[:room]


def encode_at(text):
    """An opening page: lines broken between words at AT_LINE letters ("@n"), the @ commands kept,
    the letters as pairs."""
    lines = []
    for para in text.split("\n"):
        line, col = "", 0
        for w in re.split(r"(@[A-Za-z][0-9]*| )", para):
            if not w:
                continue
            if OP.AT_CMD.fullmatch(w):
                line += w
                continue
            if w == " ":
                if col:
                    line += w
                    col += 1
                continue
            u = letters(_pieces(w))
            if col and col + u > OP.AT_LINE:
                lines.append(line.rstrip(" "))
                line, col = "", 0
            line += w
            col += u
        lines.append(line)
    return b"@n".join(
        b"".join(seg.encode("ascii") if OP.AT_CMD.fullmatch(seg) else encode(_pieces(seg))
                 for seg in re.split(r"(@[A-Za-z][0-9]*)", line) if seg) for line in lines)


AT_STRIP = re.compile(r"@[A-Za-z][0-9]*")
LABEL_TOKEN = re.compile(r"%%[A-Za-z]|%[sd]|%(?:[Gg][A-Za-z]|[A-Za-z])")


def encode_label(text):
    """A program string: its printf tokens ("%s", "%%n") and commands kept, the rest as pairs."""
    out, pos = bytearray(), 0
    for m in list(LABEL_TOKEN.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        if pos < end:
            out += encode(_pieces(text[pos:end]))
        if m:
            out += m.group().encode("ascii")
            pos = m.end()
    return bytes(out)


def show_subtitle(b):
    """A subtitle as text: "&" a new line, "#c" {#c}."""
    out, i = "", 0
    while i < len(b):
        if b[i] == 0x26:
            out += "\n"
            i += 1
        elif b[i] == 0x23:
            out += "{#%s}" % chr(b[i + 1])
            i += 2
        else:
            out += b[i:i + 2].decode("cp932", "replace")
            i += 2
    return out


def encode_subtitle(text, warn, ident):
    """A subtitle's bytes: broken between words into lines of the opening's width ("&" between them),
    ROWS lines at most (more cut and reported); {#c} the colour byte."""
    width = 2 * OP.LINE_CELLS
    lines, out = [], []
    for para in text.split("\n"):
        col, cur = 0, []
        for w in re.split(r"(\{#.\}| )", para):
            if not w:
                continue
            if w == " ":
                if col:
                    cur.append(w)
                    col += 1
                continue
            u = 0 if w.startswith("{#") else len(w)
            if col and col + u > width:
                while cur and cur[-1] == " ":
                    cur.pop()
                lines.append(cur)
                cur, col = [], 0
            cur.append(w)
            col += u
        lines.append(cur)
    if len(lines) > OP.ROWS:
        warn.append("%s: %d lines, cut to %d" % (ident, len(lines), OP.ROWS))
        lines = lines[:OP.ROWS]
    for n, line in enumerate(lines):
        if n:
            out.append(b"&")
        run = ""
        for w in line + ["{#}"]:
            if w.startswith("{#"):
                if run:
                    out.append(encode(_pieces(run)))
                    run = ""
                if len(w) == 4:
                    out.append(b"#" + w[2].encode("ascii"))
            else:
                run += w
    return b"".join(out)


# ---- English as letter pairs

def _pieces(text):
    """[(kind, value)]: "c" a command, "a" an ASCII letter, "j" a full-width character's bytes."""
    out, pos = [], 0
    for m in list(CMD.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        for ch in text[pos:end]:
            for c in SUBST.get(ch, ch):
                if " " <= c <= "~":
                    out.append(("a", c))
                else:
                    try:
                        out.append(("j", c.encode("cp932")))
                    except UnicodeEncodeError:
                        out.append(("a", "?"))
        if m:
            out.append(("c", m.group()))
            pos = m.end()
    return out


def encode(pieces):
    out, run = bytearray(), []
    for kind, v in pieces + [("end", None)]:
        if kind == "a":
            run.append(v)
            continue
        if run:
            out += encode_en("".join(run))
            run = []
        if kind == "c":
            out += v.encode("ascii")
        elif kind == "j":
            out += v
    return bytes(out)


def lay_out(text, width=LINE):
    """The message's pieces with "%N" between words where a line is full: a cell two letters, a run of
    letters as pairs (an odd one ends with a space).  From "【" to "】" the name's width is counted, and
    the lines after it are indented by it, as the program does; a full-width space starting a line
    ends that."""
    words, cur = [], []
    for p in _pieces(text):
        if p[0] == "a" and p[1] != " ":
            cur.append(p)
            continue
        if cur:
            words.append(cur)
            cur = []
        words.append([p])
    if cur:
        words.append(cur)
    open_, close, space = "【".encode("cp932"), "】".encode("cp932"), "　".encode("cp932")
    out, col, indent, naming, counting = [], 0, 0, False, False

    def start():
        return indent if naming else 0
    for w in words:
        k0, v0 = w[0]
        if k0 == "c":
            out += w
            if v0[1].upper() in NEWLINE:
                col = start()
            continue
        if k0 == "a" and v0 == " ":
            if col > start() and col < width:
                out.append(w[0])
                col += 1
            continue
        n = sum(1 for k, _v in w if k == "a")
        u = n + n % 2 + 2 * sum(1 for k, _v in w if k == "j")
        if col > start() and col + u > width:
            if out and out[-1] == ("a", " "):
                out.pop()
                col -= 1
            out.append(("c", "%N"))
            col = start()
        if k0 == "j" and v0 == space and col == start():
            naming = False
            col = 0
        if k0 == "j" and v0 == open_:
            counting, naming, indent = True, False, 0
        out += w
        col += u
        if counting:
            indent += u
            if k0 == "j" and v0 == close:
                counting, naming = False, True
    return out


def letters(pieces):
    n = 0
    for k, v in pieces:
        n += 1 if k == "a" else 2 if k == "j" else 0
    return n


# ---- the program

FETCH_NEW = """
    fetch:
        push bp
        mov bp, sp
        push ds
        push es
        push si
        push di
        cld
        mov al, 0x0b
        out 0x68, al
        mov ax, word ptr [bp + 6]
        les di, dword ptr [bp + 8]
        mov dh, ah
        sub dh, 0xa0
        cmp dh, 0x40
        jae kanji
        test al, 0x80
        jz lo
        and al, 0x7f
        add dh, 0x40
    lo:
        add dh, 0x20
        mov dl, al
        xor al, al
        out 0xa1, al
        mov bh, 1
        jmp go
    kanji:
        add ah, ah
        sub al, 0x1f
        js s1
        cmp al, 0x61
        adc al, 0xde
    s1:
        add ax, 0x1fa1
        and ax, 0x7f7f
        sub ah, 0x20
        out 0xa1, al
        mov al, ah
        out 0xa3, al
        xor bh, bh
    go:
        mov bl, 0x20
    pass:
        or bh, bh
        jz np
        mov al, dh
        out 0xa3, al
        mov dh, dl
    np:
        mov cx, 16
    row:
        mov al, 16
        sub al, cl
        or al, bl
        out 0xa5, al
        in al, 0xa9
        stosb
        inc di
        loop row
        sub di, 31
        xor bl, 0x20
        jz pass
        mov al, 0x0a
        out 0x68, al
        lds si, dword ptr [bp + 8]
        les di, dword ptr [bp + 8]
        mov cx, 0x10
    bold:
        lodsw
        xchg ah, al
        mov bx, ax
        shl ax, 1
        or ax, bx
        xchg ah, al
        stosw
        loop bold
        pop di
        pop si
        pop es
        pop ds
        pop bp
        .byte 0xcb
"""
# the kanji-ROM glyph library's routines: two far wrappers (SJIS to JIS, JIS to SJIS) around their
# near routines, then the glyph fetch (its JIS call; sub ah, 20h; out 0A1h, al ...) ending
# pop di; pop si; pop es; pop ds; pop bp (or leave); retf.  The frames are "push bp; mov bp, sp" or
# "enter 0, 0" (the programs' compilers differ).
FRAME = rb"(?:\x55\x8b\xec|\xc8\x00\x00\x00)"
WRAPPER = re.compile(FRAME + rb"\x1e\x8b\x46\x06\xe8\x03\x00\x1f[\x5d\xc9]\xcb")
FETCH = re.compile(FRAME + rb"\x1e\x06\x56\x57\xfc\xb0\x0b\xe6\x68\x8b\x46\x06\xc4\x7e\x08\xe8..\x80\xec\x20"
                   rb"\xe6\xa1", re.S)
FETCH_END = re.compile(rb"\x5f\x5e\x07\x1f[\x5d\xc9]\xcb")
# the renderer's lead-byte test: test byte ptr [bx + table], 4
LEAD = re.compile(rb"\x8a\x07\xb4\x00\x8b\xd8\xf6\x87(..)\x04", re.S)


def patch_program(orig, cfg, strings=None):
    """MAPL.EXE (LZEXE), written unpacked: the pairs' first bytes marked lead bytes in the renderer's
    character table, and a glyph fetch drawing pairs (two kanji-ROM ANK letters in one 16-dot cell)
    written over the glyph library's two conversion wrappers, their routines and the old fetch (only
    the fetch is called: its two far calls are pointed at the new one); `strings` {image place:
    bytes} written in place."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm
    p = lzexe.unpack(orig)
    image = bytearray(p["image"])
    lead = LEAD.search(image)
    fetch = FETCH.search(image)
    if not lead or not fetch:
        raise ValueError("the renderer's lead-byte test / the glyph fetch not found")
    table = dgroup(p) + struct.unpack("<H", lead.group(1))[0]
    for c in range(0xA0, 0xE0):
        image[table + c] |= 0x04
    start = fetch.start()
    wraps = list(WRAPPER.finditer(image, max(0, start - 0x60), start))
    end = FETCH_END.search(image, start).end()
    if len(wraps) != 2:
        raise ValueError("the glyph library's wrappers not found before the fetch")
    w1 = wraps[0].start()
    routines = {wraps[0].start(), wraps[0].end(), wraps[1].start(), wraps[1].end(), start}
    calls = []
    for m in re.finditer(rb"\x9a(..)(..)", image, re.S):
        off, seg = struct.unpack("<HH", m.group(1) + m.group(2))
        if w1 <= seg * 16 + off < end:
            if seg * 16 + off != start:
                raise ValueError("a far call into the glyph library's wrappers")
            calls.append((m.start(), seg))
    if not calls:
        raise ValueError("no far call to the glyph fetch")
    seg_base = calls[0][1] * 16
    for m in re.finditer(rb"\xe8(..)", image[seg_base:seg_base + 0x10000], re.S):
        at = seg_base + m.start()
        t = seg_base + ((m.start() + 3 + struct.unpack("<h", m.group(1))[0]) & 0xFFFF)
        if t in routines and not w1 <= at < end:
            raise ValueError("a near call into the glyph library's routines")
    code, _labs = _asm(Ks(KS_ARCH_X86, KS_MODE_16), FETCH_NEW, w1 - seg_base, ("fetch",))
    if len(code) > end - w1:
        raise ValueError("the new glyph fetch too long")
    image[w1:end] = code + bytes(end - w1 - len(code))
    for at, seg in calls:
        struct.pack_into("<H", image, at + 1, w1 - seg * 16)
    for at, b in (strings or {}).items():
        image[at:at + len(b)] = b
    return lzexe.build(p, bytes(image))


# ---- patch

def _pseudo(e):
    if e["kind"] == "msg":                      # (each Japanese run between the commands filled)
        parts, cmds = CMD.split(e["jp"]), CMD.findall(e["jp"])
        out = ""
        for k, part in enumerate(parts):
            n = len(JAPANESE.findall(part))
            out += pseudo(e["id"], 2 * n) if n else part
            if k < len(cmds):
                out += cmds[k]
        return out
    if e["kind"] == "subtitle":
        return pseudo(e["id"], 2 * len(JAPANESE.findall(e["jp"])))
    if e["kind"] == "opening":
        return pseudo(e["id"], 2 * len(JAPANESE.findall(AT_STRIP.sub("", e["jp"]))))
    if e["kind"] in ("label", "dos", "console"):    # (in place: cut to the room)
        return pseudo(e["id"], e["max_cells"], 1.0)[:e["max_cells"]]
    return pseudo(e["id"], e["max_cells"], 1.0)[:e["max_cells"]]


def cut(b, room):
    """b cut to room at a character's boundary (a Shift-JIS or pair lead byte takes the next)."""
    i, last = 0, 0
    while i < len(b):
        n = 2 if 0x81 <= b[i] <= 0x9F or 0xA0 <= b[i] <= 0xDF or 0xE0 <= b[i] <= 0xFC else 1
        if i + n > room:
            break
        i += n
        last = i
    return b[:last]


def _console(image, skip, prog, by_ref, ids, warn):
    out = {}
    for at, s in console_strings(image, skip):
        ref = "%s:%05x" % (prog, at)
        if ref in by_ref:
            b = encode_console(by_ref[ref], len(s) + 99)
            if len(b) > len(s):
                warn.append("%s: %d bytes, room for %d (cut)" % (ids[ref]["id"], len(b), len(s)))
                b = b[:len(s)]
            out[at] = b.ljust(len(s), b" ")
    return out


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    store = int(cfg["store"], 16)
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    for f, path in sorted(scenes(vol, cfg).items()):
        d = vol.read(path)
        new = {}
        for at, _s, _op in M.strings(d, store):
            ref = "%s:%04x" % (f, at)
            if ref not in by_ref:
                continue
            e = ids[ref]
            if e["kind"] == "msg":
                pieces = lay_out(by_ref[ref])
            else:
                pieces = _pieces(by_ref[ref])
                if letters(pieces) > e["max_cells"]:
                    warn.append("%s: %d letters, room for %d" % (e["id"], letters(pieces), e["max_cells"]))
            new[at] = encode(pieces)
        if new:
            try:
                vol.write(path, M.build(d, store, new))
            except ValueError as ex:
                raise SystemExit("%s: %s; shorten these strings: %s" % (f, ex, ", ".join(
                    sorted({ids["%s:%04x" % (f, a)]["id"] for a in new}))))
    gd = cfg["game_dir"] + "/"
    if by_ref:                                  # (no English: the programs as they were)
        orig = vol.read(gd + cfg["program"])
        strings = {}
        for at, s, kind in program_strings(lzexe.unpack(orig)):
            ref = "%s:%05x" % (cfg["program"], at)
            if ref not in by_ref:
                continue
            e = ids[ref]
            if kind == "dos":
                b = "".join(c if " " <= c <= "~" else "?" for c in by_ref[ref].replace("\n", " ")).encode("ascii")
            else:
                b = encode_label(by_ref[ref])
            if len(b) > len(s):
                warn.append("%s: %d bytes, room for %d (cut)" % (e["id"], len(b), len(s)))
                b = cut(b, len(s))
            strings[at] = b.ljust(len(s), b" " if kind == "dos" else b"\0")
        vol.write(gd + cfg["program"], patch_program(orig, cfg, strings))
        if cfg.get("opening"):
            exe = vol.read(gd + cfg["opening"])
            new = {}
            for off, subs in OP.subtitles(exe):
                for k, _s in enumerate(subs):
                    ref = "%s:%04x:%d" % (cfg["opening"], off, k)
                    if ref in by_ref:
                        new[(off, k)] = encode_subtitle(by_ref[ref], warn, ids[ref]["id"])
            try:
                vol.write(gd + cfg["opening"], OP.patch(exe, new))
            except ValueError as ex:
                raise SystemExit("%s; shorten the subtitles" % ex)
        if cfg.get("opening_at"):
            path = gd + cfg["opening_at"]
            orig = vol.read(path)
            p = lzexe.unpack(orig)
            ds = dgroup(p)
            texts = OP.at_texts(p["image"], ds)
            strings = {}
            for at, s in texts:
                ref = "%s:%04x" % (cfg["opening_at"], at)
                if ref in by_ref:
                    b = encode_at(by_ref[ref])
                    if len(b) > len(s):
                        warn.append("%s: %d bytes, room for %d (cut)" % (ids[ref]["id"], len(b), len(s)))
                        b = cut(b, len(s))
                    strings[ds + at] = b.ljust(len(s), b"\0")
            skip = {ds + at for at, _s in texts}
            strings.update(_console(p["image"], skip, cfg["opening_at"], by_ref, ids, warn))
            vol.write(path, patch_program(orig, cfg, strings))
        for prog in cfg.get("utilities", []):
            p = lzexe.unpack(vol.read(gd + prog))
            image = bytearray(p["image"])
            for at, b in _console(p["image"], set(), prog, by_ref, ids, warn).items():
                image[at:at + len(b)] = b
            vol.write(gd + prog, lzexe.build(p, bytes(image)))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
