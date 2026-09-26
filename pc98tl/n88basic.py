"""Japanese strings in a protected N88-BASIC(86) program (Abunai Tengu's NACT4).

A protected ("P") save is the tokenized program with every byte rotated right
by one bit.  Japanese in string literals is stored as ESC K, 7-bit JIS pairs,
ESC H (kanji in / kanji out).  Each such run is replaced in place by ASCII of
the same length (padded with spaces), so no line changes size and the line
links stay valid; BASIC prints ASCII half-width on the text layer.
"""
import re

KANJI = re.compile(rb"\x1bK((?:[\x21-\x7e]{2})+)\x1bH")


def unprotect(data):
    return bytes(((b << 1) | (b >> 7)) & 0xFF for b in data)


def protect(data):
    return bytes(((b >> 1) | (b << 7)) & 0xFF for b in data)


def strings(prog):
    """[(offset of ESC, length in bytes, Japanese)] in the protected program."""
    plain = unprotect(prog)
    out = []
    for m in KANJI.finditer(plain):
        jp = (b"\x1b$B" + m.group(1) + b"\x1b(B").decode("iso2022_jp", "replace")
        out.append((m.start(), m.end() - m.start(), jp))
    return out


def ascii_bytes(text):
    """English as printable ASCII (anything else becomes '?')."""
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "\n": " "}
    s = "".join(subst.get(c, c) for c in text)
    return bytes(ord(c) if 0x20 <= ord(c) < 0x7F and c != '"' else ord("?") for c in s)


def apply(prog, texts, sizes, label):
    """texts: {offset: english}, sizes: {offset: length}.  Returns (program, warnings)."""
    plain = bytearray(unprotect(prog))
    warn = []
    for off, text in texts.items():
        n = sizes[off]
        enc = ascii_bytes(text)
        if len(enc) > n:
            warn.append("%s string %04x: %d bytes, only %d fit (truncated)" % (label, off, len(enc), n))
            enc = enc[:n]
        plain[off:off + n] = enc.ljust(n, b" ")
    return protect(bytes(plain)), warn
