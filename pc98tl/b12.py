"""Himeya Soft's B12 engine (Bacta 1&2 + Voice: BACTA\\B12.EXE): the scenario archive, its scripts, and
English (the engine draws ASCII half-width itself).

SNR (`archive`, `archive_bytes`): a word (the directory's size), then 16-byte entries (a name of 12 bytes,
the dword place of the member; a last entry with no name holds the end), then the members.  Every byte of a
member is rotated right 5 bits (`decode` rotates it back).

A script runs from its first byte, op by op (B12.EXE's table of 31 ops; `Script`, `OPS`):
  00 / 1B                     end
  05 f text                   a message (f 1: shown only without the voice), up to 0
  08 0 a / 08 1               gosub a / return
  09 n a(n)                   a jump by a variable (its table of n addresses; without its flag, on)
  0E x(4) n(2) (b text)(n)    a menu of n choices
  0F 0 b name b / 0F f b      a voice / its end
  10 a bit(2) (v | addr)      a flag of 11Eh: a = 0 set it to v; else jump (a 1: when it is clear, 2: set)
  12 a bit (v | addr)         the same with the flags at 274h
  11 sub args                 a variable: 00-05 set, add, subtract (4 bytes), 06-11 compare and jump
                              (the address after 4 bytes), 12 goto, 13 random (4)
  1C 00 v(4) / 1C 01 / 1C 02  if / else / endif (the ops in between run "skipped": each steps over its
                              own arguments, so a goto inside does not end a block)
  04 x y w h c                the text window (dots: x, y, width, height; its colour)
  the others take fixed arguments, or a sub-op's (`parse`).
`parse` reads the ops in turn; where they stop reading (OPENING.SNR's pictures), the bytes after the last
end up to the next address something jumps to are data.  `rebuild` writes a script again with texts of any
length, every address mapped to its new place.

Text (B12.EXE's routine at 0521h): Shift-JIS, bytes below 80h drawn half-width (8 dots); 01-0Ah control
codes with 1 argument (0 for 07, 08; 2 for 06): 01 a colour, 04 n a string variable, 07 a new line, 08 the
window cleared, 09 f a key waited for, 0A the line's height.  The routine breaks a line at the window's
right edge and goes on down past its bottom: the English is broken between words, each line filled out to
the edge with spaces (07 in a text moves the script segment's copy of the position, not the window's), and
09 01 08 after each window's lines.
"""
import struct

FIXED = {0x00: 1, 0x1B: 1, 0x02: 1, 0x01: 2, 0x15: 2, 0x19: 2, 0x1D: 2, 0x03: 10, 0x04: 10, 0x1A: 10,
         0x0D: 12, 0x13: 3, 0x1E: 3, 0x14: 2, 0x18: 2}
CODES = [1, 1, 1, 1, 1, 2, 0, 0, 1, 1]
LINE = 18                   # the line's height (dots) the scripts set with 0A 12h
ROOM = 0x10000              # a script's segment


def decode(b):
    return bytes(((x << 5) | (x >> 3)) & 0xFF for x in b)


def encode(b):
    return bytes(((x >> 5) | (x << 3)) & 0xFF for x in b)


def archive(data):
    """[(name, bytes)] of SNR."""
    n = struct.unpack_from("<H", data, 0)[0]
    ents = []
    for k in range(n // 16):
        e = data[2 + 16 * k:18 + 16 * k]
        ents.append((e[:12].split(b"\0")[0].decode("latin-1"), struct.unpack_from("<I", e, 12)[0]))
    out = []
    for i, (name, at) in enumerate(ents):
        if name:
            end = next((a for _n, a in ents[i + 1:]), len(data))
            out.append((name, data[at:end]))
    return out, n


def archive_bytes(members, dir_size):
    head = bytearray(struct.pack("<H", dir_size))
    at = 2 + dir_size
    body = bytearray()
    for name, d in members:
        head += name.encode("latin-1").ljust(12, b"\0") + struct.pack("<I", at + len(body))
        body += d
    while len(head) < 2 + dir_size:
        head += b"\0" * 12 + struct.pack("<I", at + len(body))
    if len(head) != 2 + dir_size:
        raise ValueError("SNR: %d members do not fit its directory" % len(members))
    return bytes(head + body)


class ScriptError(ValueError):
    pass


def text_end(d, k):
    while True:
        c = d[k]
        if c == 0:
            return k
        if c < 0x20:
            if c > 10:
                raise ScriptError("code %02x at %x" % (c, k))
            k += 1 + CODES[c - 1]
        elif 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF:
            k += 2
        else:
            k += 1


def _read(d, k):
    """The ops from k, in turn: ([(place, op, length)], [address field places], [(kind, start, end)],
    [(place, window x, y, w, h)]); raises ScriptError where they stop reading."""
    w = lambda k: struct.unpack_from("<H", d, k)[0]       # noqa: E731
    ops, addrs, texts, windows = [], [], [], []
    while k < len(d):
        s, op = k, d[k]
        k += 1
        if op in FIXED:
            if op == 0x04:
                windows.append((s, w(k), w(k + 2), w(k + 4), w(k + 6)))
            k += FIXED[op] - 1
        elif op == 0x05:
            k += 1
            e = text_end(d, k)
            texts.append(("msg", k, e))
            k = e + 1
        elif op in (0x06, 0x07):
            k = text_end(d, k) + 1 + (5 if op == 0x06 else 0)
        elif op == 0x08:
            f = d[k]
            k += 1
            if f == 0:
                addrs.append(k)
                k += 2
        elif op == 0x09:
            n = d[k]
            k += 1
            for _j in range(n):
                addrs.append(k)
                k += 2
        elif op == 0x0A:
            sub = d[k]
            k += 1
            if sub in (2, 3):
                k += 1
            elif sub == 4:
                k += 1 + 4 * d[k]
            elif sub > 4:
                raise ScriptError("op 0A %d at %x" % (sub, s))
        elif op == 0x0B:
            k = text_end(d, k + 1) + 1
        elif op == 0x0C:
            sub = d[k]
            if sub > 2:
                raise ScriptError("op 0C %d at %x" % (sub, s))
            k += 1 + (0, 13, 31)[sub]
        elif op == 0x0E:
            k += 4
            n = d[k]
            k += 2
            for _j in range(n):
                k += 1
                e = text_end(d, k)
                texts.append(("item", k, e))
                k = e + 1
        elif op == 0x0F:
            f = d[k]
            k += 2
            if f == 0:
                k = d.index(b"\0", k) + 2
        elif op == 0x10:
            a, bit = d[k], w(k + 1)
            k += 3
            if bit == 0xFFFF or a == 0:
                k += 1
            else:
                addrs.append(k)
                k += 2
        elif op == 0x11:
            sub = d[k]
            k += 1
            if 6 <= sub < 0x12:
                addrs.append(k + 4)
                k += 6
            elif sub == 0x12:
                addrs.append(k)
                k += 2
            elif sub < 0x14:
                k += 4
            else:
                raise ScriptError("op 11 %x at %x" % (sub, s))
        elif op == 0x12:
            a = d[k]
            k += 2
            if a == 0:
                k += 1
            else:
                addrs.append(k)
                k += 2
        elif op == 0x16:
            lo = d[k]
            k += 2 + (1 if lo else 0)
            k = d.index(b"\0", k) + 1
        elif op == 0x17:
            k = d.index(b"\0", k + 2) + 1
        elif op == 0x1C:
            sub = d[k]
            if sub > 2:
                raise ScriptError("op 1C %d at %x" % (sub, s))
            k += 1 + (4 if sub == 0 else 0)
        else:
            raise ScriptError("op %02x at %x" % (op, s))
        if k > len(d):
            raise ScriptError("op %02x at %x runs past the end" % (op, s))
        ops.append((s, op, k - s))
    return ops, addrs, texts, windows


def _ends(d, o):
    return o[1] in (0x00, 0x1B) or (o[1] == 0x08 and d[o[0] + 1]) or (o[1] == 0x11 and d[o[0] + 1] == 0x12)


class Script:
    def __init__(self, d):
        self.d = d = bytes(d)
        w = lambda k: struct.unpack_from("<H", d, k)[0]   # noqa: E731
        self.ops, self.addrs, self.texts, self.windows, self.data = [], [], [], [], []
        k = 0
        while k < len(d):
            try:
                o, a, t, win = _read(d, k)
                self._add(o, a, t, win)
                break
            except ScriptError as err:
                bad = int(str(err).split(" at ")[1].split()[0], 16)
            o, a, t, win = _read(d[:bad], k)
            while o and not _ends(d, o[-1]):
                o.pop()
            if not o:
                raise ScriptError("no end before the bytes at %x that do not read as ops" % bad)
            cut = o[-1][0] + o[-1][2]
            self._add(o, [x for x in a if x < cut], [x for x in t if x[1] < cut], [x for x in win if x[0] < cut])
            after = [w(x) for x in self.addrs if w(x) >= cut]
            if not after:
                raise ScriptError("nothing goes on after the data at %x" % cut)
            self.data.append((cut, min(after)))
            k = min(after)
        starts = {o[0] for o in self.ops} | {len(d)}
        for a in self.addrs:
            if w(a) not in starts:
                raise ScriptError("an address at %x points at %x, no op's start" % (a, w(a)))

    def _add(self, o, a, t, win):
        self.ops += o
        self.addrs += a
        self.texts += t
        self.windows += win

    def window_at(self, k):
        """(cells a line, lines) of the last window set before k (the script's order), or of the script's
        first one (set in a routine the script calls at its start)."""
        last = None
        for s, _x, _y, w, h in self.windows:
            if s < k or last is None:
                last = (w, h)
        if last is None:
            return 68, 3
        return max(1, last[0] // 8), max(1, (last[1] + 1) // LINE)


def rebuild(sc, new):
    """The script with new texts ({start: bytes without the 0}), every address moved."""
    d = sc.d
    spans = sorted((s, e) for _k, s, e in sc.texts if s in new)
    out, at, starts = bytearray(), 0, []
    for s, e in spans:
        out += d[at:s]
        starts.append((s, e, len(out)))
        out += new[s] + b"\0"
        at = e + 1
    out += d[at:]

    def move(o):
        delta = 0
        for s, e, ns in starts:
            if o < s:
                break
            if o <= e:
                return ns + min(o - s, len(new[s]))
            delta = ns + len(new[s]) + 1 - (e + 1)
        return o + delta

    for a in sc.addrs:
        v = struct.unpack_from("<H", d, a)[0]
        struct.pack_into("<H", out, move(a), move(v))
    if len(out) > ROOM:
        raise ScriptError("%d bytes, the segment holds %d" % (len(out), ROOM))
    return bytes(out)


def layout(text, width, rows, first=0):
    """English for the window: broken between words at width cells (the first line after `first`), each
    line filled with spaces to the window's edge, where the routine breaks it (its 07 moves the script
    segment's copy of the position, not the window's), 09 01 08 (a key, the window cleared) after each `rows`
    lines."""
    from .aypio import ascii_text
    from .text import wrap
    lines = wrap(ascii_text(text), width, width=len, first=width - first if first else None)
    out = b""
    for k, ln in enumerate(lines):
        b = ln.encode("ascii")
        out += b
        if k == len(lines) - 1:
            break
        cells = len(b) + (first if k == 0 else 0)
        if (k + 1) % rows == 0:
            out += b"\x09\x01\x08"
        elif cells < width:
            out += b" " * (width - cells)      # (to the edge: the routine breaks the line there)
    return out
