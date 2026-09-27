"""A page-break pager for engines that print their messages through DOS
(int 21h function 40h to the screen), such as JAST's text-layer engines.

The patched EXE's entry stub (pc98tl/illusion_font._entry_stub) gives the
pager a small DOS block of its own and hooks int 21h there before the game
starts:

* a write to the screen (handle 1 or 2) is passed on piece by piece; at each
  MARKER byte in it the pager waits for a left click (mouse port 7FD9 bit 7)
  or a key, and the marker itself is not printed;
* the program's exit call (function 4Ch) puts the old vector back first, so
  nothing is left pointing into the freed block;
* everything else goes straight to DOS.

The English script puts MARKER before each box-full of lines, so a long
message waits instead of scrolling its start out of the box.  No engine code
is changed.
"""
MARKER = b"`"


def install(exe):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm, _entry_stub
    import struct
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    # data: +0 LIB (unused) +2 OIP +4 OCS +6 ZSEG +8 ZLEN (set by the stub), +10 old int 21h
    src = """
        .word 0, 0, 0, 0, 0
        .word 0, 0
        .word 0, 0
    handler:
        cmp ah, 0x4c
        jne h1
        push ax
        push dx
        push ds
        lds dx, dword ptr cs:[10]
        mov ax, 0x2521
        pushf
        .byte 0x2e, 0xff, 0x1e
        .word 10
        pop ds
        pop dx
        pop ax
        jmp chain
    h1:
        cmp ah, 0x40
        jne chain
        cmp bx, 2
        ja chain
        jcxz chain
        push di
        push es
        push cx
        push ds
        pop es
        mov di, dx
        mov al, {mark}
        cld
        repne scasb
        pop cx
        pop es
        pop di
        jne chain
        jmp paged
    chain:
        .byte 0x2e, 0xff, 0x2e
        .word 10
    paged:
        push bx
        push cx
        push dx
        push si
        push di
        push bp
        mov si, dx
        mov bp, cx
        mov word ptr cs:[14], cx
    p1:
        mov di, si
        mov cx, bp
        jcxz pdone
    p2:
        cmp byte ptr [di], {mark}
        je p3
        inc di
        loop p2
    p3:
        mov cx, di
        sub cx, si
        jcxz p4
        push cx
        mov dx, si
        mov ah, 0x40
        pushf
        .byte 0x2e, 0xff, 0x1e
        .word 10
        pop cx
    p4:
        add si, cx
        sub bp, cx
        jz pdone
        inc si
        dec bp
        push dx
        push bx
        mov dx, 0x7fd9
    w1:
        mov ah, 1
        int 0x18
        cmp bh, 0
        jne wkey
        in al, dx
        test al, 0x80
        jnz w1
    w2:
        in al, dx
        test al, 0x80
        jz w2
        jmp wdone
    wkey:
        mov ah, 0
        int 0x18
    wdone:
        pop bx
        pop dx
        jmp p1
    pdone:
        mov ax, word ptr cs:[14]
        pop bp
        pop di
        pop si
        pop dx
        pop cx
        pop bx
        clc
        .byte 0xca, 0x02, 0x00
    unused:
        .byte 0xcb
    finish:
        mov ax, 0x3521
        int 0x21
        mov word ptr cs:[10], bx
        mov word ptr cs:[12], es
        push cs
        pop ds
        mov dx, {handler}
        mov ax, 0x2521
        int 0x21
        mov es, word ptr cs:[6]
        xor di, di
        mov cx, word ptr cs:[8]
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
        .word 2
    """
    mark = MARKER[0]
    blob, labels = _asm(ks, src.format(mark=mark, handler=0), 0, ("handler", "unused", "finish"))
    blob, labels = _asm(ks, src.format(mark=mark, handler=labels["handler"]), 0,
                        ("handler", "unused", "finish"))
    exe = bytearray(exe)
    _entry_stub(ks, exe, blob, {"head_far": labels["handler"], "common_far": labels["unused"],
                                "finish": labels["finish"]}, 0, None, None)
    return bytes(exe)
