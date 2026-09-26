"""ADV.COM patch for Dalk: draw packed half-width English (see pc98tl/packfont.py).

Glyph path in ADV.COM (addresses are CS offsets, file offset + 0x100):
  482e  call 1a19        lead byte?  (0x80-0x9F, 0xE0-0xFF => 2-byte)
  483e  call 19eb        SJIS -> JIS            <- hooked: HOOK_CONV
  485f  call 4931        JIS -> 16x16 glyph at [4987] from the CG ROM
                                                <- hooked: HOOK_GLYPH
  then the normal 16px cell drawer (419b/40f6/4038 by font size).
The engine loads the 8x16 ANK font for codes 00-7F into A100:0000 at startup
(routine at 4c5f), so HOOK_GLYPH composes [left=ANK(c1), right=ANK(c2)] rows
from there.

The scenario page pool (segment [5560], originally 0xC00 paragraphs) is grown
so longer English pages plus page-called subroutine pages fit.

The hook code is appended after the end of the file.  Originally the stack
started at A8F6, right after the file; we move it to B8F6 and grow the DOS
memory block (int 21h/4Ah at 9f1e) by 0x100 paragraphs to keep it valid.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from pc98tl import packfont  # noqa: E402

ORG = 0x100
EXPECT_SIZE = 41062

SITE_CONV = 0x483E    # e8 aa d1  call 19eb
SITE_GLYPH = 0x485F   # e8 cf 00  call 4931
FN_CONV = 0x19EB
FN_GLYPH = 0x4931
GLYPH_BUF = 0x4987
SP_IMM = 0x10A        # mov ax, a8f6
RESIZE_IMM = 0x9F1C   # add bx, 00a0
POOL_IMM = 0x9FDC     # add ax, 0c00   size (paragraphs) of the scenario page pool
POOL_PARAS = 0x2000   # 48 KB -> 128 KB: caller pages stay resident during page calls


# Japanese strings hard-coded in ADV.COM: (CS address, bytes available).
# The text drawer stops at the first byte < 0x80 that isn't a space, so a
# replacement must leave room for one terminator byte.
EXE_STRINGS = [
    (0x547D, 24),   # 動詞，名詞が存在しません   (no verbs/nouns - script error)
    (0x5496, 14),   # やっぱりやめる             ("never mind" item in verb/object menus)
    (0x54A5, 32),   # 【★ドライブが書き込み禁止です】   (floppy only)
    (0x54C6, 42),   # 【★ドライブに★ディスクを入れてください】 (floppy only)
]


def exe_strings(adv):
    """[(address, max_bytes, japanese)] for strings.json."""
    out = []
    for addr, n in EXE_STRINGS:
        out.append((addr, n, adv[addr - ORG:addr - ORG + n].decode("cp932", "replace")))
    return out


def apply_exe_strings(adv, texts, encode):
    """texts: {address: english}.  Returns (patched bytes, warnings)."""
    adv = bytearray(adv)
    warn = []
    for addr, n in EXE_STRINGS:
        if addr not in texts:
            continue
        enc = encode(texts[addr])
        if len(enc) > n:
            warn.append("ADV.COM string %04x: %d bytes, only %d fit (truncated)" % (addr, len(enc), n))
            enc = enc[:n - (n % 2)]
        o = addr - ORG
        term = adv[o + n]  # original terminator byte
        adv[o:o + n] = enc.ljust(n, bytes([term]))
    return bytes(adv), warn


def _rel(frm_next, to):
    return (to - frm_next) & 0xFFFF


def build(adv, enlarge_pool=False):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    adv = bytearray(adv)
    if len(adv) != EXPECT_SIZE:
        raise ValueError("unexpected ADV.COM size %d" % len(adv))
    f = lambda a: a - ORG  # noqa: E731
    assert adv[f(SITE_CONV):f(SITE_CONV) + 3] == b"\xe8\xaa\xd1"
    assert adv[f(SITE_GLYPH):f(SITE_GLYPH) + 3] == b"\xe8\xcf\x00"
    assert adv[f(SP_IMM):f(SP_IMM) + 2] == b"\xf6\xa8"
    assert adv[f(RESIZE_IMM):f(RESIZE_IMM) + 2] == b"\xa0\x00"

    base = ORG + len(adv)
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    # Layout: [data][hook_conv][hook_glyph]
    data_flag = base
    data_c1 = base + 1
    data_c2 = base + 2
    alpha = base + 3
    table = bytes(ord(c) for c in packfont.ALPHABET)
    code_start = alpha + len(table)
    if code_start & 1:
        code_start += 1

    conv_body = """
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
    """.format(flag=data_flag, c1=data_c1, c2=data_c2, alpha=alpha, A=packfont.A)
    enc, _ = ks.asm(conv_body, code_start)
    conv = bytes(enc)
    # tail-jump to the original converter
    conv += b"\xe9" + _rel(code_start + len(conv) + 3, FN_CONV).to_bytes(2, "little")

    glyph_start = code_start + len(conv)
    glyph_body = """
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
    """.format(flag=data_flag, c1=data_c1, c2=data_c2, buf=GLYPH_BUF)
    enc, _ = ks.asm(glyph_body, glyph_start)
    glyph = bytes(enc)
    glyph += b"\xe9" + _rel(glyph_start + len(glyph) + 3, FN_GLYPH).to_bytes(2, "little")

    blob = bytearray(b"\0\0\0" + table)
    blob = blob.ljust(code_start - base, b"\0")
    blob += conv + glyph
    end = base + len(blob)
    assert end < 0xA8F6 - 0x100, "hook too large"

    # redirect the two calls
    adv[f(SITE_CONV) + 1:f(SITE_CONV) + 3] = _rel(SITE_CONV + 3, code_start).to_bytes(2, "little")
    adv[f(SITE_GLYPH) + 1:f(SITE_GLYPH) + 3] = _rel(SITE_GLYPH + 3, glyph_start).to_bytes(2, "little")
    # stack B8F6, memory block +0x100 paragraphs
    adv[f(SP_IMM):f(SP_IMM) + 2] = (0xB8F6).to_bytes(2, "little")
    adv[f(RESIZE_IMM):f(RESIZE_IMM) + 2] = (0x01A0).to_bytes(2, "little")
    if enlarge_pool:
        adv[f(POOL_IMM):f(POOL_IMM) + 2] = POOL_PARAS.to_bytes(2, "little")
    return bytes(adv + blob)


if __name__ == "__main__":
    src = open(sys.argv[1], "rb").read()
    out = build(src)
    open(sys.argv[2], "wb").write(out)
    print("ADV.COM %d -> %d bytes" % (len(src), len(out)))
