"""Active's "if" (MAIN.EXE; if, if 2, if 3): the scenarios' *.ADV scripts.

A script is blocks one after another, each opened by op 80h: a byte, the block's kind (0 the start, 1
the text, 2 a choice, 3 the end), and a word, the place of the next block's header plus 4.  A choice
block's header is followed by its items: D0h, a condition (an expression), a byte, the item's text
(Shift-JIS up to a NUL) and a word, where the item goes; the code after the items is the branches'.

The rest is ops and texts.  An op is a byte (`FMT`: 2Bh, 2Dh, 60h-7Fh, 80h, B0h-B9h, D1h, DFh) and its
operands: strings (up to a NUL: file and variable names), expressions (`expr`: a primary, `(`, `n` and a
byte, `?` or `@` and a name, then operators and primaries up to a NUL or `)`), bytes and words (the
jumps' targets: B0h/B1h the else's and the end's of a condition (B5h, B7h, B9h, D1h test an expression
and go on past the B0h after it or to its word), B2h a jump, B3h a call, B6h/B8h a byte and a jump; B4h
and DFh return).  Op 72h is a speaker's name, a text up to a NUL; 7Fh a sub-op and its operands; 74h
starts another script.  Any other byte starts a text: Shift-JIS up to a NUL, its controls a backslash
and a letter (`\\p` the key wait, `\\w` a new window, `\\n` a new line, `\\\\` no new line after the text,
`\\v` and a byte a pause, `\\a \\c \\e \\m \\s \\t \\z` and a byte, `\\f \\g \\k`).  Every pointer is an offset
in the script, so a script can be laid out anew with them moved (`rebuild`).

MAIN.EXE (Borland C) draws a text two bytes at a time (a Shift-JIS character, read from the kanji
ROM, a 16-dot cell) and counts its window's columns in cells; `patch_program` makes it draw a pair of
ASCII bytes as two half-width letters in the cell (the ROM's half-width row 29h).
"""
import re
import struct

FMT = {0x2B: "S", 0x2D: "S", 0x60: "BB", 0x61: "SBB", 0x62: "SBBB", 0x63: "S", 0x64: "BB", 0x65: "SBB",
       0x66: "", 0x67: "", 0x68: "B", 0x69: "S", 0x6A: "B", 0x6B: "B", 0x6C: "B", 0x6D: "B", 0x6E: "B",
       0x6F: "BBBB", 0x70: "BB", 0x71: "B", 0x72: "T", 0x73: "", 0x74: "S", 0x75: "L", 0x76: "SS", 0x77: "",
       0x78: "", 0x79: "SE", 0x7A: "", 0x7B: "", 0x7C: "", 0x7D: "", 0x7F: "K", 0x80: "H",
       0xB0: "W", 0xB1: "W", 0xB2: "W", 0xB3: "W", 0xB4: "E", 0xB5: "E", 0xB6: "BW", 0xB7: "E", 0xB8: "BW",
       0xB9: "E", 0xD1: "E", 0xDF: ""}
SUB7F = {1: "B", 2: "B", 3: "", 4: "B", 5: "B", 6: "", 7: "S", 8: "BB", 9: "B"}
ESC_ARG = set(b"acemstvz")      # the controls with a byte after them
WINDOW = 0x6F                   # op 6Fh: the text window (left, top, width in cells, lines)

# the glyph routine's Shift-JIS to JIS: push word [bp+6] / lcall (the C library's) / add sp, 2 / mov dx, ax /
# shr ax, 8 / sub al, 20h / mov [row], al / mov al, dl / and al, 0FFh / mov [column], al (the ROM's code)
CONVERT_SIG = re.compile(rb"\xff\x76\x06\x9a(....)\x83\xc4\x02\x8b\xd0\xc1\xe8\x08\x2c\x20\xa2(.)\x00"
                         rb"\x8a\xc2\x24\xff\xa2(.)\x00", re.S)
# the kanji ROM reader: push ds / mov ax, seg / mov ds, ax / mov dx, 0A1h / mov al, [column] / out dx, al
ROM_SIG = re.compile(rb"\x1e\xb8..\x8e\xd8\xba\xa1\x00\xa0(.)\x00\xee", re.S)
# the start's window: mov byte [x], 1 / [y], 0Fh / [width], w / [lines], h
WINDOW_SIG = re.compile(rb"\xc6\x06..\x01\xc6\x06..\x0f\xc6\x06..(.)\xc6\x06..(.)", re.S)


def string(d, i):
    return d.index(0, i) + 1


def primary(d, i):
    c = d[i]
    if c == 0x28:
        return expr(d, i + 1)
    if c == 0x6E:
        return i + 2
    if c in (0x3F, 0x40):
        return string(d, i + 1)
    raise ValueError("an expression's %02x at %x" % (c, i))


def expr(d, i):
    """The end of an expression from i (its NUL or `)` included)."""
    if d[i] == 0:
        return i + 1
    i = primary(d, i)
    while True:
        c = d[i]
        i += 1
        if c in (0, 0x29):
            return i
        i = primary(d, i)


def walk(d):
    """(pointers [(the place of a word, the target it means: a word, or a header's word less 4)],
    events in the script's order: ("text", start, end), ("name", start, end), ("item", start, end,
    block), ("window", cells) and ("op", place, op); end past the NUL)."""
    i, ptrs, ev = 0, [], []
    block = 0
    while i < len(d):
        op = d[i]
        if op not in FMT:
            j = string(d, i)
            ev.append(("text", i, j))
            i = j
            continue
        ev.append(("op", i, op))
        start = i
        i += 1
        f = FMT[op]
        if f == "H":
            kind = d[i]
            if kind != 3:
                ptrs.append((i + 1, "hdr"))
            i += 3
            block += 1
            if kind == 2:
                while d[i] == 0xD0:
                    i = expr(d, i + 1) + 1
                    j = string(d, i)
                    ev.append(("item", i, j, block))
                    i = j
                    ptrs.append((i, "word"))
                    i += 2
            elif kind == 3 and i != len(d):
                raise ValueError("the end block at %x before the script's end (%x)" % (start, len(d)))
            continue
        if f == "K":
            s = d[i]
            i += 1
            if s not in SUB7F:
                raise ValueError("op 7Fh's sub-op %02x at %x" % (s, start))
            f = SUB7F[s]
        if f == "L":
            while d[i]:
                i = expr(d, i)
            i += 1
            continue
        if op == WINDOW:
            ev.append(("window", d[i + 2]))
        for c in f:
            if c == "S":
                i = string(d, i)
            elif c == "E":
                i = expr(d, i)
            elif c == "B":
                i += 1
            elif c == "W":
                ptrs.append((i, "word"))
                i += 2
            elif c == "T":
                j = string(d, i)
                ev.append(("name", i, j))
                i = j
    if i != len(d):
        raise ValueError("the script runs past its end")
    starts = {e[1] for e in ev if e[0] in ("text", "op")} | {len(d)}
    for p, kind in ptrs:
        t = struct.unpack_from("<H", d, p)[0] - (4 if kind == "hdr" else 0)
        if t not in starts:
            raise ValueError("a pointer at %x to %x, no op's start" % (p, t))
    return ptrs, ev


def rebuild(d, new):
    """The script with new {start: (end, bytes)} put in place of the bytes start:end, every pointer
    moved."""
    ptrs, _ev = walk(d)
    cuts = sorted(new.items())
    out, at, shift = bytearray(), 0, []
    for s, (e, b) in cuts:
        out += d[at:s]
        shift.append((s, e, len(out) - s, len(out) + len(b) - e))
        out += b
        at = e
    out += d[at:]

    def moved(t):
        dt = 0
        for s, e, before, after in shift:
            if t >= e:
                dt = after
            elif t >= s:
                return t + before
        return t + dt
    for p, kind in ptrs:
        t = struct.unpack_from("<H", d, p)[0]
        v = moved(t - 4) + 4 if kind == "hdr" else moved(t)
        struct.pack_into("<H", out, moved(p), v)
    return bytes(out)


def window(image):
    """(cells, lines): the text window MAIN.EXE starts with."""
    m = WINDOW_SIG.findall(image)
    if len(m) != 1:
        raise ValueError("MAIN.EXE: the text window found %d times" % len(m))
    return m[0][0][0], m[0][1][0]


def data_start(image):
    """Where MAIN.EXE's data starts: its lowest data segment (mov ax, segment / mov ds, ax)."""
    segs = [struct.unpack("<H", m.group(1))[0] * 16 for m in re.finditer(rb"\xb8(..)\x8e\xd8", image, re.S)]
    return min(s for s in segs if 0 < s < len(image))


def patch_program(exe):
    """MAIN.EXE drawing a pair of ASCII bytes as two half-width letters: the glyph routine keeps a code
    whose first byte is under 80h as it is, with the first byte's top bit set (a kanji's ROM row is
    under 80h), and the ROM reader reads such a code's two letters from the ROM's half-width row 29h,
    the first's left half into the cell's left, the second's into its right (the code for each half
    given anew on every row).  The C library's call moves, its relocation with it."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    from .adl import _asm16
    exe = bytearray(exe)
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    nrel, relat = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 0x18)[0]
    img = exe[hdr:]
    conv, roms = list(CONVERT_SIG.finditer(img)), list(ROM_SIG.finditer(img))
    if len(conv) != 1 or len(roms) != 1:
        raise SystemExit("MAIN.EXE: the glyph conversion found %d times, the ROM reader %d" % (len(conv), len(roms)))
    conv, rom = conv[0], roms[0]
    lc, row, col = conv.group(1), conv.group(2)[0], conv.group(3)[0]
    if row != col + 1 or rom.group(1)[0] != col:
        raise SystemExit("MAIN.EXE: the ROM code's bytes are not the ones known")
    at = conv.start()
    code, labs = _asm16("""
    mov ax, word ptr [bp + 6]
    cmp ah, 0x80
    jb asc
    push ax
    .byte 0x9a, {l0}, {l1}, {l2}, {l3}
    add sp, 2
    sub ah, 0x20
    jmp keep
asc:
    or ah, 0x80
keep:
    mov word ptr [{col}], ax
""".format(l0=lc[0], l1=lc[1], l2=lc[2], l3=lc[3], col=hex(col)), at, [])
    if len(code) != conv.end() - at:
        raise SystemExit("MAIN.EXE: the conversion's code is %d bytes, not %d" % (len(code), conv.end() - at))
    old_seg, new_seg = at + 3 + 3, at + code.index(b"\x9a" + lc) + 3
    img[at:at + len(code)] = code
    # the reader's own: its segment, the cell's first byte, the header's width byte and the done flag
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    ins = []
    for i in md.disasm(bytes(img[rom.start():rom.start() + 0x100]), rom.start()):
        ins.append(i)
        if i.mnemonic == "retf":
            break
    end = ins[-1].address + ins[-1].size
    cell = [int(i.op_str.split("+ ")[1].split("]")[0], 16) for i in ins
            if i.mnemonic == "mov" and i.op_str.startswith("byte ptr [bx + ")][0]
    width = [int(i.op_str.split("[")[1].split("]")[0], 0) for i in ins
             if i.mnemonic == "mov" and i.op_str.startswith("byte ptr [") and i.op_str.endswith(", 0x10")][0]
    done = [int(i.op_str.split("[")[1].split("]")[0], 0) for i in ins
            if i.mnemonic == "mov" and i.op_str.startswith("word ptr [") and i.op_str.endswith(", 1")][0]
    seg = img[rom.start() + 2:rom.start() + 4]
    code, _l = _asm16("""
    push ds
    .byte 0xb8, {s0}, {s1}
    mov ds, ax
    mov dx, word ptr [{col}]
    xor cx, cx
    test dh, dh
    jns go
    mov ah, 9
    mov al, dh
    and al, 0x7f
    mov word ptr [{col}], ax
    mov dh, ah
    mov ch, 0x20
go:
    mov bx, {cell}
row:
    mov al, byte ptr [{col}]
    out 0xa1, al
    mov al, byte ptr [{row}]
    out 0xa3, al
    mov al, cl
    or al, 0x20
    out 0xa5, al
    in al, 0xa9
    mov byte ptr [bx], al
    mov al, dl
    out 0xa1, al
    mov al, dh
    out 0xa3, al
    mov al, cl
    or al, ch
    out 0xa5, al
    in al, 0xa9
    mov byte ptr [bx + 1], al
    inc bx
    inc bx
    inc cl
    cmp cl, 0x10
    jb row
    mov word ptr [{width}], 0x210
    inc word ptr [{done}]
    pop ds
    .byte 0xcb
""".format(s0=seg[0], s1=seg[1], col=hex(col), row=hex(row), cell=hex(cell), width=hex(width), done=hex(done)),
        rom.start(), [])
    if len(code) > end - rom.start():
        raise SystemExit("MAIN.EXE: the ROM reader does not fit (%d bytes, %d)" % (len(code), end - rom.start()))
    img[rom.start():rom.start() + len(code)] = code
    img[rom.start() + len(code):end] = b"\x90" * (end - rom.start() - len(code))
    exe[hdr:] = img
    found = 0
    for k in range(nrel):
        off, s_ = struct.unpack_from("<HH", exe, relat + 4 * k)
        if s_ * 16 + off == old_seg:
            struct.pack_into("<HH", exe, relat + 4 * k, new_seg - s_ * 16, s_)
            found += 1
    if found != 1:
        raise SystemExit("MAIN.EXE: the C library call's relocation found %d times" % found)
    return bytes(exe)
