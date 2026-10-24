"""Black Package's engine (Miwaku no Chousho: MCEXE.EXE, *.SO3 scripts).

A script (*.SO3) is LZSS-compressed as Aaru's files are (`aaru.unlz`/`aaru.lz`: two dwords, the packed
and unpacked sizes, then flag bytes and literals or 12-bit references) and runs from its first byte in a
segment of its own (kept to F800h bytes, a little more than the largest script the game
ships).  It is a run of ops: a word FCxxh (xx the op), a word, the number of
the op's argument bytes, and the arguments; MCEXE.EXE's table has its handler at entry xx+1.  Between
blocks of ops (after a return or a jump) may lie bytes no op reaches, zeros and tables, kept as they are
(`Script.items`).  Three ops name a place in the script: 09h and 21h jump there, 0Ah calls it (0Bh
returns); their first word is the place, moved when a script is laid out anew (`Script.build`).  The
structured ops (1Ah/1Bh, 1Dh/82h, 20h/83h, 22h/24h) find their ends by walking the ops' lengths, and the
loop 22h writes 24h's place itself, so they need nothing moved.

Op 06h shows a message: its text up to a NUL.  In it "-" breaks the line, "_" ends the speaker's name,
`n puts in a name (`0 the hero's), %n a number, ?n sets the colour.  The program draws a byte below 80h
from its own half-width font (ANK.DA1), so English goes in as ASCII; the marks the text takes as codes
(` ! } $ ? ^ % & { # | * _ -) are written as their full-width forms.
"""
import struct

from .aaru import compressed, lz, unlz

JUMPS = (0x09, 0x0A, 0x21)     # ops whose first word is a place in the script
MESSAGE = 0x06
LIMIT = 0xF800                 # a script's room: its segment, kept to about the largest the game ships (63,197)
# ops whose handlers neither move the script's place, nor write into the script, nor keep where they are
# (read from MCEXE.EXE's handlers), and the call, less the ones the structured ops look for (1Ah-24h,
# 42h, 44h, 45h, 82h, 83h): a run of them may be moved into a subroutine
FOLD_SAFE = frozenset([0x01, 0x02, 0x03, 0x04, 0x05, 0x07, 0x0A, 0x0C, 0x0D, 0x0F, 0x11, 0x12, 0x13, 0x14, 0x15,
                       0x16, 0x17, 0x18, 0x19, 0x23, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D,
                       0x2E, 0x2F, 0x30, 0x33, 0x34, 0x35, 0x36, 0x38, 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E,
                       0x3F, 0x40, 0x41, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E,
                       0x4F, 0x50, 0x51, 0x52, 0x53, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x5B, 0x5C, 0x5D,
                       0x5E, 0x5F, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x6D, 0x6E,
                       0x6F, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x7B, 0x7C,
                       0x7D, 0x7E, 0x7F, 0x80, 0x81, 0x84, 0x85, 0x86, 0x87, 0x8A, 0x8B, 0x8C, 0x8D,
                       0x8E, 0x8F, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0x9C,
                       0x9D, 0x9E, 0x9F, 0xA0, 0xA1, 0xA2, 0xA3, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xAB, 0xAC,
                       0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xBB, 0xBC, 0xC1,
                       0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xD0, 0xD1, 0xD2,
                       0xD3, 0xD6, 0xD7, 0xE1, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8])


def unpack(data):
    return unlz(data) if compressed(data) else bytes(data)


class Script:
    """A script's items: ("op", place, op, args) and ("raw", place, bytes) for what no op covers."""

    def __init__(self, data):
        u = unpack(data)
        self.size = len(u)
        self.items = []
        p = 0
        while p < len(u):
            if p + 4 <= len(u) and u[p + 1] == 0xFC:
                n = struct.unpack_from("<H", u, p + 2)[0]
                if p + 4 + n <= len(u):
                    a = bytes(u[p + 4:p + 4 + n])
                    self.items.append(["op", p, u[p], a,
                                       struct.unpack_from("<H", a, 0)[0] if u[p] in JUMPS and n >= 2 else None])
                    p += 4 + n
                    continue
            q = p + 1
            while q < len(u) and not (q + 4 <= len(u) and u[q + 1] == 0xFC):
                q += 1
            self.items.append(["raw", p, bytes(u[p:q])])
            p = q

    def ops(self):
        return [it for it in self.items if it[0] == "op"]

    def size_now(self):
        return sum(4 + len(it[3]) if it[0] == "op" else len(it[2]) for it in self.items)

    def build(self):
        """The script's bytes laid out anew, its jumps' places moved (folded first if it would not fit)."""
        if self.size_now() > LIMIT:
            self.fold()
        where, p = {}, 0
        for it in self.items:
            where[it[1]] = p
            p += 4 + len(it[3]) if it[0] == "op" else len(it[2])
        if p > LIMIT:
            raise ValueError("%d bytes, a script holds %d" % (p, LIMIT))
        out = bytearray()
        for it in self.items:
            if it[0] == "raw":
                out += it[2]
                continue
            args = bytearray(it[3])
            if it[4] is not None:
                if it[4] not in where:
                    raise ValueError("op %02X at %04X goes to %04X, not an op's place" % (it[2], it[1], it[4]))
                struct.pack_into("<H", args, 0, where[it[4]])
            out += struct.pack("<BBH", it[2], 0xFC, len(args)) + args
        return bytes(out)

    def fold(self, limit=LIMIT):
        """Make room: a run of ops found more than once (ops that do not depend on where they are) is
        put once at the end, as a subroutine, and each run made a call of it."""
        targets = {it[4] for it in self.items if it[0] == "op" and it[4] is not None}
        key = 0x10000 + len(self.items)
        while self.size_now() > limit:
            best = None
            for n in range(6, 1, -1):
                count = {}
                for k in range(len(self.items) - n + 1):
                    win = self.items[k:k + n]
                    if any(it[0] != "op" or it[2] not in FOLD_SAFE for it in win):
                        continue
                    if any(it[1] in targets for it in win[1:]):
                        continue
                    sig = tuple((it[2], it[3], it[4]) for it in win)
                    count.setdefault(sig, []).append(k)
                for sig, at in count.items():
                    # occurrences that do not overlap
                    keep, last = [], -n
                    for k in at:
                        if k >= last + n:
                            keep.append(k)
                            last = k
                    size = sum(4 + len(a) for _c, a, _t in sig)
                    gain = len(keep) * (size - 6) - (size + 4)
                    if len(keep) >= 2 and gain > 0 and (best is None or gain > best[0]):
                        best = (gain, sig, keep, n)
            if best is None:
                raise ValueError("%d bytes, a script holds %d (no more to fold)" % (self.size_now(), limit))
            _gain, sig, keep, n = best
            sub = key
            key += 1
            for k in reversed(keep):
                first = self.items[k][1]
                self.items[k:k + n] = [["op", first, 0x0A, struct.pack("<H", 0), sub]]
            body = [["op", sub if j == 0 else key + j, c, a, t] for j, (c, a, t) in enumerate(sig)]
            key += n
            self.items += body + [["op", key, 0x0B, b"", None]]
            key += 1

    def pack(self):
        return lz(self.build())


# ---- texts ----

CODE_MARKS = b"`%&?^}"           # a mark and its number: a name, a number, a colour, ...
FULL = {"!": "！", "?": "？", "-": "－", "%": "％", "&": "＆", "$": "＄", "^": "＾",
        "`": "｀", "{": "｛", "}": "｝", "#": "＃", "|": "｜", "*": "＊", "_": "＿",
        "\\": "￥", "~": "～"}
CHOICE = 0x0E
INSERT = 0x37
WIDTH = 72                     # half-width cells on a line of the message window (it pages every 4 lines)


def _lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def parts(t):
    """A message's text as [("t", bytes) | ("c", code bytes) | ("n", )]: characters, codes, new lines."""
    out, p, run = [], 0, bytearray()
    while p < len(t):
        b = t[p]
        if _lead(b) and p + 1 < len(t):
            run += t[p:p + 2]
            p += 2
            continue
        if b in CODE_MARKS:
            q = p + 1
            while q < len(t) and 0x30 <= t[q] <= 0x39 and q - p < 3:
                q += 1
            if b == 0x60 and q > p + 2:      # `n takes one digit
                q = p + 2
            if run:
                out.append(("t", bytes(run)))
                run = bytearray()
            out.append(("c", bytes(t[p:q])))
            p = q
            continue
        if b == 0x2D:
            if run:
                out.append(("t", bytes(run)))
                run = bytearray()
            out.append(("n",))
            p += 1
            continue
        run.append(b)
        p += 1
    if run:
        out.append(("t", bytes(run)))
    return out


def show(t):
    """A message's text as strings.json shows it: \n a new line, {`0} {%12} {?15}... its codes."""
    out = []
    for x in parts(t):
        if x[0] == "t":
            out.append(x[1].decode("cp932"))
        elif x[0] == "c":
            out.append("{%s}" % x[1].decode("ascii"))
        else:
            out.append("\n")
    return "".join(out)
