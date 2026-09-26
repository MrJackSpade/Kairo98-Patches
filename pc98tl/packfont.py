"""Packed half-width English for engines that only draw 2-byte cells.

Two ASCII characters are packed into one otherwise-unused Shift-JIS code, and
an engine hook draws both 8px ANK glyphs inside the single 16px cell.  Script
bytes stay at ~1 byte per letter and the engine's layout logic still sees one
full-width cell, so line lengths, menus and wrapping keep working.

Code space: lead 0x80 or 0xEB..0xFF (never used by JIS X 0208 text), trail
0x01..0xFF (0x00 is avoided because engines copy text with strcpy-style loops).
"""

ALPHABET = (" abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789"
            ".,!?'\"-:()")
A = len(ALPHABET)
LEADS = [0x80] + list(range(0xEB, 0x100))
assert A * A <= len(LEADS) * 255, "alphabet too large for code space"
INDEX = {c: i for i, c in enumerate(ALPHABET)}

_SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', ";": ",",
          "—": "-", "–": "-", "…": "...", "[": "(", "]": ")",
          "{": "(", "}": ")", "`": "'"}


def normalize(s):
    import unicodedata
    out = []
    for ch in s:
        ch = _SUBST.get(ch, ch)
        if all(c in INDEX for c in ch):
            out.append(ch)
            continue
        base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        out.append(base if base and all(c in INDEX for c in base) else ch)
    return "".join(out)


def pair_code(c1, c2):
    n = INDEX[c1] * A + INDEX[c2]
    return bytes([LEADS[n // 255], 1 + n % 255])


def encode(s, fallback):
    """Encode str -> bytes.  Characters outside the alphabet go through
    `fallback` (e.g. full-width Shift-JIS), each taking one whole cell."""
    s = normalize(s)
    out = bytearray()
    pend = None
    for ch in s:
        if ch in INDEX:
            if pend is None:
                pend = ch
            else:
                out += pair_code(pend, ch)
                pend = None
        else:
            if pend is not None:
                out += pair_code(pend, " ")
                pend = None
            out += fallback(ch)
    if pend is not None:
        out += pair_code(pend, " ")
    return bytes(out)


def cells(s):
    """Width in 16px cells after encoding."""
    s = normalize(s)
    n = 0
    run = 0
    for ch in s:
        if ch in INDEX:
            run += 1
        else:
            n += (run + 1) // 2 + 1
            run = 0
    return n + (run + 1) // 2
