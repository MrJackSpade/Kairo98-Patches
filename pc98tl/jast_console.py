"""Page instead of scroll in JAST's text-layer message window (Tenshi-tachi
no Gogo V and relatives): the message box is a window on the PC-98 text
layer (a window library: left/top/right/bottom, cursor column/row, VRAM
position), and a line past its bottom scrolls the window up.  English
outgrows the Japanese, so the scroll calls in the window's putchar are
pointed at a pager: it waits for a left click (mouse port 7FD9 bit 7) or a
key, clears the window (the library's own scroll, once per row) and starts
again at its top left.  The pager sits in a zero-filled area of the code
segment that the game never touches (checked in np21w save states;
game.json "cave").
"""
import re
import struct

# the window scroll: move the rectangle up one row, blank the bottom row,
# cursor to the bottom row's left, recompute the VRAM position
SCROLL = re.compile(
    rb"\x55\x8b\xec\x56\xa1(?P<bottom>..)\x40\x8b\xf0\xa1(?P<top>..)\x40\x50\xa1(?P<left>..)\x40\x50\x56"
    rb"\xa1..\x40\x50\xa1..\x40\x40\x50\xa1..\x40\x50\xe8..\x83\xc4\x0c\xa1..\x2b\x06..\x40\x50\xe8..\x59"
    rb"\xc7\x06(?P<flag>..)\x00\x00\xa1..\xa3(?P<col>..)\xa1..\xa3(?P<row>..)\xe8(?P<rel>..)\x5e\x5d\xc3", re.S)


def install(exe, cave):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm
    exe = bytearray(exe)
    base = struct.unpack_from("<H", exe, 8)[0] * 16
    img = bytes(exe[base:])
    m = SCROLL.search(img)
    if not m:
        raise ValueError("message window scroll not found")
    w = {k: struct.unpack("<H", m.group(k))[0] for k in ("bottom", "top", "left", "col", "row")}
    scroll = m.start()
    recompute = (m.end() - 3 + struct.unpack("<h", m.group("rel"))[0]) & 0xFFFF
    calls = [c.start() for c in re.finditer(rb"\xe8(..)", img[:0x10000], re.S)
             if (c.start() + 3 + struct.unpack("<h", c.group(1))[0]) & 0xFFFF == scroll]
    if not calls:
        raise ValueError("no calls to the window scroll")
    src = """
        push ax
        push bx
        push cx
        push dx
        mov dx, 0x7fd9
    fl:
        mov ah, 1
        int 0x18
        cmp bh, 0
        je w0
        mov ah, 0
        int 0x18
        jmp fl
    w0:
        in al, dx
        test al, 0x80
        jz w0
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
        jmp clr
    wkey:
        mov ah, 0
        int 0x18
    clr:
        mov cx, word ptr [{bottom}]
        sub cx, word ptr [{top}]
        inc cx
    c1:
        push cx
        CALLN 0x{scroll:x}
        pop cx
        loop c1
        mov ax, word ptr [{left}]
        mov word ptr [{col}], ax
        mov ax, word ptr [{top}]
        mov word ptr [{row}], ax
        CALLN 0x{recompute:x}
        pop dx
        pop cx
        pop bx
        pop ax
        .byte 0xc3
    """.format(scroll=scroll, recompute=recompute, **w)
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    code, _ = _asm(ks, src, cave)
    if b"\x66" in code:
        raise ValueError("32-bit prefix in the pager")
    if any(exe[base + cave:base + cave + len(code)]):
        raise ValueError("pager area is not free")
    exe[base + cave:base + cave + len(code)] = code
    for c in calls:
        struct.pack_into("<h", exe, base + c + 1, cave - (c + 3))
    return bytes(exe)
