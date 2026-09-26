"""Half-width English for Alice Soft System 1 on the PC-98 (ADV.COM patch).

System 1 draws messages on the PC-98 text layer: each Japanese character is
written into text VRAM (A000) as two cells (left/right halves of a JIS code)
and the cursor moves two cells.  The text layer shows 1-byte ASCII codes as
single 8px cells natively, so English needs no glyph work at all:

* script bytes A0-DD (legal 1-byte message characters, normally half-width
  kana that the engine converts to full-width hiragana) carry English letters
  (same assignment as System 3, see alice3_font.ONE_BYTE);
* a hook replaces the drawer's call to the kana converter: for those bytes it
  writes the ASCII code into one text cell at the cursor (with the current
  attribute), advances the cursor one cell and resumes the drawer's loop.
  Anything else goes through the original converter unchanged.

Characters outside the one-byte alphabet are written as ordinary full-width
Shift-JIS (two cells).  Patch sites are found by signature.
"""
import re

from . import alice3_font
from .text import encode_fullwidth

ORG = 0x100
ONE_BYTE = alice3_font.ONE_BYTE
BYTE_OF = alice3_font.BYTE_OF


def encode(s, fallback=encode_fullwidth):
    out = bytearray()
    for ch in s:
        ch = alice3_font._SUBST.get(ch, ch)
        for c in ch:
            out += bytes([BYTE_OF[c]]) if c in BYTE_OF else fallback(c)
    return bytes(out)


def cells(s):
    n = 0
    for ch in s:
        ch = alice3_font._SUBST.get(ch, ch)
        n += sum(1 if c in BYTE_OF else 2 for c in ch)
    return (n + 1) // 2


def build(adv):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    adv = bytearray(adv)
    data = bytes(adv)
    pat = (rb"\x26\x8a\x04\x46\xe8..\x73[\x05\x06](\xe8..)\xeb[\x06\x07]\x90?\x8a\xe0\x26\x8a\x04\x46"
           rb"\xe8..\x50\x52\xbf(..)\x8b\x1d\xff\x05\xff\x05\x8b\x0e(..)")
    hits = list(re.finditer(pat, data, re.S))
    if len(hits) != 1:
        raise ValueError("System 1 text drawer: expected 1 match, found %d" % len(hits))
    m = hits[0]
    conv_site = m.start(1)
    rel = int.from_bytes(adv[conv_site + 1:conv_site + 3], "little", signed=True)
    fn_conv = (ORG + conv_site + 3 + rel) & 0xFFFF
    xvar = int.from_bytes(m.group(2), "little")
    yvar = int.from_bytes(m.group(3), "little")
    # the loop resumes right after the drawer's two stosw and pop es
    tail = re.compile(rb"\xab\x26\x89\x95\x00\x20\x80\xc4\x80\xab\x07", re.S).search(data, m.end())
    if not tail:
        raise ValueError("System 1 text drawer: write sequence not found")
    resume = ORG + tail.end()

    base = ORG + len(adv)
    table_at = base
    table = bytes([ord(c) for c in ONE_BYTE] + [0] * (64 - len(ONE_BYTE)))
    code_at = table_at + len(table)
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    # assemble in two parts so both far targets are exact near jumps
    part1 = """
        cmp al, 0xA0
        jb orig
        cmp al, {last}
        ja orig
        pop bx
        push ax
        push cx
        push di
        push es
        mov bx, ax
        xor bh, bh
        sub bl, 0xA0
        mov bl, byte ptr [bx + {table}]
        mov ax, word ptr [{y}]
        mov cx, 0xA0
        mul cx
        mov di, word ptr [{x}]
        add di, di
        add di, ax
        mov ax, 0xA000
        mov es, ax
        xor bh, bh
        mov word ptr es:[di], bx
        mov word ptr es:[di + 0x2000], dx
        inc word ptr [{x}]
        pop es
        pop di
        pop cx
        pop ax
    """.format(last=0xA0 + len(ONE_BYTE) - 1, table=table_at, x=xvar, y=yvar)
    # "orig" sits after a 3-byte placeholder that becomes the jump back into
    # the drawer; after it comes the jump to the original converter.
    code = bytes(ks.asm(part1 + " nop; nop; nop; orig:", code_at)[0])
    jmp_resume_at = code_at + len(code) - 3
    code = code[:-3] + b"\xe9" + ((resume - (jmp_resume_at + 3)) & 0xFFFF).to_bytes(2, "little")
    orig_at = code_at + len(code)
    code += b"\xe9" + ((fn_conv - (orig_at + 3)) & 0xFFFF).to_bytes(2, "little")

    blob = table + code
    sp = re.search(rb"\xb8(..)\x05(..)\x8b\xe0|\xb8(..)\x8b\xe0|\xbc(..)", data[:0x40], re.S)
    resize = re.search(rb"\xbb..\xc1\xeb\x04\x81\xc3(..)\xb4\x4a\xcd\x21|\xbb..\x81\xc3(..)\xc1\xeb\x04(?:\x8b\xf3\x8b\xfb)?\xb4\x4a\xcd\x21", data, re.S)
    if not sp or not resize:
        raise ValueError("stack/memory setup not found")
    if sp.group(3) is not None:
        off, val = sp.start(3), int.from_bytes(sp.group(3), "little")
        sp_top = val
    elif sp.group(4) is not None:
        off, val = sp.start(4), int.from_bytes(sp.group(4), "little")
        sp_top = val
    else:
        off, val = sp.start(2), int.from_bytes(sp.group(2), "little")
        sp_top = int.from_bytes(sp.group(1), "little") + val
    if base + len(blob) >= sp_top + 0x1000 - 0x400:  # the stack moves up 4 KB below
        raise ValueError("no room for the hook below the stack")
    adv[off:off + 2] = (val + 0x1000).to_bytes(2, "little")
    g = 1 if resize.group(1) is not None else 2
    old = int.from_bytes(resize.group(g), "little")
    adv[resize.start(g):resize.start(g) + 2] = (old + (0x100 if g == 1 else 0x1000)).to_bytes(2, "little")
    adv[conv_site + 1:conv_site + 3] = ((code_at - (ORG + conv_site + 3)) & 0xFFFF).to_bytes(2, "little")
    return bytes(adv + blob)
