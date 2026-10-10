"""D.O.'s ADL5 engine (ADL5.EXE: Yuu Disk Vol. 5 and the 1993-94 titles):
the EDT scripts and the half-width patch.  It is ADL's later version
(pc98tl/adl.py: the characters, the kana table, the name and command
tables are the same); addresses below are Yuu Disk Vol. 5's ADL5.EXE.

A script (*.EDT) is read whole into a segment: a big-endian word, the
offset of the statements (from the file's start); then the entries
(big-endian words, offsets from that start: the targets of 2Bh's gotos and
28h's calls, 10h's menus and 11h's items); then the statements, until FFh
or the end of the file.  The interpreter (ADL5.EXE 4EA8h, seg 80h) steps
over a statement as STMT_LEN gives, or, for the opcodes it lists at
5143h: a NUL-ended name and a byte (NAMED), 33h (the same, then four bytes
when the byte is 2 or more), 4Ah (a byte, then entries until FFh: a
byte, a length, that many bytes), 70h (text), 71h (four bytes, then text,
drawn at a place of its own), 22h, 25h, 61h, 64h, 93h, A5h, A8h, C3h
(a picture: two bytes, their product, doubled with the flag after them,
and one more) and C4h.

Text (70h; ADL5.EXE 1F9Eh): items until a 00 or a byte of 0Ch-FEh (the
next statement): FFh, then characters until 00 (a run of text; ADL's 0Fh);
01-0Bh the window's controls: 01 c the colour, 02 a key wait, 03 the window
cleared, 04 n speaker n's name (the text after it indented by the name
table's slot, op 19h), 05, 06 a new line (when the window is full: a key
wait, then the window cleared), 07 n and 08 n an animation on and off,
09 and 0Ah (three bytes), 0Bh n window n becomes the current one.  A 00
straight after a control moves the cursor to the window's left edge; a 00
after a run only ends the statement.

Windows (82h: x, y, width, height (big-endian words), the window's
number): the text runs from 16 dots in at the left to 16 dots in at the
right, from 12 dots down; text is drawn to the graphics planes through
the GRCG (16 or 32 dots a character, bold or not).

The patch (patch_exe, on ADL5.EXE; it is not packed):

* The helper's room: ROOM paragraphs put in at the end of the code
  segment, the segments after it moved up (as pc98tl/adl.py).
* In a run of text, 20h switches to half-width letters (until 20h again or
  the run's end): 21h-7Eh are ASCII, 7Fh a space and 0Ah a new line, each
  drawn 8 dots wide from the BIOS 8x16 font in the window's colour (bold
  where the engine's text is bold), with the engine's own character wait
  and wrap (the character width set to 8 for it); bytes of 80h and up are
  still Shift-JIS.  Before each word the helper measures it against the
  window's right edge and starts a new line when it would not fit; a new
  line whose row (16 dots) would run past the window's bottom pages first
  (the engine's own page only once a row starts at or below the bottom).
* Speaker names and the commands (drawn by the same routine, 1D8Bh) take
  ASCII as well.

Every site is found by its byte signature; a program that does not match is
refused.
"""
import re
import struct

from .adl import Bad, _asm16, _call_target, _once, CODE_SEG

STMT_LEN = {0x10: 4, 0x11: 4, 0x12: 7, 0x13: 2, 0x14: 1, 0x15: 1, 0x17: 2, 0x20: 2, 0x21: 2, 0x23: 4, 0x24: 4,
            0x28: 3, 0x29: 1, 0x2A: 6, 0x2B: 3, 0x30: 1, 0x31: 1, 0x32: 1, 0x34: 1, 0x35: 1, 0x36: 17, 0x37: 11,
            0x39: 1, 0x3A: 11, 0x40: 5, 0x41: 5, 0x42: 4, 0x43: 6, 0x44: 7, 0x45: 5, 0x48: 3, 0x49: 4, 0x4B: 3,
            0x4C: 4, 0x4D: 3, 0x53: 4, 0x54: 6, 0x60: 1, 0x62: 1, 0x63: 1, 0x65: 6, 0x72: 2, 0x73: 2, 0x74: 2,
            0x75: 4, 0x80: 2, 0x81: 2, 0x82: 10, 0x83: 3, 0x85: 3, 0x86: 7, 0x88: 2, 0x90: 10, 0x91: 1, 0x92: 2,
            0x94: 4, 0x95: 5, 0xA0: 4, 0xA1: 4, 0xA2: 9, 0xA4: 2, 0xA6: 5, 0xA7: 11, 0xA9: 7, 0xAA: 9, 0xAB: 5,
            0xAC: 3, 0xB0: 8, 0xB1: 1, 0xB2: 1, 0xB3: 2, 0xB4: 1, 0xB5: 2, 0xC2: 3, 0xC5: 11, 0xC6: 13, 0xC7: 1,
            0xC8: 2, 0xC9: 5, 0xCA: 3, 0xCB: 1}
NAMED = {0x16, 0x18, 0x19, 0x38, 0x50, 0x51, 0x52, 0x84, 0x87, 0xA3, 0xC0, 0xC1}
TEXT_MARK = 0xFF
WINDOW_OP = 0x82
# the controls' argument bytes
CTRL_ARGS = {1: 1, 4: 1, 7: 1, 8: 1, 0x0B: 1, 9: 3, 0x0A: 3}
CTRL_END = 0x0C                 # the first byte that is not a control
LOADS = (0x50, 0x51)
CODED = False                   # the scripts are coded (pc98tl/adl.py's codes, after a 4-byte prefix)

# ADL98 (ADL98.EXE, Zatsuon Ryouiki 1994: its walker at 57A6h): ADL5's statements with these lengths
# changed or added, more named statements, 0Ch a control with a byte, and the scripts coded
ADL98 = {
    "len": {0x10: 5, 0x1A: 4, 0x1B: 4, 0x3B: 4, 0x3C: 6, 0x65: 7, 0x89: 3, 0x8A: 1, 0x9A: 5, 0x9B: 5, 0xAD: 8,
            0xAE: 13, 0xD2: 11, 0xD3: 5, 0xD4: 10, 0xD5: 1, 0xD6: 5, 0xD7: 7, 0xD8: 3, 0xDA: 4, 0xDB: 2, 0xE1: 7,
            0xE2: 9, 0xE3: 1},
    "named": {0xD0, 0xD1, 0x96},
    "ctrl_args": {0x0C: 1},
}
# ADL98S (ADL98S.EXE, Cybernoid Alpha 1995: its walker at 59FFh): ADL98's, and 66h named, 67h, 9Dh,
# AFh, and 9Ch (a length byte and that many bytes)
ADL98S = {"len": {0x67: 1, 0x9D: 6, 0xAF: 8}, "named": {0x66}}
# ADL3 (ADL3A.EXE: DOR Special Edition Sakigake, Doki Doki Disk Vol. 4-5; ADL3B.EXE: Collector D): ADL5's
# earlier build, without its opcodes from B0h and C0h on, 75h, 88h, 94h, 95h, with shorter 23h, 24h, 53h,
# 54h; ADL3A's 93h is one byte (ADL3B's and ADL5's a name and three bytes)
ADL3 = {"len": {0x23: 2, 0x24: 3, 0x53: 3, 0x54: 5},
        "drop": {0x75, 0x88, 0x94, 0x95, 0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xC2, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
                 0xCA, 0xCB},
        "named_drop": {0xC0, 0xC1}}
_BASE = (dict(STMT_LEN), set(NAMED), dict(CTRL_ARGS))
VARIANT = "adl5"


def set_variant(name):
    """The engine's build: "adl5" (ADL5.EXE), "adl98" (ADL98.EXE) or "adl98s" (ADL98S.EXE)."""
    global STMT_LEN, NAMED, CTRL_ARGS, CTRL_END, CODED, VARIANT
    STMT_LEN, NAMED, CTRL_ARGS = dict(_BASE[0]), set(_BASE[1]), dict(_BASE[2])
    CTRL_END, CODED, VARIANT = 0x0C, False, name
    if name in ("adl98", "adl98s"):
        STMT_LEN.update(ADL98["len"])
        NAMED |= ADL98["named"]
        CTRL_ARGS.update(ADL98["ctrl_args"])
        CTRL_END, CODED = 0x0D, True
    if name == "adl98s":
        STMT_LEN.update(ADL98S["len"])
        NAMED |= ADL98S["named"]
    if name in ("adl3a", "adl3b"):
        STMT_LEN.update(ADL3["len"])
        for op in ADL3["drop"]:
            STMT_LEN.pop(op, None)
        NAMED -= ADL3["named_drop"]
        if name == "adl3a":
            STMT_LEN[0x93] = 1


def decode(raw):
    """(the prefix and coding, a script as the engine reads it)."""
    if not CODED:
        return None, raw
    from .adl import _decode
    head, dec = _decode(raw[4:])
    return (raw[:4], head), dec


def encode(how, d):
    if how is None:
        return d
    from .adl import _encode
    return how[0] + _encode(how[1], d)


def ctrl_len(b):
    return 1 + CTRL_ARGS.get(b, 0)


def _named(d, i):
    return d.index(0, i + 1) + 2


def _text(d, j):
    while True:
        b = d[j]
        j += 1
        if b == 0:
            return j
        if b == TEXT_MARK:
            j = d.index(0, j) + 1
        elif b < CTRL_END:
            j += CTRL_ARGS.get(b, 0)
        else:
            return j - 1


def statement(d, i):
    """The end of the statement at i."""
    op = d[i]
    if op in NAMED:
        return _named(d, i)
    if op == 0x33:
        j = _named(d, i)
        return j + 4 if d[j - 1] >= 2 else j
    if op == 0x4A:
        j = i + 2
        while d[j] != 0xFF:
            j += 2 + d[j + 1]
        return j + 1
    if op == 0x70:
        return _text(d, i + 1)
    if op == 0x71:
        return _text(d, i + 5)
    if op == 0xA5:
        return _named(d, i + 13)
    if op == 0xA8:
        return _named(d, i + 3)
    if op == 0x22:
        return d.index(0, i + 2) + 1
    if op == 0x25:
        return d.index(0, i) + 1
    if op == 0x61:
        return _named(d, i) + 1
    if op == 0x64:
        return _named(d, i) + (6 if VARIANT in ("adl98", "adl98s") else 5)
    if op == 0x93 and VARIANT != "adl3a":
        return _named(d, i) + 3
    if op == 0xC3 and not VARIANT.startswith("adl3"):
        return i + 4 + d[i + 1] * d[i + 2] * (2 if d[i + 3] & 2 else 1)
    if op == 0xC4 and not VARIANT.startswith("adl3"):
        return _named(d, i + 1)
    if VARIANT == "adl98s" and op == 0x9C:
        return i + 2 + d[i + 1]
    if VARIANT in ("adl98", "adl98s"):
        if op == 0x98:
            # (two bytes, then 3-byte records until 04)
            j = i + 3
            while d[j] != 4:
                j += 3
            return j + 1
        if op == 0x99:
            # (five bytes, then records until FFh: 00 and a word, 01 and three bytes, else five)
            j = i + 6
            while d[j] != 0xFF:
                j += {0: 3, 1: 4}.get(d[j], 6)
            return j + 1
        if op == 0xE0:
            return _named(d, i) + 6
        if op == 0xD9:
            return _named(d, i) + 5
        if op == 0x76:
            # (five bytes, then items until 00: 01 and a byte, or a byte and a run of bytes from 0Ah up)
            j = i + 5
            while d[j] != 0:
                if d[j] == 1:
                    j += 2
                else:
                    j += 1
                    while d[j] >= 0x0A:
                        j += 1
            return j + 1
        if op == 0x15:
            return i + 1
    if op not in STMT_LEN:
        raise Bad("opcode %02X at %x" % (op, i))
    return i + STMT_LEN[op]


def base(d):
    return struct.unpack_from(">H", d, 0)[0]


def _linear(d):
    out, i = [], base(d)
    while i < len(d) and d[i] != 0xFF:
        j = statement(d, i)
        if j > len(d):
            raise Bad("statement at %x runs past the end" % i)
        out.append((i, j))
        i = j
    return out


def _resync(d):
    """[(start, end)] of the statements read straight through, the walk picked up again at the next
    entry wherever it meets bytes no statement starts with (ADL98S's tables after AFh: records the
    entries reach, never the walker); the bytes skipped move with the statements around them."""
    ents = sorted(v for v in entries(d).values() if v < len(d))
    out, i = [], base(d)
    while i < len(d) and d[i] != 0xFF:
        try:
            j = statement(d, i)
            if j > len(d):
                raise Bad("past the end")
            out.append((i, j))
            i = j
        except (Bad, IndexError, ValueError):
            # (the next entry after the last statement's start: a statement it falls inside is dropped,
            # it was bytes the walker never steps onto)
            after = out[-1][0] if out else -1
            e = next((v for v in ents if v > after and v != i), len(d))
            if e < i:
                while out and out[-1][1] > e:
                    out.pop()
            elif e == len(d) or e <= i:
                e = next((v for v in ents if v > i), len(d))
            i = e
    return out


def tokenize(d):
    """[(start, end)] of the statements: read straight through from the statements' start, or, where
    that runs into bytes no statement starts with, picked up again at the next entry (_resync)."""
    try:
        return _linear(d)
    except (Bad, IndexError, ValueError):
        return _resync(d)


def entries(d):
    start = base(d)
    return {k: start + struct.unpack_from(">H", d, 2 + 2 * k)[0] for k in range(start // 2 - 1)}


def items(d, s, e):
    """As pc98tl/adl.py's: ("text", start, end), ("ctrl", start, end), ("end", s, e)."""
    out = []
    j = s + (5 if d[s] == 0x71 else 1)
    while j < e:
        b = d[j]
        if b == TEXT_MARK:
            k = d.index(0, j + 1)
            out.append(("text", j + 1, k))
            j = k + 1
        elif b == 0:
            out.append(("end", j, j + 1))
            j += 1
        else:
            out.append(("ctrl", j, j + ctrl_len(b)))
            j += ctrl_len(b)
    return out


def rebuild(d, toks, new):
    """The script with the statements in new ({start: bytes}) replaced, the entries moved (offsets
    from the statements' start).  (A script past 64 KB comes back as built, its entries cut to 16
    bits: the caller refuses it by its size.)"""
    start = base(d)
    out = bytearray(d[:start])
    # (pieces: (old start, old end, new start, kept as it is); the bytes between statements kept)
    pieces, pos = [], start
    for s, e in toks:
        if s > pos:
            pieces.append((pos, s, len(out), True))
            out += d[pos:s]
        pieces.append((s, e, len(out), s not in new))
        out += new.get(s, d[s:e])
        pos = e
    pieces.append((pos, len(d), len(out), True))
    out += d[pos:]
    for k, at in entries(d).items():
        if at >= len(d):
            # (an entry past the statements: the end of the file, moved with it)
            to = at - len(d) + len(out)
        else:
            piece = next(p for p in pieces if p[0] <= at < p[1] or p[0] == at)
            if at != piece[0] and not piece[3]:
                raise Bad("entry %d (%x) is inside a rebuilt statement" % (k, at))
            to = piece[2] + (at - piece[0])
        struct.pack_into(">H", out, 2 + 2 * k, (to - start) & 0xFFFF)
    return bytes(out)


def window(d, s):
    """(x, the text's width in dots) of 82h at s."""
    x, _y, w, _h = struct.unpack_from(">4H", d, s + 1)
    return x, w - 32


def set_window_width(d, s, width):
    """82h at s with its text widened to width dots."""
    x, y, _w, h = struct.unpack_from(">4H", d, s + 1)
    return d[s:s + 1] + struct.pack(">4H", x, y, width + 32, h) + d[s + 9:s + 10]


# ---- ADL5.EXE

ROOM = 0x20                     # paragraphs put in at the end of the code segment for the helper

# a run of text, the engine's loop (1F9Eh): call controls / mov al, es:[si-1] / or al, al / je /
# cmp al, FFh / jne / call run / jmp
RUNS_SIG = re.compile(rb"\xe8..\x26\x8a\x44\xff\x0a\xc0\x74\x09\x3c\xff\x75\x05\xe8(..)\xeb.", re.S)
# the run (1FBAh) from its test of the buffer mode to its draw, wait and advance
RUN_SIG = re.compile(
    rb"\x80\x3e(..)\x00\x75\x05\x56\xe8..\x5e"           # cmp [buffer], 0 / jne / push si / call / pop si
    rb"\x26\x8a\x34\x46\x0a\xf6\x75\x03\xe9..\x80\xfe\x20\x74\xe4"   # mov dh, es:[si] ... cmp dh, 20h / je
    rb"\x80\xfe\x80\x73\x13\x8a\xde\x32\xff\xd1\xe3\x81\xc3..\x2e\x8a\x37\x2e\x8a\x57\x01\xeb\x04"
    rb"\x26\x8a\x14\x46"
    rb"\x80\x3e..\x00\x74\x12\x8b\x3e(..)\x8a\x0e(..)\xe8(..)\x83\x06..\x02\xeb."     # buffer: draw at [pos]
    rb"\xa0(..)\x32\xe4\xbf(..)\x03\xf8\x8b\x05\x52\xe8(..)\x5a\x8b\x5d\x02\xe8(..)\x8b\xf8"
    rb"\x8a\x0e..\xe8..\x80\x3e(..)\x00\x75.(\xb0\x0c\xe8..\x0a\xc0\x75.)?"
    rb"\xb8\x0e\x04\xcd\x18\xf6\xc4\x04\x75."
    rb"\xb4\x05\xcd\x33\xb2\x01\xa8\x03\x75\x09\xe8(..)\xa8\x10\x75\x02\xb2\x03\x8a\xc2"
    rb"\xe8(..)\xe8(..)\xe8(..)\xe9", re.S)
# the advance (205Eh): ... add ax, [width] ...; its new line: add [di+2], 14h / call page
ADVANCE_SIG = re.compile(rb"\xa0..\x32\xe4\xbf..\x03\xf8\x8b\x05\x03\x06(..)\x3d\x80\x02", re.S)
# the glyph drawer (1DD7h): ... xor ah, ah / mov al, [colour] / cli / call grcg on / mov si, glyph /
# call / call grcg off / sti; its rows: test [bold], 1
GLYPH_SIG = re.compile(rb"\x32\xe4\xa0(..)\xfa\xe8(..)\xbe..\xe8..\xe8(..)\xfb", re.S)
BOLD_SIG = re.compile(rb"\xac\x8a\xe0\xac\xf6\x06(..)\x01\x74\x06\x8b\xd8\xd1\xe8\x0b\xc3", re.S)
# the graphics-plane string drawer (1D8Bh, names and commands) at its two-byte character
GRAPH_SIG = re.compile(rb"\x3c\x0d\x74\x08\xac\x8a\xd0\xe8(..)\xeb\xe6", re.S)

HELPER = """
runstart:
    mov byte ptr cs:[{ank}], 0
    mov byte ptr cs:[{word}], 1
    JMPN {run}

text:
    cmp dh, 0x20
    jne t1
    xor byte ptr cs:[{ank}], 1
    JMPN {run}
t1:
    test byte ptr cs:[{ank}], 1
    jz back
    cmp dh, 0x80
    jb t2
back:
    JMPN {notspace}
t2:
    cmp byte ptr [{buffer}], 0
    je t3
    mov di, word ptr [{bufpos}]
    mov al, dh
    CALLN ank
    inc word ptr [{bufpos}]
    JMPN {run}
t3:
    mov al, byte ptr [{sel}]
    xor ah, ah
    mov di, {rec}
    add di, ax
    cmp dh, 0x0a
    jne t4
    mov byte ptr cs:[{word}], 1
    mov ax, word ptr [di]
    cmp ax, word ptr [di + 4]
    je t9
    CALLN newline
    mov ax, word ptr [di + 4]
    mov word ptr [di], ax
t9:
    JMPN {run}
t4:
    cmp dh, 0x7f
    jne t4w
    mov byte ptr cs:[{word}], 1
    mov ax, word ptr [di]
    cmp ax, word ptr [di + 4]
    je t9
    mov dh, 0x20
    jmp t5
t4w:
    cmp byte ptr cs:[{word}], 0
    je t5
    mov byte ptr cs:[{word}], 0
    push si
    mov cx, 1
w1:
    mov al, byte ptr es:[si]
    cmp al, 0x21
    jb w2
    cmp al, 0x7f
    jae w2
    inc cx
    inc si
    jmp w1
w2:
    pop si
    shl cx, 3
    mov ax, word ptr [di]
    cmp ax, word ptr [di + 4]
    je t5
    add ax, cx
    cmp ax, word ptr [di + 8]
    jbe t5
    push dx
    CALLN newline
    pop dx
    mov ax, word ptr [di + 4]
    mov word ptr [di], ax
t5:
    push word ptr [{width}]
    mov word ptr [{width}], 8
    mov ax, word ptr [di]
    push dx
    CALLN {prewrap}
    pop dx
    mov ax, word ptr [di]
    mov bx, word ptr [di + 2]
    CALLN {xy}
    mov di, ax
    mov al, dh
    CALLN ank
    cmp byte ptr [{fast}], 0
    jne t7
{extra}    mov ax, 0x40e
    int 0x18
    test ah, 4
    jne t7
    mov ah, 5
    int 0x33
    mov dl, 1
    test al, 3
    jne t6
    CALLN {skipkey}
    test al, 0x10
    jne t6
t6s:
    mov dl, 3
t6:
    mov al, dl
    CALLN {settimer}
    CALLN {waittimer}
t7:
    CALLN {advance}
    pop word ptr [{width}]
    JMPN {run}

newline:
    add word ptr [di + 2], 0x14
    mov ax, word ptr [di + 2]
    add ax, 0x10
    cmp ax, word ptr [di + {bottom}]
    jbe n1
    mov ax, word ptr [di + {bottom}]
    mov word ptr [di + 2], ax
n1:
    CALLN {page}
    .byte 0xc3

ank:
    pusha
    push ds
    push es
    mov dl, al
    mov dh, 0x80
    mov bx, cs
    mov cx, {glyph}
    mov ah, 0x14
    int 0x18
    mov bl, byte ptr [{bold}]
    xor ah, ah
    mov al, byte ptr [{color}]
    cli
    CALLN {grcg_on}
    mov ax, 0xa800
    mov es, ax
    push cs
    pop ds
    mov si, {glyph2}
    mov cx, 16
a1:
    lodsb
    test bl, 1
    jz a2
    mov ah, al
    shr ah, 1
    or al, ah
a2:
    mov byte ptr es:[di], al
    add di, 0x50
    loop a1
    CALLN {grcg_off}
    sti
    pop es
    pop ds
    popa
    .byte 0xc3

graph:
    cmp al, 0x80
    jb g1
    lodsb
    mov dl, al
    CALLN {cgkanji}
    JMPN {graphloop}
g1:
    push ds
    mov dx, cs
    add dx, {dseg_delta}
    mov ds, dx
    CALLN ank
    pop ds
    inc di
    JMPN {graphloop}
"""


def _move_up(exe, hdr, img, fixups, rel_at, split_seg, room_paras, code, name):
    """The program with room_paras paragraphs (code at their start) put in at split_seg: every
    segment from it on moves up (the fixups' values, the relocation entries past it, the stack)."""
    split = split_seg * 16
    for f in fixups:
        v = struct.unpack_from("<H", img, f)[0]
        if v >= split_seg:
            struct.pack_into("<H", img, f, v + room_paras)
    room = bytearray(room_paras * 16)
    room[:len(code)] = code
    img[split:split] = room
    out = bytearray(exe[:hdr]) + img
    for k in range(len(fixups)):
        o, sg = struct.unpack_from("<2H", out, rel_at + 4 * k)
        if sg * 16 + o >= split:
            struct.pack_into("<H", out, rel_at + 4 * k + 2, sg + room_paras)
    ss = struct.unpack_from("<H", out, 0x0E)[0]
    if ss >= split_seg:
        struct.pack_into("<H", out, 0x0E, ss + room_paras)
    struct.pack_into("<HH", out, 2, len(out) % 512, -(-len(out) // 512))
    return bytes(out)


def patch_exe(exe, name="ADL5.EXE"):
    """ADL5.EXE (or ADL98.EXE) with the half-width helper (see the module's docstring), put in at the
    end of the code segment (the entry's), before the next segment the relocations name."""
    if exe[:2] != b"MZ":
        raise SystemExit("%s: not an MZ program" % name)
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    img = bytearray(exe[hdr:])
    cs0 = code_seg * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    next_seg = min(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v > code_seg)
    seg = bytearray(img[cs0:next_seg * 16])
    runs = _once(seg, RUNS_SIG, "text runs' loop")
    run_call = runs.start() + 15
    run = _call_target(seg, run_call)
    m = _once(seg, RUN_SIG, "text run")
    if m.start() != run:
        raise SystemExit("%s: the text run is not where its loop calls" % name)
    word = lambda k: struct.unpack("<H", m.group(k))[0]  # noqa: E731
    buffer, bufpos, color, sel, rec, fast = word(1), word(2), word(3), word(5), word(6), word(9)
    # (call targets are relative: read them off their instructions)
    prewrap = _call_target(seg, m.start(7) - 1)
    xy = _call_target(seg, m.start(8) - 1)
    skipkey = _call_target(seg, m.start(11) - 1)
    settimer = _call_target(seg, m.start(12) - 1)
    waittimer = _call_target(seg, m.start(13) - 1)
    advance = _call_target(seg, m.start(14) - 1)
    # (ADL98's added key check before the wait: mov al, 0Ch / call / or al, al / jne (the slow wait))
    extra = ""
    if m.group(10):
        extra = "    mov al, 0x0c\n    CALLN %s\n    or al, al\n    jne t6s\n" % hex(_call_target(seg, m.start(10) + 2))
    space = seg.find(b"\x80\xfe\x20\x74\xe4", run, run + 0x20)
    notspace = space + 5
    a = ADVANCE_SIG.match(seg, advance)
    if not a:
        raise SystemExit("%s: the advance is not laid out as expected" % name)
    width = struct.unpack("<H", a.group(1))[0]
    # (the page: the new line's call after add [di+2], 14h)
    nl = seg.find(b"\x83\x45\x02\x14\xe8", advance, advance + 0x40)
    if nl < 0:
        raise SystemExit("%s: the advance's new line is not found" % name)
    page = _call_target(seg, nl + 4)
    # (the page: mov ax, [di+2] / cmp ax, [di+bottom] / jb / call: a new line pages once a row starts at
    # or below the window's bottom; the helper's pages as well once a row would run past it)
    pm = re.compile(rb"\x8b\x45\x02\x3b\x45(.)\x72\x03\xe8", re.S).match(seg, page)
    if not pm:
        raise SystemExit("%s: the page is not laid out as expected" % name)
    bottom = pm.group(1)[0]
    g =_once(seg, GLYPH_SIG, "glyph drawer")
    gcolor = struct.unpack("<H", g.group(1))[0]
    grcg_on = _call_target(seg, g.start() + 6)
    grcg_off = _call_target(seg, g.end() - 4)
    if gcolor != color:
        raise SystemExit("%s: the glyph drawer's colour is not the text's" % name)
    bold = struct.unpack("<H", _once(seg, BOLD_SIG, "glyph rows").group(1))[0]
    gr = _once(seg, GRAPH_SIG, "graphics drawer")
    gat = gr.start() + 4
    cgkanji = _call_target(seg, gat + 3)
    graphloop = gat + 8 + struct.unpack("b", seg[gat + 7:gat + 8])[0]
    # (the data segment the glyph drawer loads (push ds / push es / mov ax, seg / mov ds, ax / mov es, ax),
    # as an offset from the code segment once the room is in: the graphics path's ds)
    dm = re.compile(rb"\x1e\x06\xb8(..)\x8e\xd8\x8e\xc0", re.S).search(seg, cgkanji, cgkanji + 0x10)
    if not dm:
        raise SystemExit("%s: the glyph drawer's data segment is not found" % name)
    data_seg = struct.unpack("<H", dm.group(1))[0]
    dseg_delta = data_seg + (ROOM if data_seg >= next_seg else 0) - code_seg
    at = len(seg)
    flags = (at + ROOM * 16 - 0x14, at + ROOM * 16 - 0x13)
    glyph = at + ROOM * 16 - 0x12          # the BIOS font's answer: 2 bytes, then 16 rows
    src = HELPER.format(
        ank=hex(flags[0]), word=hex(flags[1]), run=hex(run), notspace=hex(notspace), buffer=hex(buffer), bufpos=hex(bufpos),
        sel=hex(sel), rec=hex(rec), page=hex(page), width=hex(width), prewrap=hex(prewrap), xy=hex(xy),
        fast=hex(fast), skipkey=hex(skipkey), settimer=hex(settimer), waittimer=hex(waittimer),
        advance=hex(advance), glyph=hex(glyph), glyph2=hex(glyph + 2), color=hex(color), bold=hex(bold),
        grcg_on=hex(grcg_on), grcg_off=hex(grcg_off), cgkanji=hex(cgkanji), graphloop=hex(graphloop),
        extra=extra, dseg_delta=hex(dseg_delta), bottom=hex(bottom))
    code, labels = _asm16(src, at, ("runstart", "text", "graph"))
    if len(code) > ROOM * 16 - 0x14:
        raise SystemExit("%s: the helper is %d bytes, the room %d" % (name, len(code), ROOM * 16 - 0x14))
    seg[run_call:run_call + 3] = b"\xe8" + struct.pack("<H", (labels["runstart"] - (run_call + 3)) & 0xFFFF)
    seg[space:space + 5] = b"\xe9" + struct.pack("<H", (labels["text"] - (space + 3)) & 0xFFFF) + b"\x90\x90"
    seg[gat:gat + 3] = b"\xe9" + struct.pack("<H", (labels["graph"] - (gat + 3)) & 0xFFFF)
    img[cs0:cs0 + len(seg)] = seg
    for lo, n in ((run_call, 3), (space, 5), (gat, 3)):
        if any(cs0 + lo - 1 <= f < cs0 + lo + n for f in fixups):
            raise SystemExit("%s: a segment fixup falls in a patched range" % name)
    return _move_up(exe, hdr, img, fixups, rel_at, next_seg, ROOM, code, name)


# ---- ADL5.EXE's own strings

_PAIR = rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])"


def _data_segment(img, fixups):
    """The program's data segment: the segment its relocations name most often."""
    from collections import Counter
    return Counter(struct.unpack_from("<H", img, f)[0] for f in fixups).most_common(1)[0][0]


def _runtime_bytes(seg):
    """The data segment's bytes the code writes one at a time (mov [addr], a byte register: a drive
    letter, a digit)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    found, a = set(), 0
    # (a store through ds or es: the data segment; cs: is the program's own variables)
    store = re.compile(r"byte ptr (?:es:)?\[(0x[0-9a-f]+)\], [a-d][hl]$")
    while a < len(seg):
        moved = False
        for ins in md.disasm(seg[a:], a):
            if ins.mnemonic == "mov":
                m = store.match(ins.op_str)
                if m:
                    found.add(int(m.group(1), 16))
            a = ins.address + ins.size
            moved = True
        if not moved or a < len(seg):
            a += 1
    return found


def program_strings(exe):
    """[(start, end, kind, fixed)] in ADL5.EXE (file offsets): "run" a message's run of text (after its
    FFh, before its 00; fixed: the offsets of the characters the code rewrites, the drive letter),
    "word" a movement command's 9-byte slot (8 letters and NUL, drawn by the graphics drawer)."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    img = exe[hdr:]
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    data_seg = _data_segment(img, fixups)
    data = data_seg * 16
    writes = _runtime_bytes(img[struct.unpack_from("<H", exe, 0x16)[0] * 16:data])
    out = []
    for m in re.finditer(rb"\xff(" + _PAIR + rb"{2,})\x00", img[data:], re.S):
        s, e = m.start(1), m.end(1)
        # (a rewritten byte is a character's second: the character starts one before it)
        fixed = sorted(w - 1 - s for w in writes if s < w < e)
        out.append((hdr + data + s, hdr + data + e, "run", fixed))
    # the movement commands: four 9-byte slots in a row, each a NUL-ended name of spaces and characters
    word = re.compile(rb"(?:" + _PAIR + rb"|\x20)+\x00", re.S)
    seg = img[data:]
    for at in range(9, len(seg) - 36):
        if all(word.fullmatch(seg, at + 9 * k, at + 9 * k + 9) for k in range(4)) and \
                not word.fullmatch(seg, at - 9, at):
            for k in range(4):
                out.append((hdr + data + at + 9 * k, hdr + data + at + 9 * k + 8, "word", []))
    return sorted(out)


# ---- a helper program with the same graphics drawer (PCMSET2.EXE, the voice speed setting)

GRAPH_HELPER = """
graph:
    cmp al, 0x80
    jb g1
    lodsb
    mov dl, al
    CALLN {cgkanji}
    JMPN {graphloop}
g1:
    pusha
    push ds
    push es
    mov dx, cs
    add dx, {dseg_delta}
    mov ds, dx
    mov dl, al
    mov dh, 0x80
    mov bx, cs
    mov cx, {glyph}
    mov ah, 0x14
    int 0x18
    mov bl, byte ptr [{bold}]
    xor ah, ah
    mov al, byte ptr [{color}]
    cli
    CALLN {grcg_on}
    mov ax, 0xa800
    mov es, ax
    push cs
    pop ds
    mov si, {glyph2}
    mov cx, 16
a1:
    lodsb
    test bl, 1
    jz a2
    mov ah, al
    shr ah, 1
    or al, ah
a2:
    mov byte ptr es:[di], al
    add di, 0x50
    loop a1
    CALLN {grcg_off}
    sti
    pop es
    pop ds
    popa
    inc di
    JMPN {graphloop}
"""
GRAPH_ROOM = 0x10


def patch_graph(exe, name):
    """A program whose strings are drawn by ADL5's graphics drawer (1D8Bh's copy) with ASCII drawn
    half-width (8 dots, the BIOS 8x16 font, the drawer's colour and bold), the helper in GRAPH_ROOM
    paragraphs put in at the end of its code segment (the entry's), the segments after it moved up."""
    if exe[:2] != b"MZ":
        raise SystemExit("%s: not an MZ program" % name)
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    img = bytearray(exe[hdr:])
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    data_seg = min(v for v in (struct.unpack_from("<H", img, f)[0] for f in fixups) if v > code_seg)
    cs0 = code_seg * 16
    seg = bytearray(img[cs0:data_seg * 16])
    gr = _once(seg, GRAPH_SIG, "graphics drawer")
    gat = gr.start() + 4
    cgkanji = _call_target(seg, gat + 3)
    graphloop = gat + 8 + struct.unpack("b", seg[gat + 7:gat + 8])[0]
    g = _once(seg, GLYPH_SIG, "glyph drawer")
    color = struct.unpack("<H", g.group(1))[0]
    grcg_on = _call_target(seg, g.start() + 6)
    grcg_off = _call_target(seg, g.end() - 4)
    bold = struct.unpack("<H", _once(seg, BOLD_SIG, "glyph rows").group(1))[0]
    at = len(seg)
    glyph = at + GRAPH_ROOM * 16 - 0x12
    src = GRAPH_HELPER.format(cgkanji=hex(cgkanji), graphloop=hex(graphloop), dseg_delta=hex(data_seg + GRAPH_ROOM - code_seg),
                              glyph=hex(glyph), glyph2=hex(glyph + 2), bold=hex(bold), color=hex(color),
                              grcg_on=hex(grcg_on), grcg_off=hex(grcg_off))
    code, labels = _asm16(src, at, ("graph",))
    if len(code) > GRAPH_ROOM * 16 - 0x12:
        raise SystemExit("%s: the helper is %d bytes, the room %d" % (name, len(code), GRAPH_ROOM * 16 - 0x12))
    seg[gat:gat + 3] = b"\xe9" + struct.pack("<H", (labels["graph"] - (gat + 3)) & 0xFFFF)
    img[cs0:cs0 + len(seg)] = seg
    if any(cs0 + gat - 1 <= f < cs0 + gat + 3 for f in fixups):
        raise SystemExit("%s: a segment fixup falls in a patched range" % name)
    split = data_seg * 16
    if any(f >= split for f in fixups):
        raise SystemExit("%s: a segment fixup is past the code segment" % name)
    for f in fixups:
        v = struct.unpack_from("<H", img, f)[0]
        if v >= data_seg:
            struct.pack_into("<H", img, f, v + GRAPH_ROOM)
    room = bytearray(GRAPH_ROOM * 16)
    room[:len(code)] = code
    img[split:split] = room
    out = bytearray(exe[:hdr]) + img
    struct.pack_into("<HH", out, 2, len(out) % 512, -(-len(out) // 512))
    # (the stack segment, past the code, moves up with the rest)
    ss = struct.unpack_from("<H", out, 0x0E)[0]
    if ss >= data_seg:
        struct.pack_into("<H", out, 0x0E, ss + GRAPH_ROOM)
    return bytes(out)


def graph_strings(exe):
    """[(start, end, fixed)] (file offsets) of a helper program's lines: NUL-ended Shift-JIS strings in
    its data segment (fixed: the offsets in a line of the characters the code rewrites, digits)."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    img = exe[hdr:]
    code_seg = struct.unpack_from("<H", exe, 0x16)[0]
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    fixups = [struct.unpack_from("<H", exe, rel_at + 4 * k)[0] + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0]
              for k in range(nrel)]
    data_seg = _data_segment(img, fixups)
    data = data_seg * 16
    writes = _runtime_bytes(img[code_seg * 16:data])
    out = []
    for m in re.finditer(rb"(?<=\x00)((?:" + _PAIR + rb"|\x20)*" + _PAIR + rb"(?:" + _PAIR + rb"|\x20)*)\x00",
                         img[data:], re.S):
        s, e = m.start(1), m.end(1)
        out.append((hdr + data + s, hdr + data + e, sorted(w - 1 - s for w in writes if s < w < e)))
    return out


# ---- ADL98S's file archives (EDT00: the scripts and the tables)

class Archive:
    """EDT00 (and GF00, FMD00, PCM00): a word, the entries' size; entries of 16 bytes: the name
    (12, NUL-padded) and the member's offset (a dword); an entry with no name gives the end.  The
    members follow in order, from the header's end."""

    def __init__(self, raw):
        self.raw = raw
        first = struct.unpack_from("<H", raw, 0)[0]
        self.entries = []
        for at in range(2, first, 16):
            name = raw[at:at + 12].split(b"\x00")[0].decode("ascii")
            self.entries.append((name, struct.unpack_from("<I", raw, at + 12)[0]))
        if not self.entries or self.entries[-1][0]:
            raise Bad("the archive does not end with an unnamed entry")

    def names(self):
        return [n for n, _o in self.entries[:-1]]

    def read(self, name):
        for k, (n, o) in enumerate(self.entries[:-1]):
            if n == name:
                return self.raw[o:self.entries[k + 1][1]]
        raise KeyError(name)

    def rebuilt(self, changed):
        """The archive with changed ({name: bytes}) members, the offsets laid out anew."""
        first = 2 + struct.unpack_from("<H", self.raw, 0)[0]
        head = bytearray(self.raw[:first])
        body = bytearray()
        for k, (n, o) in enumerate(self.entries):
            struct.pack_into("<I", head, 2 + 16 * k + 12, first + len(body))
            if n:
                body += changed.get(n, self.raw[o:self.entries[k + 1][1]])
        return bytes(head + body + self.raw[self.entries[-1][1]:])
