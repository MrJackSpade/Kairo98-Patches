"""Half-width English for Alice Soft System 1 on the PC-98 (ADV.COM patch).

System 1 draws messages on the PC-98 text layer: each Japanese character is
written into text VRAM (A000) as two cells (left/right halves of a JIS code).
The text layer shows 1-byte ASCII codes as single 8px cells natively, so
English needs no glyph work at all:

* script bytes A0-DD (legal 1-byte message characters, normally half-width
  kana that the engine converts to full-width hiragana) carry English letters
  (same assignment as System 3, see alice3_font.ONE_BYTE);
* a hook replaces the drawer's call to the kana converter: for those bytes it
  writes the ASCII code into one text cell at the cursor (with the current
  attribute), advances the cursor and resumes the drawer's loop.  Anything
  else goes through the original converter unchanged.

Two cursor units exist, both found by signature:
  cell  (Intruder): the cursor counts text cells and steps 2 per character;
        a letter steps 1.
  char  (D.P.S SG): the cursor counts full-width characters; letters fill the
        left and right halves of a character cell in turn (a half flag, reset
        whenever the engine moves the cursor itself), and a full-width
        character after a lone left half starts in the next cell.

Characters outside the one-byte alphabet are written as ordinary full-width
Shift-JIS (two cells).
"""
import re

from . import alice3_font, dosmem
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
           rb"(\xe8..)\x50\x52\xbf(..)\x8b\x1d\xff\x05(\xff\x05)?\x8b\x0e(..)")
    hits = list(re.finditer(pat, data, re.S))
    if len(hits) != 1:
        raise ValueError("System 1 text drawer: expected 1 match, found %d" % len(hits))
    m = hits[0]
    unit = "cell" if m.group(4) else "char"
    conv_site, jis_site = m.start(1), m.start(2)

    def target(site):
        rel = int.from_bytes(adv[site + 1:site + 3], "little", signed=True)
        return (ORG + site + 3 + rel) & 0xFFFF
    fn_conv, fn_jis = target(conv_site), target(jis_site)
    xvar = int.from_bytes(m.group(3), "little")
    yvar = int.from_bytes(m.group(5), "little")
    # the loop resumes right after the drawer's two stosw and pop es
    tail = re.compile(rb"\xab\x26\x89\x95\x00\x20\x80\xc4\x80\xab\x07", re.S).search(data, m.end())
    if not tail:
        raise ValueError("System 1 text drawer: write sequence not found")
    resume = ORG + tail.end()

    # Stack: the hook goes just above the old stack top (uninitialised data
    # can follow the file, so the file end is not free memory) and the stack
    # moves up 4 KB past it.
    # D.P.S SG: the stack sits at the top of the memory block, which is sized
    # as (end >> 4) + paragraphs; growing the block moves the stack with it.
    blk = re.match(rb"\x8c\xc8\x8e\xd0\xbb(..)\xb1\x04\xd3\xeb\x81\xc3(..)\xb4\x4a\xcd\x21"
                   rb"\x8b\xc3\xd3\xe0\x48\x48\x8b\xe0", data, re.S)
    if blk:
        paras = int.from_bytes(blk.group(2), "little")
        sp_top = ((int.from_bytes(blk.group(1), "little") >> 4) + paras) << 4
    else:
        sp = re.search(rb"\xb8(..)\x05(..)\x8b\xe0|\xb8(..)\x8b\xe0|\xbc(..)", data[:0x40], re.S)
        if not sp:
            raise ValueError("stack setup not found")
        if sp.group(3) is not None:
            off, val = sp.start(3), int.from_bytes(sp.group(3), "little")
            sp_top = val
        elif sp.group(4) is not None:
            off, val = sp.start(4), int.from_bytes(sp.group(4), "little")
            sp_top = val
        else:
            off, val = sp.start(2), int.from_bytes(sp.group(2), "little")
            sp_top = int.from_bytes(sp.group(1), "little") + val

    file_end = ORG + len(adv)
    base = max(file_end, sp_top)
    table_at = base
    table = bytes([ord(c) for c in ONE_BYTE] + [0] * (64 - len(ONE_BYTE)))
    half, lastx = table_at + len(table), table_at + len(table) + 1   # "char" engines only
    code_at = lastx + 2 + ((lastx + 2) & 1)
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    head = """
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
        push dx
        mov ax, word ptr [{y}]
        mov cx, 0xA0
        mul cx
        pop dx
        mov di, word ptr [{x}]
        add di, di
    """
    if unit == "cell":
        body = """
        add di, ax
        mov ax, 0xA000
        mov es, ax
        xor bh, bh
        mov word ptr es:[di], bx
        mov word ptr es:[di + 0x2000], dx
        inc word ptr [{x}]
        """
    else:
        body = """
        add di, di
        add di, ax
        mov ax, word ptr [{x}]
        cmp ax, word ptr [{lastx}]
        je same
        mov byte ptr [{half}], 0
    same:
        cmp byte ptr [{half}], 0
        je left
        add di, 2
    left:
        mov ax, 0xA000
        mov es, ax
        xor bh, bh
        mov word ptr es:[di], bx
        mov word ptr es:[di + 0x2000], dx
        xor byte ptr [{half}], 1
        jnz keep
        inc word ptr [{x}]
    keep:
        mov ax, word ptr [{x}]
        mov word ptr [{lastx}], ax
        """
    tailcode = """
        pop es
        pop di
        pop cx
        pop ax
    """
    part1 = (head + body + tailcode).format(last=0xA0 + len(ONE_BYTE) - 1, table=table_at,
                                            x=xvar, y=yvar, half=half, lastx=lastx)
    # "orig" sits after a 3-byte placeholder that becomes the jump back into
    # the drawer; after it comes the jump to the original converter.
    code = bytes(ks.asm(part1 + " nop; nop; nop; orig:", code_at)[0])
    jmp_resume_at = code_at + len(code) - 3
    code = code[:-3] + b"\xe9" + ((resume - (jmp_resume_at + 3)) & 0xFFFF).to_bytes(2, "little")
    orig_at = code_at + len(code)
    code += b"\xe9" + ((fn_conv - (orig_at + 3)) & 0xFFFF).to_bytes(2, "little")
    jis_at = None
    if unit == "char":
        # before a full-width character: step past a half-filled cell
        jis_at = code_at + len(code)
        jis = bytes(ks.asm("""
            push ax
            mov ax, word ptr [{x}]
            cmp ax, word ptr [{lastx}]
            jne clear
            cmp byte ptr [{half}], 0
            je clear
            inc word ptr [{x}]
        clear:
            mov byte ptr [{half}], 0
            pop ax
        """.format(x=xvar, lastx=lastx, half=half), jis_at)[0])
        jis += b"\xe9" + ((fn_jis - (jis_at + len(jis) + 3)) & 0xFFFF).to_bytes(2, "little")
        code += jis

    blob = table + b"\0" * (code_at - (table_at + len(table))) + code
    if base + len(blob) >= sp_top + 0x1000 - 0x400:  # the stack moves up 4 KB, above the hook
        raise ValueError("no room for the hook below the stack")
    if sp_top + 0x1000 >= 0xFFF0:
        raise ValueError("stack cannot move up 4 KB")
    if not blk:
        adv[off:off + 2] = (val + 0x1000).to_bytes(2, "little")
    dosmem.grow_block(adv, data)   # D.P.S SG: this also moves the stack
    adv[conv_site + 1:conv_site + 3] = ((code_at - (ORG + conv_site + 3)) & 0xFFFF).to_bytes(2, "little")
    if jis_at is not None:
        adv[jis_site + 1:jis_site + 3] = ((jis_at - (ORG + jis_site + 3)) & 0xFFFF).to_bytes(2, "little")
    return bytes(adv) + b"\0" * (base - file_end) + bytes(blob)
