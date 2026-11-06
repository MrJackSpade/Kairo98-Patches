"""Caption tables in an ADVH opening program (Can Can Bunny Superior's OP.EXE).

The opening shows a caption under each picture: its number n picks the n-th
word of a table in the program's data segment (`TABLE_SIG`: the segment loaded
into DS, the table's place in it), the place of a NUL-ended string there.  The
program clears two rows of the text layer (rows 23 and 24) and draws the string
from column 10: a byte below 80h or A0h-DFh as one cell (its ANK character, so
English goes in as ASCII and is drawn half-width), Shift-JIS as two, 0Dh a new
line at the same column.  The Japanese centres a line with full-width spaces
before it and starts a speaker's second line under the 「.

`captions` lists them; `patch` writes English in their place: broken between
words at WIDTH cells into at most ROWS lines (more is cut and reported), each
line centred on the 80-column screen.  The strings are written anew past the
program's stack (the load image made to reach there, its minimum allocation
lessened to match: the memory it takes is the same but for the strings), still
within DS, and the table's words point at them.
"""
import re
import struct

from .aypio import ascii_text

TABLE_SIG = re.compile(rb"\xbe(..)\x8e\xde.{0,16}?\x8b\xb4(..)", re.S)
COL = 10                        # the column the program draws a caption from
SCREEN = 80                     # the text layer's columns
WIDTH = SCREEN - COL            # a line's room
ROWS = 2                        # the rows the program clears for a caption


def _header(exe):
    return list(struct.unpack_from("<14H", exe, 0))


def _layout(exe):
    """(image offset, DS's place in the image, table's offset in DS, count)."""
    hdr = _header(exe)
    base = hdr[4] * 16
    img = exe[base:]
    hits = list(TABLE_SIG.finditer(img))
    if len(hits) != 1:
        raise ValueError("OP: the caption table's lookup is not found once")
    ds = struct.unpack("<H", hits[0].group(1))[0] * 16
    table = struct.unpack("<H", hits[0].group(2))[0]
    # (the table runs up to the first caption, which follows it)
    count = (struct.unpack_from("<H", img, ds + table)[0] - table) // 2
    return base, ds, table, count


def _show(raw):
    """A caption's text as strings.json shows it: one line (the Japanese breaks
    its lines where the row is full, inside a word), the full-width spaces that
    centre or indent them left out."""
    return "".join(line.decode("cp932").strip("　") for line in raw.split(b"\r"))


def captions(exe, count=None):
    """[(n, start, end, text)]: the n-th caption's bytes in the file (its NUL
    not included) and its text.  count: the table's entries (by default the
    words up to the first caption, as the program ships)."""
    base, ds, table, found = _layout(exe)
    count = count or found
    out = []
    for k in range(count):
        p = struct.unpack_from("<H", exe, base + ds + table + 2 * k)[0]
        s = base + ds + p
        e = exe.index(b"\0", s)
        out.append((k, s, e, _show(exe[s:e])))
    return out


def _lines(text):
    words = ascii_text(" ".join(text.split("\n"))).split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > WIDTH:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w) if cur else w[:WIDTH]
    if cur:
        lines.append(cur)
    return lines


def encode(text):
    """(bytes, cut): English as a caption's bytes, its lines centred; cut when
    it took more than ROWS lines."""
    lines = _lines(text)
    cut = len(lines) > ROWS
    lines = lines[:ROWS]
    out = b"\r".join((" " * max(0, (SCREEN - len(ln)) // 2 - COL) + ln).encode("ascii") for ln in lines)
    return out, cut


def patch(exe, texts):
    """The program with {n: English} in place of those captions: (bytes,
    [n cut])."""
    if not texts:
        return exe, []
    hdr = _header(exe)
    base, ds, table, count = _layout(exe)
    img = bytearray(exe[base:])
    size = hdr[2] * 512 - (512 - hdr[1] if hdr[1] else 0) - base
    need_end = size + hdr[5] * 16                  # where the program's memory ended
    start = (hdr[7] * 16 + hdr[8] + 15) & ~15      # past the stack
    strings, cut = bytearray(), []
    for k, s, e, _t in captions(exe):
        if k in texts:
            raw, over = encode(texts[k])
            if over:
                cut.append(k)
        else:
            raw = exe[s:e]
        off = start + len(strings) - ds
        if not 0 <= off < 0x10000:
            raise ValueError("OP: the captions would lie past the data segment")
        struct.pack_into("<H", img, ds + table + 2 * k, off)
        strings += raw + b"\0"
    img = img[:size] + bytes(start - size) + strings
    total = base + len(img)
    hdr[1], hdr[2] = total % 512, (total + 511) // 512
    hdr[5] = max(0, (need_end - len(img) + 15) // 16)
    out = bytearray(exe[:base]) + img
    struct.pack_into("<14H", out, 0, *hdr)
    return bytes(out), cut
