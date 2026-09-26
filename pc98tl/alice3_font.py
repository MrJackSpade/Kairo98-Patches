"""Half-width English for Alice Soft System 3 on the PC-98 (ADV.COM patch).

System 3 hands every character code to the AGS graphics driver, which draws
NEC "row 9" codes (Shift-JIS 85xx) as 8x16 half-width glyphs straight from the
kanji ROM.  So the patch only has to
  1. rewrite ADV.COM's half-width-kana -> full-width table so the kana bytes
     A0-DF become row-9 ASCII: English costs one script byte per letter, and
     every byte is still a legal message byte for the script parser;
  2. advance the cursor half a cell after a row-9 character (or the space
     code 8140) instead of a whole cell.  Other characters keep the full
     advance, so partly translated builds stay readable;
  3. move the stack up so the hook fits after the file.  The scenario page
     region (0x800 paragraphs) is left alone by default: original games load
     pages far larger than it, and growing it can exceed the free memory of
     the disk image's DOS setup.  `pool_paras` enlarges it only on request.
This follows the approach of the PC-98 Rance 4.1/4.2 English ports (half-width
row-9 glyphs through the kana table); the per-character advance is our change.

Patch sites are located by byte signatures, so any System 3 build with the
same code shape works.
"""
import re

ORG = 0x100

# One-byte codes (A0-DF): our own assignment.  Characters not listed are
# written as 2-byte row-9 codes (still half-width).
# DE/DF are the dakuten marks, which the engine handles outside the table, so
# only A0-DD (62 codes) are assigned.
ONE_BYTE = " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,!?'-:()"
assert len(ONE_BYTE) == 62
BYTE_OF = {c: 0xA0 + i for i, c in enumerate(ONE_BYTE)}

_SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-",
          "–": "-", "…": "...", "　": " "}


def row9(c):
    """ASCII 0x21-0x7E -> NEC row-9 Shift-JIS code (half-width glyph)."""
    o = ord(c)
    t = o + 0x1F if o < 0x60 else o + 0x20
    return bytes([0x85, t])


def table_words():
    words = []
    for c in ONE_BYTE:
        words.append(0x8140 if c == " " else int.from_bytes(row9(c), "big"))
    return words


def encode(s, fallback):
    import unicodedata
    out = bytearray()
    for ch in s:
        ch = _SUBST.get(ch, ch)
        for c in ch:
            if c in BYTE_OF:
                out.append(BYTE_OF[c])
            elif 0x21 <= ord(c) <= 0x7E:
                out += row9(c)
            else:
                base = "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))
                if base and all(0x20 <= ord(x) <= 0x7E for x in base):
                    out += encode(base, fallback)
                else:
                    out += fallback(c)
    return bytes(out)


def cells(s):
    """Screen width in full cells (every English character is half a cell)."""
    return (len(s) + 1) // 2


def _find(data, pattern, what):
    rx = re.compile(pattern, re.S)
    hits = list(rx.finditer(data))
    if len(hits) != 1:
        raise ValueError("%s: expected 1 match, found %d" % (what, len(hits)))
    return hits[0]


def build(adv, pool_paras=None):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    adv = bytearray(adv)
    # 1. kana table
    m = _find(bytes(adv), re.escape(bytes.fromhex("4081428175817681418145")), "kana table")
    t = m.start()
    for i, w in enumerate(table_words()):
        adv[t + 2 * i] = w & 0xFF
        adv[t + 2 * i + 1] = w >> 8
    # 2. character advance in the text drawer
    try:  # 1994-95 builds: lead check, kana convert, then mov bp/di/cx, add [x],cx
        m = _find(bytes(adv), rb"\xe8..\x73\x05\xe8..\xeb\x06\x8a\xe0\x26\x8a\x04\x46"
                              rb"\x8b\x2e(..)\x8b\x3e..\x8b\x0e..(\x01\x0e(..))", "text drawer")
        site, xvar = m.start(2), int.from_bytes(m.group(3), "little")
    except ValueError:  # 1996 builds (Ningyo): mov bx/cx/bp/di, add [x],cx after a half-width branch
        hits = [h for h in re.finditer(rb"\x8b\x1e..\x8b\x0e..\x8b\x2e(..)\x8b\x3e..(\x01\x0e(..))", bytes(adv), re.S)
                if h.group(1) == h.group(3)]
        if len(hits) != 1:
            raise ValueError("text drawer: expected 1 match, found %d" % len(hits))
        site, xvar = hits[0].start(2), int.from_bytes(hits[0].group(3), "little")
    # 3. stack / memory block / page pool
    # mov ax,imm / mov sp,ax  or  mov sp,imm
    sp = _find(bytes(adv[:0x40]), rb"\xb8(..)\x8b\xe0|\xbc(..)", "stack setup")
    sp_group = 1 if sp.group(1) is not None else 2
    # memory block = end of init code + stack room: either "shr 4; add paragraphs"
    # (group 1) or "add bytes; shr 4" (group 2).  Both grow by 0x1000 bytes.
    resize = _find(bytes(adv), rb"\xbb..\xc1\xeb\x04\x81\xc3(..)\xb4\x4a\xcd\x21"
                               rb"|\xbb..\x81\xc3(..)\xc1\xeb\x04(?:\x8b\xf3\x8b\xfb)?\xb4\x4a\xcd\x21", "memory resize")
    rs_group, rs_add = (1, 0x100) if resize.group(1) is not None else (2, 0x1000)
    pool = _find(bytes(adv), rb"\xb4\x48\xcd\x21\x72\xfa\x03\xd8\xa3..\xa3..\x05(\x00\x08)", "page pool")

    base = ORG + len(adv)
    code_at = base + (base & 1)
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    asm = """
        cmp ah, 0x85
        je half
        cmp ax, 0x8140
        je half
        add word ptr [{x}], cx
        .byte 0xc3
    half:
        push cx
        shr cx, 1
        add word ptr [{x}], cx
        pop cx
        .byte 0xc3
    """.format(x=xvar)
    hook = bytes(ks.asm(asm, code_at)[0])
    sp_val = int.from_bytes(sp.group(sp_group), "little")
    if code_at + len(hook) >= sp_val - 0x400:
        raise ValueError("no room for the hook below the stack")
    rel = (code_at - (ORG + site + 3)) & 0xFFFF
    adv[site:site + 4] = b"\xe8" + rel.to_bytes(2, "little") + b"\x90"
    adv[sp.start(sp_group):sp.start(sp_group) + 2] = (sp_val + 0x1000).to_bytes(2, "little")
    old = int.from_bytes(resize.group(rs_group), "little")
    adv[resize.start(rs_group):resize.start(rs_group) + 2] = (old + rs_add).to_bytes(2, "little")
    if pool_paras:  # optional; off by default so the patch stays memory-neutral
        adv[pool.start(1):pool.start(1) + 2] = pool_paras.to_bytes(2, "little")
    pad = b"\0" * (code_at - base)
    return bytes(adv) + pad + hook
