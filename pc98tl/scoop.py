"""Scoop's "Adventure Script Interpreter" (AI.COM, Immoral Study 1-3): the scripts and their text.

A script (*.BIN, "Adventure v1.00\\0"): three words at 10h (where the code starts, 18h) and a word at
16h, the string table's place; the code runs from 18h up to it, the strings (each ended by a NUL)
from there to the end of the file.  The interpreter is a stack machine of 89h ops; an op's inline
operands (INLINE: a byte or a word after it) are all its length, the rest come from the stack.  0Dh w
pushes a word: a number, or a string's offset from the table's start; the strings shown are pushed
right before the op that shows them: 44h a message (a speaker's tag is one too: "<", ESC c nn ;,
【name】, ">"), 4Ah a menu's item, 4Bh a menu's heading.  Nothing else in a script is an address of
a string, and a jump (01-06h) is an address in the code, which does not move: new text goes after
the end of the file and only the pushes that show it are changed.

Text: Shift-JIS; a byte A0h-DFh is a character from AI.COM's table (KANA_SIG: "　。「」、・を", small
and plain hiragana, "ー", "…", "？"); an ASCII byte is drawn half-width (SCBIOS.COM writes the text
VRAM, one cell a byte); 0Dh a new line; "[" and "]" turn the highlight colour on and off, "<" ">"
and 01-05h are a tag's marks and attributes, ESC ... ";" a command.  The window breaks a line at
its right edge (54 cells, the message window and the full screen's alike), between any two
characters, and at its bottom waits for a key and starts over.
"""
import re
import struct

MAGIC = b"Adventure v1.00\0"
INLINE = {0x01: 2, 0x02: 1, 0x03: 2, 0x04: 1, 0x05: 2, 0x06: 1, 0x09: 2, 0x0A: 2, 0x0D: 2, 0x0E: 1,
          0x0F: 1, 0x10: 1, 0x11: 1, 0x81: 2, 0x88: 2}
OPS = 0x89
SHOW = {0x44: "msg", 0x4A: "item", 0x4B: "title"}
# AI.COM's text loop: a byte A0h-DFh, its character from the table
KANA_SIG = re.compile(rb"\x3c\xa0\x72.\x3c\xdf\x77.\x2c\xa0\x8b\xf0\xd1\xe6\x8b\x84(..)\x86[\xc4\xe0]", re.S)


def is_script(d):
    return d.startswith(MAGIC)


def kana_table(prog):
    """{byte A0h-DFh: its character}, from AI.COM."""
    m = KANA_SIG.search(prog)
    if m is None:
        raise ValueError("AI.COM: the kana table not found")
    at = struct.unpack("<H", m.group(1))[0] - 0x100
    return {0xA0 + k: prog[at + 2 * k:at + 2 * k + 2].decode("cp932") for k in range(64)}


class Script:
    """The code's ops [(addr, op)], the strings {offset: (start, end)}, and the strings shown:
    [(op addr of the push, offset, kind)]."""

    def __init__(self, d):
        if not is_script(d):
            raise ValueError("not an Adventure script")
        self.d = d
        self.base = struct.unpack_from("<H", d, 0x16)[0]
        i, self.ops = 0x18, []
        while i < self.base:
            op = d[i]
            if op >= OPS:
                raise ValueError("op %02x at %x" % (op, i))
            self.ops.append((i, op))
            i += 1 + INLINE.get(op, 0)
        if i != self.base:
            raise ValueError("the code runs past the string table (%x, %x)" % (i, self.base))
        self.strings, i = {}, self.base
        while i < len(d):
            j = d.index(0, i)
            self.strings[i - self.base] = (i, j)
            i = j + 1
        self.shown = []
        for (a, op), (_b, nxt) in zip(self.ops, self.ops[1:]):
            if op == 0x0D and nxt in SHOW:
                w = struct.unpack_from("<H", d, a + 1)[0]
                if w not in self.strings:
                    raise ValueError("a push at %x shows %x, not a string's start" % (a, w))
                self.shown.append((a, w, SHOW[nxt]))

    def text(self, off):
        s, e = self.strings[off]
        return self.d[s:e]


def rebuild(sc, new):
    """The script with the English: new {offset: bytes} put after the end of the file, the pushes
    that show those strings changed to them."""
    d = bytearray(sc.d)
    place = {}
    for off, b in new.items():
        place[off] = len(d) - sc.base
        d += b + b"\0"
    if len(d) - sc.base > 0xFFFF or len(d) > 0xFFFF:
        raise OverflowError(len(d))
    for a, off, _k in sc.shown:
        if off in place:
            struct.pack_into("<H", d, a + 1, place[off])
    return bytes(d)
