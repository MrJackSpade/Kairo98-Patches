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
  columns left drop to zero or below, and a CR LF right after such a wrap is
  taken as that line's end (not drawn, no blank line);
* pages long messages (English outgrows boxes the Japanese filled): when the
  box's line count is used up and more text follows, it waits for a mouse
  click (mouse port 7FD9, bit 7), restores the box area saved when the
  message started and continues at the top.  The saved copy sits at the same
  place on graphics page 1 (copied row by row through the access-page port
  A6), which these games leave unused.  Only messages longer than the box
  are saved and paged, so short strings never touch the access page.  The
  pager lives in a small DOS block of its own, set up by an entry stub
  before the game starts (see _entry_stub), and the loop calls it through
  far pointers kept in its own spare bytes;
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
    # the loop reaches the pager through two far pointers kept in the loop's
    # own spare bytes (its last 8)
    ptrs = org + region - 8
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    v = {"W": width, "P": pos, "S": stride, "C": cols, "B": bpvar, "L": org, "ML": box_lines,
         "PTRH": ptrs, "PTRC": ptrs + 4}

    # the pager runs in a DOS block of its own (see _entry_stub); its data sits
    # at fixed offsets from the block's start (numeric addresses: keystone
    # would give label operands a 32-bit address prefix, which a 286 rejects)
    d = {"LIB": 0, "OIP": 2, "OCS": 4, "ZSEG": 6, "ZLEN": 8, "flag": 10, "pend": 11,
         "lines": 12, "dirv": 13, "endf": 14, "p0": 16, "rows": 18, "vpos": 20, "pseg": 22,
         "planes": 24, "cc": 32, "temp": 34}
    v.update(d)
    pager_src = """
        .word 0, 0, 0, 0, 0
        .byte 0, 0, 0, 0, 0, 0
        .word 0, 0, 0, 0
        .word 0xa800, 0xb000, 0xb800, 0xe000
        .word 0
        .fill 80, 1, 0
    head_far:
        push ds
        mov ds, word ptr cs:[{LIB}]
        CALLN head
        cmp byte ptr cs:[{endf}], 0
        jne hf_end
        pop ds
        .byte 0xcb
    hf_end:
        mov byte ptr cs:[{endf}], 0
        pop ds
        add sp, 4
        .byte 0xcb
    common_far:
        push ds
        mov ds, word ptr cs:[{LIB}]
        CALLN common
        pop ds
        .byte 0xcb
    finish:
        mov es, word ptr cs:[{ZSEG}]
        xor di, di
        mov cx, word ptr cs:[{ZLEN}]
        xor al, al
        cld
        rep stosb
        pop es
        pop ds
        pop bp
        pop di
        pop si
        pop dx
        pop cx
        pop bx
        pop ax
        .byte 0x2e, 0xff, 0x2e
        .word {OIP}
    head:
        cmp byte ptr es:[si], 0x24
        jne h1
        mov byte ptr cs:[{flag}], 0
        mov byte ptr cs:[{pend}], 0
        mov byte ptr cs:[{endf}], 1
        .byte 0xc3
    h1:
        cmp byte ptr cs:[{flag}], 0
        jne h2
        mov byte ptr cs:[{flag}], 1
        mov byte ptr cs:[{lines}], 0
        push ax
        mov ax, word ptr [{P}]
        mov word ptr cs:[{p0}], ax
        pop ax
        CALLN count
        cmp byte ptr cs:[{flag}], 2
        je h1s
        .byte 0xc3
    h1s:
        mov byte ptr cs:[{dirv}], 0
        CALLN copybox
        .byte 0xc3
    h2:
        cmp byte ptr cs:[{pend}], 0
        jne h2p
        .byte 0xc3
    h2p:
        cmp byte ptr cs:[{flag}], 2
        je h3
        mov byte ptr cs:[{pend}], 0
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
        mov word ptr [{P}], ax
        mov ax, word ptr [{C}]
        mov byte ptr cs:[{lines}], 0
        .byte 0xc3
    count:
        push ax
        push bx
        push cx
        push si
        xor bx, bx
        xor cx, cx
    cn_loop:
        mov al, byte ptr es:[si]
        cmp al, 0x24
        je cn_done
        cmp al, 0x0d
        jne cn_char
        inc bl
        xor cx, cx
        add si, 2
        jmp cn_loop
    cn_char:
        test al, al
        js cn_wide
        inc cx
        inc si
        jmp cn_wrap
    cn_wide:
        add cx, word ptr [{W}]
        add si, 2
    cn_wrap:
        cmp cx, word ptr [{C}]
        jb cn_loop
        inc bl
        xor cx, cx
        cmp byte ptr es:[si], 0x0d
        jne cn_loop
        add si, 2
        jmp cn_loop
    cn_done:
        cmp bl, {ML}
        jb cn_out
        mov byte ptr cs:[{flag}], 2
    cn_out:
        pop si
        pop cx
        pop bx
        pop ax
        .byte 0xc3
    common:
        mov bx, word ptr [{S}]
        add bx, ax
        sub bx, word ptr [{C}]
        add word ptr [{P}], bx
        mov ax, word ptr [{C}]
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
        mul word ptr [{S}]
        mov bx, 80
        div bx
        mov word ptr cs:[{rows}], ax
        mov ax, word ptr [{C}]
        mov word ptr cs:[{cc}], ax
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
        mov cx, word ptr cs:[{cc}]
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
        mov cx, word ptr cs:[{cc}]
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
    pager, labels = _asm(ks, pager_src, 0, ("head_far", "common_far", "finish"))

    head_src = """
        .byte 0x2e, 0xff, 0x1e
        .word 0x%x
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
    """ % v["PTRH"]
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
        cmp byte ptr es:[si], 0x0d
        jne common
    nl:
        add si, 2
    common:
        .byte 0x2e, 0xff, 0x1e
        .word {PTRC}
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
    """.format(F=fetch, **v)
    tail_code, tl = _asm(ks, tail_src, t0, ("ascii",))
    if 37 + len(tail_code) > region - 8:
        raise ValueError("rewritten loop is %d bytes, room for %d" % (37 + len(tail_code), region - 8))
    ascii_at = tl["ascii"]
    jns = head.index(b"\x79")
    rel = ascii_at - (org + jns + 2)
    if not -128 <= rel <= 127:
        raise ValueError("ascii path out of short-jump range")
    head = head[:jns + 1] + bytes([rel & 0xFF]) + head[jns + 2:]
    code = (head + keep + tail_code).ljust(region - 8, b"\x90") + bytes(8)
    exe[base + m.start():base + m.end()] = code
    _entry_stub(ks, exe, pager, labels, seg, v["PTRH"], v["PTRC"])
    exe[base + s.start() + 3] = 0x1A                     # lookup stops at ^Z instead of "!"
    return bytes(exe)


def _entry_stub(ks, exe, pager, labels, libseg, ptrh, ptrc):
    """Give the pager a DOS block of its own, set up before the game starts.

    The EXE's entry point moves to a stub which shrinks the program's block
    (DOS hands a program all free memory) by the pager's size, allocates that
    freed top of memory to the pager, copies the pager there, points the
    draw loop's far pointers at it, zeroes the area the stub and pager were
    loaded into (a zero-filled area of the image, which the game may use as
    data later) and jumps to the original entry point.  The block holds a few
    hundred bytes of the free memory the game runs in."""
    hdr = struct.unpack_from("<14H", exe, 0)
    base = hdr[4] * 16
    img = bytes(exe[base:])
    paras = (len(pager) + 15) // 16
    stack = (hdr[7] * 16, hdr[7] * 16 + hdr[8])
    relocs = set()
    for k in range(hdr[3]):
        off, sg = struct.unpack_from("<HH", exe, hdr[12] + 4 * k)
        relocs.update((sg * 16 + off, sg * 16 + off + 1))
    msg = b"Not enough memory to start the English patch.\r\n$"

    def stub_src(poff, zlen, msg_at):
        return """
        push ax
        push bx
        push cx
        push dx
        push si
        push di
        push bp
        push ds
        push es
        mov ah, 0x4a
        mov bx, 0xffff
        int 0x21
        sub bx, {np1}
        jb fail
        mov ah, 0x4a
        int 0x21
        jb fail
        mov ah, 0x48
        mov bx, {np}
        int 0x21
        jb fail
        mov es, ax
        push cs
        pop ds
        mov si, {poff}
        xor di, di
        mov cx, {plen}
        cld
        rep movsb
        mov bp, sp
        mov dx, word ptr [bp]
        add dx, 0x10
        mov ax, dx
        add ax, {libseg}
        mov word ptr es:[0], ax
        mov word ptr es:[2], {oip}
        mov ax, dx
        add ax, {ocs}
        mov word ptr es:[4], ax
        mov word ptr es:[6], cs
        mov word ptr es:[8], {zlen}
        mov ax, word ptr es:[0]
        mov ds, ax
        mov word ptr [{ptrh}], {head}
        mov word ptr [{ptrh2}], es
        mov word ptr [{ptrc}], {common}
        mov word ptr [{ptrc2}], es
        push es
        mov ax, {finish}
        push ax
        .byte 0xcb
    fail:
        push cs
        pop ds
        mov dx, {msg_at}
        mov ah, 9
        int 0x21
        mov ax, 0x4c01
        int 0x21
        """.format(np=paras, np1=paras + 1, poff=poff, plen=len(pager), libseg=libseg,
                   oip=hdr[10], ocs=hdr[11], zlen=zlen, ptrh=ptrh, ptrh2=ptrh + 2,
                   ptrc=ptrc, ptrc2=ptrc + 2, head=labels["head_far"],
                   common=labels["common_far"], finish=labels["finish"], msg_at=msg_at)

    # the immediates are 16-bit, so the stub's size doesn't depend on them
    size = len(_asm(ks, stub_src(0x1000, 0x1000, 0x1000), 0)[0])
    stub = _asm(ks, stub_src(size + len(msg), size + len(msg) + len(pager), size), 0)[0]
    blob = stub + msg + pager
    if len(stub) != size:
        raise ValueError("entry stub size changed between passes")
    # a zero-filled, paragraph-aligned area of the image: not the stack, and no
    # relocation entry inside (the loader would write there)
    for z in re.finditer(rb"\x00{%d,}" % (len(blob) + 16), img):
        at = (z.start() + 15) & ~15
        end = at + len(blob)
        if end > z.end() or end > stack[0] and at < stack[1]:
            continue
        if any(r in relocs for r in range(at, end)):
            continue
        break
    else:
        raise ValueError("no free area in the EXE image for the entry stub")
    exe[base + at:base + end] = blob
    struct.pack_into("<HH", exe, 20, 0, at // 16)        # entry point: the stub


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
