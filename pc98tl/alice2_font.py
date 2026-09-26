"""Half-width English for Alice Soft System 2 on the PC-98 (ADV.COM patch).

Two English letters are packed into one unused Shift-JIS code (see
pc98tl/packfont.py); the engine draws that code as one 16px cell whose left
and right halves are the two letters' 8x16 glyphs from the engine's own ANK
font table (loaded at A100:0000 at startup).  Script text stays at about one
byte per letter and the engine's layout logic is untouched.

Two engine shapes exist, both located by byte signature:
  fetch   (Dalk, Prostudent G, Ayumi-chan, Super D.P.S): the drawer converts
          SJIS->JIS, calls a glyph-fetch routine that fills a 32-byte buffer
          from the CG ROM, then draws the buffer.  Hooks: the converter call
          (records the two letters) and the fetch call (fills the buffer).
  direct  (Dr. Stop!): the 16px draw routine reads the CG ROM and writes video
          memory itself.  Hooks: the converter call and the 16px draw call,
          which draws the composed glyph with the same bolding transform.

The hook code goes just above the old stack top (the file is zero-padded up
to it: uninitialised data can follow the file) and the stack moves up by 4 KB
past it, with the DOS memory block grown to match; nothing else changes size,
so the patch stays memory-neutral.
"""
import re

from . import dosmem, packfont

ORG = 0x100


def _one(data, pattern, what):
    hits = list(re.finditer(pattern, data, re.S))
    if len(hits) != 1:
        raise ValueError("%s: expected 1 match, found %d" % (what, len(hits)))
    return hits[0]


def _target(adv, call_off):
    rel = int.from_bytes(adv[call_off + 1:call_off + 3], "little", signed=True)
    return (ORG + call_off + 3 + rel) & 0xFFFF


def _rel(frm_next, to):
    return (to - frm_next) & 0xFFFF


def font_px(adv):
    """Message font size in dots (16, or 24 for engines like Dr. Stop! whose
    default is the 24-dot mode): the drawer picks its routine from a size
    variable that startup loads from a default ("mov ax,[default] / mov
    [size],ax")."""
    m = re.search(rb"\x83\x3e(..)\x10\x75\x03\xe8..\x83\x3e\1\x18", adv, re.S)
    if not m:
        return 16
    size = m.group(1)
    d = re.search(rb"\xa1(..)\xa3" + re.escape(size), adv, re.S)
    if not d:
        return 16
    at = int.from_bytes(d.group(1), "little") - ORG
    return int.from_bytes(adv[at:at + 2], "little") if 0 <= at < len(adv) - 1 else 16


def build(adv, room=0x1000):
    """room: how far the stack moves up (the space above the hook, which
    relocated text can also use)."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    adv = bytearray(adv)
    data = bytes(adv)
    conv = _one(data, rb"\xe8..\x73\x05\xe8..\xeb\x06\x8a\xe0\x26\x8a\x04\x46(\xe8..)", "converter call")
    conv_site = conv.start(1)
    fn_conv = _target(adv, conv_site)
    if not re.search(rb"\xb8\x00\xa1\x8e", data):  # loaded and read by the engine itself
        raise ValueError("engine does not use the ANK font table at A100")

    fetch = list(re.finditer(rb"\x86\xe0\x2c\x20(\xe8..)", data, re.S))
    glyph_buf = None
    if len(fetch) == 1:
        glyph_site = fetch[0].start(1)
        fn_glyph = _target(adv, glyph_site)
        head = data[fn_glyph - ORG:fn_glyph - ORG + 0x20]
        buf = re.search(rb"\xe6\xa3\x86\xc4\xe6\xa1(?:\x86\xc4)?\xbf(..)", head, re.S)
        if buf:                          # fetch into a buffer, drawn afterwards
            shape = "fetch"
            glyph_buf = int.from_bytes(buf.group(1), "little")
        elif re.search(rb"\xe6\xa3\x86\xc4\xe6\xa1\xb0\xc0\xe6\x7c", head):
            shape = "direct"             # the called routine reads the ROM and draws itself
        else:
            raise ValueError("glyph routine: unknown shape")
    else:
        shape = "direct"
        m = _one(data, rb"\x86\xe0\x2c\x20\x83\x3e..\x10\x75\x03(\xe8..)", "16px draw call")
        glyph_site = m.start(1)
        fn_glyph = _target(adv, glyph_site)

    # Direct engines can also draw in a 24-dot mode (Dr. Stop!'s message
    # windows): a second routine scales each 16-dot ROM row to 24 dots.  Its
    # scaling block (from the row in AH:AL to the three stosb and the doubled
    # row) is reused verbatim on the composed rows.
    big_site = scale = None
    if shape == "direct":
        m24 = re.compile(rb"\x83\x3e..\x18\x75\x03(\xe8..)", re.S).search(data, glyph_site, glyph_site + 0x20)
        if m24:
            big_site = m24.start(1)
            fn_big = _target(adv, big_site)
            body = data[fn_big - ORG:fn_big - ORG + 0x100]
            sb = re.match(rb"\x51\x57\x06\xe6\xa3\x86\xc4\xe6\xa1\xb0\xc0\xe6\x7c\xb0\x0b\xe6\x68\xb8\x00\xa8\x8e\xc0"
                          rb"\x33\xc9\x8a\xc1\x0c\x20\xe6\xa5\xe4\xa9\x8a\xe0\x8a\xc1\xe6\xa5\xe4\xa9"
                          rb"(.+?)\x41\x83\xf9\x10", body, re.S)
            # the block's only jump is its final "jb" over the doubled row to
            # the loop's "inc cx", which follows the block in the copy too
            if not sb or len(sb.group(1)) > 0xC0 or not sb.group(1).endswith(b"\x83\xc7\x4d"):
                raise ValueError("24-dot draw routine: unknown shape")
            scale = sb.group(1)

    # Every program sets its own stack; engines also shrink their DOS block
    # (a program that doesn't owns all memory).  The hook goes just above the
    # old stack top, since the program's uninitialised data can follow the
    # file, and the stack moves up 4 KB past it.
    sp = re.search(rb"\xb8(..)\x05(..)\x8b\xe0|\xb8(..)\x8b\xe0", data[:0x40], re.S)
    if sp is None:
        raise ValueError("stack setup not found")
    if sp.group(3) is not None:          # mov ax,imm ; mov sp,ax
        sp_val = int.from_bytes(sp.group(3), "little")
        sp_off, new_sp = sp.start(3), sp_val + room
    else:                                # mov ax,imm ; add ax,imm ; mov sp,ax
        sp_val = int.from_bytes(sp.group(1), "little") + int.from_bytes(sp.group(2), "little")
        sp_off, new_sp = sp.start(2), int.from_bytes(sp.group(2), "little") + room
    file_end = ORG + len(adv)
    base = max(file_end, sp_val)
    flag, c1, c2, alpha = base, base + 1, base + 2, base + 3
    table = bytes(ord(c) for c in packfont.ALPHABET)
    code_at = alpha + len(table) + ((alpha + len(table)) & 1)
    ks = Ks(KS_ARCH_X86, KS_MODE_16)

    conv_asm = """
        cmp ah, 0xEB
        jae packed
        cmp ah, 0x80
        je packed
        mov byte ptr [{flag}], 0
        jmp far_exit
    packed:
        push bx
        push dx
        mov bl, al
        mov al, ah
        cmp al, 0x80
        jne l1
        xor al, al
        jmp l2
    l1:
        sub al, 0xEA
    l2:
        xor ah, ah
        mov dx, 255
        mul dx
        xor bh, bh
        dec bx
        add ax, bx
        xor dx, dx
        mov bx, {A}
        div bx
        mov bx, ax
        mov al, byte ptr [bx + {alpha}]
        mov byte ptr [{c1}], al
        mov bx, dx
        mov al, byte ptr [bx + {alpha}]
        mov byte ptr [{c2}], al
        mov byte ptr [{flag}], 1
        mov ax, 0x2121
        pop dx
        pop bx
        .byte 0xc3
    far_exit:
    """.format(flag=flag, c1=c1, c2=c2, alpha=alpha, A=packfont.A)
    conv_code = bytes(ks.asm(conv_asm, code_at)[0])
    conv_code += b"\xe9" + _rel(code_at + len(conv_code) + 3, fn_conv).to_bytes(2, "little")

    glyph_at = code_at + len(conv_code)
    if shape == "fetch":
        glyph_asm = """
            cmp byte ptr [{flag}], 0
            jne build
            jmp far_exit
        build:
            push si
            push di
            push ds
            push es
            push cx
            push ax
            push bx
            push cs
            pop es
            mov di, {buf}
            xor bx, bx
            mov bl, byte ptr [{c1}]
            mov si, bx
            shl si, 4
            mov bl, byte ptr [{c2}]
            shl bx, 4
            mov ax, 0xA100
            mov ds, ax
            mov cx, 16
        row:
            mov al, byte ptr [si]
            stosb
            mov al, byte ptr [bx]
            stosb
            inc si
            inc bx
            loop row
            pop bx
            pop ax
            pop cx
            pop es
            pop ds
            pop di
            pop si
            .byte 0xc3
        far_exit:
        """.format(flag=flag, c1=c1, c2=c2, buf=glyph_buf)
    else:
        # Same row transform as the engine's own 16px routine: left byte
        # L | L>>1, right byte R | R>>1 | L<<7, written with the GRCG in tile mode.
        glyph_asm = """
            cmp byte ptr [{flag}], 0
            jne build
            jmp far_exit
        build:
            push cx
            push di
            push es
            push si
            push ds
            push bx
            push dx
            xor bx, bx
            mov bl, byte ptr [{c1}]
            mov si, bx
            shl si, 4
            mov bl, byte ptr [{c2}]
            shl bx, 4
            mov al, 0xc0
            out 0x7c, al
            mov ax, 0xA800
            mov es, ax
            mov ax, 0xA100
            mov ds, ax
            mov cx, 16
        row:
            mov al, byte ptr [si]
            mov ah, al
            shr al, 1
            or al, ah
            stosb
            mov dl, byte ptr [bx]
            mov al, dl
            shl ah, 7
            or al, ah
            shr dl, 1
            or al, dl
            stosb
            add di, 0x4e
            inc si
            inc bx
            loop row
            xor ax, ax
            out 0x7c, al
            pop dx
            pop bx
            pop ds
            pop si
            pop es
            pop di
            pop cx
            .byte 0xc3
        far_exit:
        """.format(flag=flag, c1=c1, c2=c2)
    glyph_code = bytes(ks.asm(glyph_asm, glyph_at)[0])
    glyph_code += b"\xe9" + _rel(glyph_at + len(glyph_code) + 3, fn_glyph).to_bytes(2, "little")

    big_code = b""
    big_at = glyph_at + len(glyph_code)
    if scale is not None:
        # cmp byte [flag],0 / jne build / jmp <original 24-dot routine>
        head = b"\x80\x3e" + flag.to_bytes(2, "little") + b"\x00\x75\x03"
        orig_jmp = b"\xe9" + _rel(big_at + len(head) + 3, fn_big).to_bytes(2, "little")
        setup_at = big_at + len(head) + 3
        setup = bytes(ks.asm("""
            push cx
            push di
            push es
            push si
            push ds
            push bx
            push dx
            push bp
            xor bx, bx
            mov bl, byte ptr [{c1}]
            mov si, bx
            shl si, 4
            mov bl, byte ptr [{c2}]
            mov bp, bx
            shl bp, 4
            mov al, 0xc0
            out 0x7c, al
            mov ax, 0xA800
            mov es, ax
            mov ax, 0xA100
            mov ds, ax
            xor cx, cx
        """.format(c1=c1, c2=c2), setup_at)[0])
        row_at = setup_at + len(setup)
        row = b"\x8a\x24" + b"\x3e\x8a\x46\x00" + b"\x46\x45"   # mov ah,[si] / mov al,ds:[bp+0] / inc si / inc bp
        loop_at = row_at + len(row) + len(scale)
        tail = b"\x41\x83\xf9\x10\x73\x03"                        # inc cx / cmp cx,16 / jae done
        tail += b"\xe9" + _rel(loop_at + len(tail) + 3, row_at).to_bytes(2, "little")
        tail += bytes(ks.asm("""
            xor ax, ax
            out 0x7c, al
            pop bp
            pop dx
            pop bx
            pop ds
            pop si
            pop es
            pop di
            pop cx
            .byte 0xc3
        """, loop_at + len(tail))[0])
        big_code = head + orig_jmp + setup + row + scale + tail

    blob = bytearray(b"\0\0\0" + table).ljust(code_at - base, b"\0") + conv_code + glyph_code + big_code
    end = base + len(blob)

    if end >= sp_val + room - 0x400:   # the stack moves up by `room`, above the hook
        raise ValueError("no room for the hook below the stack")
    if sp_val + room >= 0xFFF0:
        raise ValueError("stack cannot move up 4 KB")
    adv[sp_off:sp_off + 2] = new_sp.to_bytes(2, "little")
    dosmem.grow_block(adv, data, room)
    adv[conv_site + 1:conv_site + 3] = _rel(ORG + conv_site + 3, code_at).to_bytes(2, "little")
    adv[glyph_site + 1:glyph_site + 3] = _rel(ORG + glyph_site + 3, glyph_at).to_bytes(2, "little")
    if big_code:
        adv[big_site + 1:big_site + 3] = _rel(ORG + big_site + 3, big_at).to_bytes(2, "little")
    return bytes(adv) + b"\0" * (base - file_end) + bytes(blob)
