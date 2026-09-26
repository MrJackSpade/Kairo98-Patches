"""Shift-JIS helpers: column widths, English encoding, word wrap, pseudo text."""
import re
import unicodedata


def is_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def sjis_cols(data):
    """Display width in half-width columns (2-byte char = 2, 1-byte = 1)."""
    cols = i = 0
    while i < len(data):
        n = 2 if is_lead(data[i]) else 1
        cols += n
        i += n
    return cols


# ASCII -> full-width Shift-JIS.  Engines that only treat bytes >= 0x80 as text
# (Alice Soft System 1-3, many others) cannot take raw ASCII, but every PC-98
# engine can draw full-width JIS characters.
def _fw(ch):
    if ch == " ":
        return b" "  # half-width space is a legal text byte and saves room
    o = ord(ch)
    if 0x21 <= o <= 0x7E:
        try:
            return chr(o + 0xFEE0).encode("cp932")
        except UnicodeEncodeError:
            pass
    special = {"’": "＇", "‘": "＇", "“": "＂", "”": "＂",
               "…": "…", "—": "―", "–": "－"}
    if ch in special:
        try:
            return special[ch].encode("cp932")
        except UnicodeEncodeError:
            return "？".encode("cp932")
    try:
        b = ch.encode("cp932")
        return b
    except UnicodeEncodeError:
        base = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in base if not unicodedata.combining(c))
        if base and base != ch:
            return b"".join(_fw(c) for c in base)
        return "？".encode("cp932")


def encode_fullwidth(s):
    return b"".join(_fw(c) for c in s)


def wrap(s, max_cols, encode=encode_fullwidth, width=None):
    """Greedy word wrap.  `width(str)` gives display width (defaults to the
    Shift-JIS column width of `encode(str)`).  '\n' forces a break.
    Returns a list of str lines."""
    if width is None:
        width = lambda t: sjis_cols(encode(t))  # noqa: E731
    lines = []
    for para in s.split("\n"):
        words = para.split(" ")
        cur = ""
        for w in words:
            cand = w if not cur else cur + " " + w
            if width(cand) <= max_cols or not cur:
                cur = cand
                # a single over-long word: hard split
                while width(cur) > max_cols:
                    cut = len(cur)
                    while cut > 1 and width(cur[:cut]) > max_cols:
                        cut -= 1
                    lines.append(cur[:cut])
                    cur = cur[cut:]
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


_LOREM = ("the quick brown fox jumps over lazy dogs while brave heroes explore "
          "dark dungeons searching for ancient treasure and forgotten magic").split()


def pseudo(ident, jp_cols, factor=2.5):
    """Filler English roughly `factor` times the Japanese display width,
    tagged with the string id so a screenshot identifies the line."""
    target_chars = max(4, int(jp_cols * factor / 2))  # full-width: 2 cols/char
    out = "<%s>" % ident
    i = sum(map(ord, ident))
    while len(out) < target_chars:
        out += " " + _LOREM[i % len(_LOREM)]
        i += 7
    return out


TOKEN_RE = re.compile(r"\{([A-Z])(\d+)\}")
