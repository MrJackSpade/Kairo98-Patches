"""Half-width English for Illusion's tmexec engine (GAME.EXE patch).

The message library draws a record two bytes (one Shift-JIS character) at a
time: Shift-JIS -> JIS, glyph from the kanji ROM, drawn at the cursor, cursor
advanced by the character width (a variable: 1, 2 or 3 bytes), with the
engine wrapping lines itself.  The patch
* rewrites that loop in its own bytes, keeping its two far calls at their
  original offsets (so the EXE's relocation entries still match): a byte
  below 80 is drawn as the kanji ROM's 8x16 ANK glyph (the fetch routine
  sends code - 2000 to ports A1/A3, and code (c+20)00 there selects ANK c)
  with the width set to 1 for that character (the engine's half-width mode
  keeps the glyph's left half), and advances one byte; a line wraps when the
  columns left drop to zero or below;
* pages long messages (English outgrows boxes the Japanese filled): when the
  box's line count is used up and more text follows, it waits for a mouse
  click (mouse port 7FD9, bit 7), restores the box area saved when the
  message started and continues at the top.  The saved copy sits at the same
  place on graphics page 1 (copied row by row through the access-page port
  A6), which these games leave unused, so no memory is taken.  This code lives in the library's unused tail
  (zero-filled in the file, untouched at run time), found by size;
* changes the message lookup's end-of-file mark from "!" to the ^Z every
  message file ends with, so English may use "!".
All sites are found by byte signature.
"""
import re
import struct

LOOP = re.compile(
    rb"\x50\x53\x51\x52\x26\x80\x3c\x24\x75\x05\x5a\x59\x5b\x58\xcb\x56\x57\x26\x8b\x04\x86\xe0"
    rb"(\x9a..(..))\x2e\x89\x2e(..)(\x9a(..)..)\x5f\x5e\x5a\x59\x5b\x58\x2e\x2b\x06(..)\x74\x1d"
    rb".{50,110}?\x2e\xa1(..)\x83\xc6\x02\xe9..", re.S)
SEARCH = re.compile(rb"\x26\x80\x3c\x21(\x74.\x26\x80\x3c\x23)", re.S)
CAVE_BYTES = 0x300


def _asm(ks, src, org, want=()):
    """Assemble with keystone.  "CALLN target" (a label or 0x-address) becomes a
    3-byte near call (keystone emits a 32-bit form for 16-bit near calls).
    Returns (code, {label: address}) for the labels in `want`."""
    lines, calls = [], []
    for line in src.split("\n"):
        t = line.strip()
        if t.startswith("CALLN "):
            tag = "__call%d" % len(calls)
            calls.append((tag, t.split()[1]))
            lines += [tag + ":", "nop", "nop", "nop"]
        else:
            lines.append(line)
    names = list(want) + [c[0] for c in calls] + [c[1] for c in calls if not c[1].startswith("0x")]
    names = list(dict.fromkeys(names))
    body = "\n".join(lines)
    full = bytes(ks.asm(body + "\n" + "\n".join(".word %s" % n for n in names), org)[0])
    code = bytearray(full[:len(full) - 2 * len(names)])
    addr = {n: int.from_bytes(full[len(code) + 2 * i:len(code) + 2 * i + 2], "little")
            for i, n in enumerate(names)}
    for tag, target in calls:
        t = int(target, 16) if target.startswith("0x") else addr[target]
        at = addr[tag] - org
        code[at:at + 3] = b"\xe8" + ((t - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    return bytes(code), addr


def build(exe, box_lines=4):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    exe = bytearray(exe)
    hdr = struct.unpack_from("<14H", exe, 0)
    base = hdr[4] * 16                                   # load image starts here in the file
    img = bytes(exe[base:])
    m = LOOP.search(img)
    if not m:
        raise ValueError("message draw loop not found")
    s = SEARCH.search(img)
    if not s:
        raise ValueError("message lookup not found")
    seg = int.from_bytes(m.group(2), "little")           # the library's segment (pre-relocation)
    org = m.start() - seg * 16                           # loop start as a segment offset
    fetch = int.from_bytes(m.group(5), "little")         # glyph fetch + draw routine (far)
    bpvar = int.from_bytes(m.group(3), "little")
    width = int.from_bytes(m.group(6), "little")
    cols = int.from_bytes(m.group(7), "little")
    tail = re.compile(rb"\x2e\x01\x1e(..)\x83\xc6\x02\x5a", re.S).search(img, m.start())
    stride_m = re.compile(rb"\x2e\x8b\x1e(..)\x2e\x01\x1e(..)\x2e\x29\x06", re.S).search(img, m.start())
    if not tail or not stride_m:
        raise ValueError("message draw loop: cursor variables not found")
    pos = int.from_bytes(tail.group(1), "little")
    stride = int.from_bytes(stride_m.group(1), "little")
    region = m.end() - m.start()
    # the pager: in the zero-filled tail of the library segment (its last part)
    z = re.compile(rb"\x00{%d,}" % 0x800).search(img, m.end())
    if not z or z.start() - seg * 16 > 0x10000 - 0x800:
        raise ValueError("no free space in the library segment for the pager")
    cave = z.end() - seg * 16 - CAVE_BYTES
    if cave + CAVE_BYTES > 0x10000:
        cave = 0x10000 - CAVE_BYTES
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    v = {"W": width, "P": pos, "S": stride, "C": cols, "B": bpvar, "L": org, "ML": box_lines}

    # data at fixed offsets from the pager's start (numeric addresses: keystone
    # would give label operands a 32-bit address prefix, which a 286 rejects)
    d = {k: cave + off for k, off in (("flag", 2), ("pend", 3), ("lines", 4), ("dirv", 5),
                                      ("p0", 6), ("rows", 8), ("vpos", 10), ("pseg", 12),
                                      ("planes", 14), ("temp", 22))}
    v.update(d)
    cave_src = """
        .byte 0xeb, 100
        .byte 0, 0, 0, 0
        .word 0, 0, 0, 0
        .word 0xa800, 0xb000, 0xb800, 0xe000
        .fill 80, 1, 0
    head:
        cmp byte ptr es:[si], 0x24
        jne h1
        mov byte ptr cs:[{flag}], 0
        mov byte ptr cs:[{pend}], 0
        add sp, 2
        .byte 0xcb
    h1:
        cmp byte ptr cs:[{flag}], 0
        jne h2
        mov byte ptr cs:[{flag}], 1
        mov byte ptr cs:[{lines}], 0
        push ax
        mov ax, word ptr cs:[{P}]
        mov word ptr cs:[{p0}], ax
        pop ax
        mov byte ptr cs:[{dirv}], 0
        CALLN copybox
        .byte 0xc3
    h2:
        cmp byte ptr cs:[{pend}], 0
        jne h3
        .byte 0xc3
    h3:
        mov byte ptr cs:[{pend}], 0
        push ax
        push dx
        mov dx, 0x7fd9
    w1:
        in al, dx
        test al, 0x80
        jnz w1
    w2:
        in al, dx
        test al, 0x80
        jz w2
        pop dx
        pop ax
        mov byte ptr cs:[{dirv}], 1
        CALLN copybox
        mov ax, word ptr cs:[{p0}]
        mov word ptr cs:[{P}], ax
        mov ax, word ptr cs:[{C}]
        mov byte ptr cs:[{lines}], 0
        .byte 0xc3
    common:
        mov bx, word ptr cs:[{S}]
        add bx, ax
        sub bx, word ptr cs:[{C}]
        add word ptr cs:[{P}], bx
        mov ax, word ptr cs:[{C}]
        inc byte ptr cs:[{lines}]
        mov bl, byte ptr cs:[{lines}]
        cmp bl, {ML}
        jb c1
        mov byte ptr cs:[{pend}], 1
    c1:
        .byte 0xc3
    copybox:
        push ax
        push bx
        push cx
        push dx
        push si
        push di
        push ds
        push es
        mov ax, {ML}
        mul word ptr cs:[{S}]
        mov bx, 80
        div bx
        mov word ptr cs:[{rows}], ax
        mov ax, word ptr cs:[{C}]
        cmp ax, 80
        ja cb_out
        xor al, al
        out 0x7c, al
        xor bx, bx
    cb_plane:
        mov ax, word ptr cs:[bx + {planes}]
        mov word ptr cs:[{pseg}], ax
        mov ax, word ptr cs:[{p0}]
        mov word ptr cs:[{vpos}], ax
        mov dx, word ptr cs:[{rows}]
    cb_row:
        mov al, byte ptr cs:[{dirv}]
        out 0xa6, al
        mov cx, word ptr cs:[{C}]
        mov si, word ptr cs:[{vpos}]
        mov ds, word ptr cs:[{pseg}]
        mov di, {temp}
        push cs
        pop es
        cld
        rep movsb
        mov al, byte ptr cs:[{dirv}]
        xor al, 1
        out 0xa6, al
        mov cx, word ptr cs:[{C}]
        mov si, {temp}
        push cs
        pop ds
        mov di, word ptr cs:[{vpos}]
        mov es, word ptr cs:[{pseg}]
        rep movsb
        add word ptr cs:[{vpos}], 80
        dec dx
        jnz cb_row
        add bx, 2
        cmp bx, 8
        jb cb_plane
        xor al, al
        out 0xa6, al
    cb_out:
        pop es
        pop ds
        pop di
        pop si
        pop dx
        pop cx
        pop bx
        pop ax
        .byte 0xc3
    """.format(**v)
    cave_code, labels = _asm(ks, cave_src, cave, ("head", "common"))
    if len(cave_code) > CAVE_BYTES:
        raise ValueError("pager is %d bytes, room for %d" % (len(cave_code), CAVE_BYTES))
    cave_head, cave_common = labels["head"], labels["common"]

    head_src = """
        CALLN 0x%x
        nop
        nop
        nop
        nop
        push ax
        push bx
        push cx
        push dx
        push si
        push di
        mov ax, word ptr es:[si]
        test al, al
        .byte 0x79, 0x00
        xchg al, ah
    """ % cave_head
    head, _ = _asm(ks, head_src, org)                     # the jns (79 xx) target is fixed up below
    if len(head) != 22:
        raise ValueError("head is %d bytes, expected 22" % len(head))
    keep = img[m.start() + 22:m.start() + 37]           # lcall convert+draw / mov [bp] / lcall fetch
    t0 = org + 37
    tail_src = """
        pop di
        pop si
        pop dx
        pop cx
        pop bx
        pop ax
        mov bx, word ptr cs:[{W}]
        add si, 2
    adv:
        sub ax, bx
        jle wrap
        add word ptr cs:[{P}], bx
        cmp byte ptr es:[si], 0x0d
        je nl
        jmp {L}
    wrap:
        mov ax, bx
        jmp common
    nl:
        add si, 2
    common:
        CALLN 0x{CC:x}
        jmp {L}
    ascii:
        mov ah, al
        add ah, 0x20
        xor al, al
        mov bp, ax
        mov word ptr cs:[{B}], bp
        push word ptr cs:[{W}]
        mov word ptr cs:[{W}], 1
        push cs
        CALLN 0x{F:x}
        pop word ptr cs:[{W}]
        pop di
        pop si
        pop dx
        pop cx
        pop bx
        pop ax
        mov bx, 1
        inc si
        jmp adv
    """.format(CC=cave_common, F=fetch, **v)
    tail_code, tl = _asm(ks, tail_src, t0, ("ascii",))
    if 37 + len(tail_code) > region:
        raise ValueError("rewritten loop is %d bytes, room for %d" % (37 + len(tail_code), region))
    ascii_at = tl["ascii"]
    jns = head.index(b"\x79")
    rel = ascii_at - (org + jns + 2)
    if not -128 <= rel <= 127:
        raise ValueError("ascii path out of short-jump range")
    head = head[:jns + 1] + bytes([rel & 0xFF]) + head[jns + 2:]
    code = (head + keep + tail_code).ljust(region, b"\x90")
    exe[base + m.start():base + m.end()] = code
    at = base + seg * 16 + cave
    if any(exe[at:at + len(cave_code)]):
        raise ValueError("pager area is not free")
    exe[at:at + len(cave_code)] = cave_code
    exe[base + s.start() + 3] = 0x1A                     # lookup stops at ^Z instead of "!"
    return bytes(exe)


def message_width(exe):
    """The message window's width (in half-width columns) the game passes to the
    message routine (the lookup that finds "#nnnnn" and draws it): callers
    load the columns per line into AX just before the far call."""
    hdr = struct.unpack_from("<14H", exe, 0)
    img = bytes(exe[hdr[4] * 16:])
    s = SEARCH.search(img)
    m = LOOP.search(img)
    if not s or not m:
        return None
    seg = int.from_bytes(m.group(2), "little")
    start = img.rfind(b"\x1e\x06\x57\x50\x53\x51\x52\x55", 0, s.start())
    if start < 0 or s.start() - start > 0x40:
        return None
    call = b"\x9a" + (start - seg * 16).to_bytes(2, "little") + seg.to_bytes(2, "little")
    widths = []
    for c in re.finditer(re.escape(call), img):
        w = re.compile(rb"\xb8(..)", re.S).search(img, c.start() - 24, c.start())
        if w:
            widths.append(int.from_bytes(w.group(1), "little"))
    # the message window is the width most calls use; narrower ones are small
    # boxes (names, labels), so only widths of 30 columns and up count
    widths = [w for w in widths if 30 <= w <= 80]
    if not widths:
        return None
    return max(sorted(set(widths)), key=widths.count)
