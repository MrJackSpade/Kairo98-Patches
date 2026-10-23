"""A compiled QuickBASIC 4.x game (TechnoGrard's Minimum Guynarock: MG.EXE, EXEPACKed): its string constants
and English drawn half-width.

The program (`Program`) is unpacked (pc98tl/exepack.py).  Its data group (DGROUP: the largest segment its
relocations name) holds the string constants as BASIC descriptors: a word the length, a word the place of the
bytes (here the bytes right after), which the code names by the descriptor's place (`descriptors`).  So a
string is given other bytes of any length by pointing its descriptor at them: the English goes in a block
after the data group's initialised data (`patch`), where the stack segment started (the header's SS moved up
by the block), and the runtime's start of its string space (a word of the data group, the old end) and the
start-up's stack (SS set to the data group, SP the data's end added) are moved past it.  The program is
written back unpacked.

The story is drawn by one BASIC routine: it takes T$ a character at a time (MID$(T$, P, 1), DBCS-aware:
a Shift-JIS character or one byte), handles the marks (：n a speaker's line, n a full-width digit or a
space; ＾ a new line; ￥ a key and the window cleared; ＠ and ＃ settings), and PRINTs the character at its
column, then adds 4 to the column (8-dot units: the screen draws its text at double width, a full-width
character 32 dots).  `patch` makes that step 2 for a one-byte character (a helper in 17 bytes of padding
between two runtime routines: the step's constant chosen by C$'s length), so ASCII letters stand 16 dots
apart: half the full-width character.  The routine breaks a line at the window's edge by itself.
"""
import re
import struct

from . import exepack

STEP_SITE = re.compile(rb"\xb8(..)\x50\x9a....\xbb(..)\x9a....(\xbb(..))\x9a....\xbb\2\x9a", re.S)
PADDING = re.compile(rb"\xca\x06\x00(\x00{17})")      # (after a retf 6: two runtime routines apart)
# a string given to a routine with three more arguments (LOCATE's row and column, COLOR) and PRINTed whole:
# T$ = "..." then CALL SUB(a, b, c, T$)
LINE_SITE = re.compile(rb"\xb8(..)\x50\xb8(..)\x50\x9a....(?:\xb8..\x50){3}\xb8\2\x50\x9a", re.S)
LINE_CELLS = 26             # a line of the window: 26 letters (13 full-width)
WINDOW_LINES = 5


class Program:
    def __init__(self, exe):
        if exepack.is_packed(exe):
            exe = exepack.unpack(exe)
        self.exe = bytearray(exe)
        h = struct.unpack_from("<14H", self.exe, 0)
        self.hb = h[4] * 16
        rel = [struct.unpack_from("<HH", self.exe, h[12] + 4 * k) for k in range(h[3])]
        segs = {struct.unpack_from("<H", self.exe, self.hb + s * 16 + o)[0] for o, s in rel}
        self.dseg = max(segs)
        self.ds = self.hb + self.dseg * 16        # file offset of DGROUP
        self.end = len(self.exe)                 # its initialised data's end (where the stack segment starts)
        if h[7] * 16 + self.hb != self.end:
            raise ValueError("the stack segment does not start at the image's end")

    def descriptors(self):
        """[(DGROUP offset, length)] of the string constants (a descriptor and its bytes after it)."""
        d, base = self.exe, self.ds
        out = []
        k = 0
        n = self.end - base
        while k < n - 4:
            ln, p = struct.unpack_from("<HH", d, base + k)
            if p == k + 4 and 0 < ln < 0x400 and k + 4 + ln <= n:
                out.append((k, ln))
                k += 4 + ln
                continue
            k += 1
        return out

    def lines(self):
        """The descriptors of the strings PRINTed whole at a place (LINE_SITE): the opening's lines, drawn as
        they are (an ASCII letter half a full-width character)."""
        code = bytes(self.exe[self.hb:self.ds])
        return {struct.unpack("<H", m.group(1))[0] for m in LINE_SITE.finditer(code)}

    def text(self, k):
        ln, p = struct.unpack_from("<HH", self.exe, self.ds + k)
        return bytes(self.exe[self.ds + p:self.ds + p + ln])


def patch(prog, new):
    """The program with new bytes for string constants ({descriptor offset: bytes}) and the half step for
    one-byte characters."""
    d = prog.exe
    code = bytes(d[prog.hb:prog.ds])
    sites = list(STEP_SITE.finditer(code))
    sites = [m for m in sites if struct.unpack("<f", d[prog.ds + struct.unpack("<H", m.group(4))[0]:
                                                       prog.ds + struct.unpack("<H", m.group(4))[0] + 4])[0] == 4.0]
    if len(sites) != 1:
        raise ValueError("MG.EXE: the column's step is found %d times, not once" % len(sites))
    m = sites[0]
    cstr, four = struct.unpack("<H", m.group(1))[0], struct.unpack("<H", m.group(4))[0]
    two = _constant(prog, 2.0)
    pads = list(PADDING.finditer(code))
    if not pads:
        raise ValueError("MG.EXE: no room for the step's helper")
    at = pads[0].start(1)
    helper = (b"\xbb" + struct.pack("<H", four) + b"\x83\x3e" + struct.pack("<H", cstr) + b"\x01"
              + b"\x75\x03\xbb" + struct.pack("<H", two) + b"\xc3")
    site = m.start(3)
    if abs(at - site) > 0x7FFF:
        raise ValueError("MG.EXE: the helper's room is out of a near call's reach")
    d[prog.hb + at:prog.hb + at + len(helper)] = helper
    d[prog.hb + site:prog.hb + site + 3] = b"\xe8" + struct.pack("<h", at - (site + 3))
    if not new:
        return bytes(d)
    # the English after the data
    heap = [k for k in range(0, prog.end - prog.ds - 1, 1)
            if struct.unpack_from("<H", d, prog.ds + k)[0] == prog.end - prog.ds]
    if len(heap) != 1:
        raise ValueError("MG.EXE: the string space's start is found %d times, not once" % len(heap))
    block = bytearray()
    base = prog.end - prog.ds
    for k, b in sorted(new.items()):
        struct.pack_into("<HH", d, prog.ds + k, len(b), base + len(block))
        block += b
        block += b"\0" * (len(block) % 2)
    block += b"\0" * (-len(block) % 16)
    if base + len(block) > 0xF000:
        raise ValueError("MG.EXE: the English takes %d bytes, the data group has room for %d"
                         % (len(block), 0xF000 - base))
    # the start-up puts the stack in DGROUP: SS the data group, SP the stack's size plus the data's end
    starts = [m.start(1) for m in re.finditer(rb"\xfa\x8e\xd7\x81\xc4(..)", code, re.S)
              if struct.unpack("<H", m.group(1))[0] == base - 2]
    if len(starts) != 1:
        raise ValueError("MG.EXE: the stack's place is found %d times, not once" % len(starts))
    d += block
    struct.pack_into("<H", d, prog.hb + starts[0], base - 2 + len(block))
    struct.pack_into("<H", d, prog.ds + heap[0], base + len(block))
    h = list(struct.unpack_from("<14H", d, 0))
    h[7] += len(block) // 16
    h[1], h[2] = len(d) % 512, (len(d) + 511) // 512
    struct.pack_into("<14H", d, 0, *h)
    return bytes(d)


def _constant(prog, value):
    want = struct.pack("<f", value)
    d = prog.exe
    for k in range(0, prog.end - prog.ds - 4, 2):
        if d[prog.ds + k:prog.ds + k + 4] == want:
            return k
    raise ValueError("MG.EXE: no constant %g" % value)


# ---- text ----------------------------------------------------------------------------------------------------

SPEAKER = "："
DIGITS = "０１２３４５６７８９"


def show(b):
    """The routine's marks as tokens: {S1}.. a speaker's line ({S0} the line without a name), ＾ \\n, ￥ {W}."""
    t = bytes(b).decode("cp932", "replace")
    out, k = [], 0
    while k < len(t):
        c = t[k]
        if c == SPEAKER and k + 1 < len(t) and (t[k + 1] in DIGITS or t[k + 1] == "　"):
            out.append("{S%d}" % (DIGITS.index(t[k + 1]) if t[k + 1] in DIGITS else 0))
            k += 2
            continue
        out.append({"＾": "\n", "￥": "{W}"}.get(c, c))
        k += 1
    return "".join(out)


FULL_SPACE = b"\x81\x40"


def halfwidth(s):
    """ASCII as NEC's two-byte half-width characters (JIS row 29h, a letter's own code the column), drawn
    half-width by PRINT itself, each as wide as two one-byte characters: so a space is two spaces.  (A
    full-width character after them shows only at an even count of letters: see `name`.)"""
    out = bytearray()
    for c in s:
        if c == " ":
            out += b"  "
            continue
        j1, j2 = 0x29, ord(c)
        s1 = ((j1 + 1) >> 1) + 0x70
        s2 = j2 + (0x1F if j1 & 1 else 0x7E)
        if s2 >= 0x7F and j1 & 1:
            s2 += 1
        out += bytes((s1, s2))
    return bytes(out)


def name(s, cells):
    """A speaker's name for the window's column of `cells` full-width cells (its full-width ：　 after it):
    the letters half-width, then full-width spaces to the column's end.  A full-width character shows
    right only after an even count of letters, so an odd count is evened by two spaces (one letter's
    width) before the full-width ones."""
    s = s[:cells]
    b = halfwidth(s)
    n = len(s)
    if n % 2:
        b += b"  "
        n += 1
    return b + FULL_SPACE * (cells - n)


TOKEN = re.compile(r"(\{S\d\}|\{W\}|\n)")


def encode(text, cells=LINE_CELLS, lines=WINDOW_LINES):
    """English bytes with the marks: each speaker's text broken between words at `cells` letters (＾, none
    after a full line: the routine breaks it), a ￥ (a key, the window cleared) before a line past the
    window's `lines`; a speaker's mark starts a line."""
    from .aypio import ascii_text
    from .text import wrap
    wait, newline = "￥".encode("cp932"), "＾".encode("cp932")
    out, cur, full = b"", 0, False

    def line(mark):
        nonlocal out, cur
        if cur >= lines:
            out += wait
            cur = 0
            if not mark:            # (after ￥ the routine's line is the one above the window's first)
                out += newline
        elif cur and not mark and not full:
            out += newline
        cur += 1

    for part in TOKEN.split(text):
        if not part:
            continue
        if part == "{W}":
            out += wait
            cur, full = 0, False
            continue
        if part == "\n":
            line(False)
            full = False
            continue
        m = re.fullmatch(r"\{S(\d)\}", part)
        if m:
            line(True)
            n = int(m.group(1))
            out += (SPEAKER + (DIGITS[n] if n else "　")).encode("cp932")
            full = False
            continue
        ls = wrap(ascii_text(part), cells, width=len)
        for i, ln in enumerate(ls):
            if i or cur == 0:
                line(False)
            out += ln.encode("ascii")
            full = len(ln) >= cells
    return out
