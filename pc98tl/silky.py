"""Silky's (and Elf's) "General Message system-1" (SL.EXE, Be-Yond 1996): the
archives, their compression and the MES scripts.

Archives (DISKA ... DISKG, one per floppy): a word, the count; that many
19-byte entries: name (12 bytes, NUL padded), a byte (54h), the size
(word) and the offset from the start of the file (dword); the members
follow, the last one ending the file.

A script member is compressed (SL.EXE 0A924h): a byte, FFh (other
members, pictures and music, start with 00-02 and are read as they are),
then words: the size
unpacked, the size of the data stream, the number of tokens, the size of
the flag stream; the flag stream, then the data stream.  A flag bit (the
high bit first) of 0 is a literal byte from the data stream, 1 a
reference: a word, the position in a 2048-byte ring (zeroed, written from
position 0), and a byte, the length less one.  A reference reads the ring
as it was before it, then writes what it read.

A MES script: a word, the offset of its bytecode; before it the file's
dictionary (two-byte Shift-JIS characters).  The interpreter (SL.EXE
2218h) runs a statement at a time: an opcode (30h-85h; a table at 1F16h)
and its arguments, or 00, which ends the block (a subroutine or the
script returns).  Arguments:

* an expression (0ACADh): items until 00.  A first item 32h is a random
  number (two words, the lowest and the highest); 01-04 a constant (that
  many bytes); 05-0Ah a variable with an index (a byte, the type, a word,
  the address, then the index, an expression); 0Bh-1Fh a variable (type,
  word); 20h and up an operator.
* an argument list (3F1Dh): until 00: 11h and a NUL-ended string, 0Fh and
  a variable and a byte, or an expression.
* a variable list (3F72h): variables, each with a byte after it, until 00.
* text (4Ah, 27C9h): a mode byte, then characters until 00.  Mode 1:
  18h-7Fh and A0h-DFh are dictionary characters (their number less 17h,
  or 37h, the word at twice that offset), 04 a new line (the engine pages
  by itself at the window's bottom), anything else a two-byte Shift-JIS
  character.  Mode 2: single-byte characters, drawn half-width (the font
  size index is 0, an 8x16 cell: the game's half-width katakana sound
  effects); 04 a new line.  The engine wraps at the window's right edge
  by itself.
* 45h copies into a variable another variable or an inline string (a
  NUL-ended string and a byte: speaker names, shown by 4Bh).
* 44h: a variable, a word (the address after its inline data, where the
  engine goes on), the data.
* 3Ah, 6Bh and 71h take a sub-command (3Ah a byte, the others a constant)
  that picks the arguments.

Addresses are absolute offsets in the script: the words OPS_ADDRESS names
(the targets of jumps, loops, cases and calls; all of them land on a
statement in every script), 44h's word, and the callee of 40h and 39h
where it is in the script (else it is in the system library, loaded past
the script's room).  A rebuilt script has them
moved with the statements.
"""
import struct

# ---- the archive


def decode(m):
    """A member's bytes unpacked."""
    size, dsize, count, fsize = struct.unpack_from("<4H", m, 1)
    flags = m[9:9 + fsize]
    data = m[9 + fsize:9 + fsize + dsize]
    ring = bytearray(0x800)
    r = fi = di = bits = cur = 0
    out = bytearray()
    for _ in range(count):
        if bits == 0:
            cur, fi, bits = flags[fi], fi + 1, 8
        bits -= 1
        ref = cur & 0x80
        cur = (cur << 1) & 0xFF
        if not ref:
            got = data[di:di + 1]
            di += 1
        else:
            pos, n = data[di] | data[di + 1] << 8, data[di + 2] + 1
            di += 3
            got = bytes(ring[(pos + k) & 0x7FF] for k in range(n))
        out += got
        for c in got:
            ring[r] = c
            r = (r + 1) & 0x7FF
    if len(out) != size:
        raise ValueError("a member unpacks to %d bytes, not %d" % (len(out), size))
    return bytes(out)


def encode(data):
    """data packed (greedy matches within the last 2048 bytes, as the ring
    holds them)."""
    flags, stream, count = bytearray(), bytearray(), 0
    heads = {}
    i, bit, cur = 0, 0, 0
    while i < len(data):
        best, at = 0, 0
        key = bytes(data[i:i + 3])
        for s in reversed(heads.get(key, [])[-64:]):
            if s < i - 0x800 + 256:
                break
            n = 0
            # (the source must have been written before this reference, and not be overwritten by it)
            while n < 256 and i + n < len(data) and s + n < i and data[s + n] == data[i + n]:
                n += 1
            if n > best:
                best, at = n, s
        if best >= 4:
            cur |= 0x80 >> bit
            stream += struct.pack("<HB", at & 0x7FF, best - 1)
            step = best
        else:
            stream.append(data[i])
            step = 1
        for k in range(i, i + step):
            heads.setdefault(bytes(data[k:k + 3]), []).append(k)
        i += step
        count += 1
        bit += 1
        if bit == 8:
            flags.append(cur)
            bit, cur = 0, 0
    if bit:
        flags.append(cur)
    return b"\xff" + struct.pack("<4H", len(data), len(stream), count, len(flags)) + bytes(flags) + bytes(stream)


class Archive:
    """One of the game's archives: its members by name."""

    def __init__(self, raw):
        self.raw = raw
        n = struct.unpack_from("<H", raw, 0)[0]
        self.entries = []
        for k in range(n):
            e = raw[2 + 19 * k:21 + 19 * k]
            name = e[:12].split(b"\0")[0].decode("ascii")
            kind, size, off = struct.unpack_from("<BHI", e, 12)
            self.entries.append((name, kind, off, size))

    def names(self):
        return [e[0] for e in self.entries]

    def read(self, name):
        for n, _k, off, size in self.entries:
            if n == name:
                m = self.raw[off:off + size]
                return decode(m) if m[:1] == b"\xff" else m
        raise KeyError(name)

    def rebuilt(self, changed):
        """The archive with the members in changed ({name: unpacked
        bytes}) packed again, every member laid out anew."""
        head = bytearray(struct.pack("<H", len(self.entries)))
        body = bytearray()
        start = 2 + 19 * len(self.entries)
        for name, kind, off, size in self.entries:
            m = encode(changed[name]) if name in changed else self.raw[off:off + size]
            if len(m) > 0xFFFF:
                raise SystemExit("%s: %d bytes packed, an archive member holds 65535" % (name, len(m)))
            head += name.encode("ascii").ljust(12, b"\0") + struct.pack("<BHI", kind, len(m), start + len(body))
            body += m
        return bytes(head + body)


# ---- the script

class Bad(Exception):
    pass


# argument formats: W word, E expression, X expressions until 00, Y expressions until 00 (which
# the caller takes), L argument list, V variable list, v variable, B byte, T text
OPS = {
    0x31: "WWE", 0x32: "WW", 0x33: "WE", 0x34: "WE", 0x35: "WX", 0x37: "E", 0x38: "",
    0x39: "WWE", 0x3B: "EB", 0x3C: "BBBBB", 0x3D: "", 0x3E: "BB", 0x3F: "WWE", 0x40: "WWE",
    0x41: "", 0x46: "L", 0x47: "L", 0x48: "L", 0x49: "L", 0x4A: "T", 0x4B: "vBB", 0x4C: "L",
    0x4D: "L", 0x4E: "WL", 0x4F: "L", 0x50: "L", 0x51: "L", 0x52: "L", 0x53: "L", 0x54: "L",
    0x55: "L", 0x56: "", 0x57: "", 0x58: "L", 0x59: "L", 0x5A: "L", 0x5B: "L", 0x5C: "L",
    0x5D: "L", 0x5E: "L", 0x5F: "L", 0x62: "L", 0x63: "L", 0x64: "L", 0x65: "V", 0x66: "",
    0x67: "L", 0x68: "VB", 0x69: "", 0x6A: "V", 0x6C: "L", 0x6D: "L", 0x6E: "L", 0x6F: "L",
    0x70: "", 0x72: "EvBEB", 0x73: "EvBEB", 0x74: "L", 0x75: "L", 0x76: "EEB", 0x77: "EEB",
    0x78: "L", 0x79: "EV", 0x7A: "L", 0x7B: "vBL", 0x7C: "", 0x7D: "L", 0x7E: "EvBEB",
    0x80: "", 0x81: "L", 0x82: "L", 0x83: "WWE", 0x84: "L", 0x85: "L",
}
# the W arguments that are addresses in the script, by opcode (their number among the words)
OPS_ADDRESS = {0x31: (1,), 0x32: (1,), 0x33: (0,), 0x34: (0,), 0x35: (0,), 0x39: (0,),
               0x3F: (0, 1), 0x40: (0,), 0x83: (1,)}
# calls (40h and 39h: the word after the return address): into the system library (at an address
# past every script, 7918h in Be-Yond), or into the script itself, an address there
OPS_CALL = {0x39: 1, 0x40: 1}
SUB71 = {0: "vBB", 1: "EB", 2: "L", 3: "EEB", 4: "EB", 5: "B", 7: "L"}
SUB6B = {0: "B", 1: "B", 2: "V", 3: "V", 4: "L", 5: "L", 6: "L", 7: "B", 8: "B", 9: "L"}
SUB3A = {2: "vB", 3: "vB", 4: "EEEEEEEEE", 5: "EEEvBvB", 6: "vB", 7: "E", 8: "E", 9: "E",
         10: "Y", 11: "", 12: ""}


def _var(d, i):
    t = d[i]
    if not 5 <= t < 0x20:
        raise Bad("variable %02x at %x" % (t, i))
    i += 3
    return _expr(d, i) if t < 0x0B else i


def _expr(d, i):
    first = True
    while True:
        b = d[i]
        if b == 0:
            return i + 1
        if first and b == 0x32:
            i += 5
        elif b >= 0x20:
            i += 1
        elif 1 <= b <= 4:
            i += 1 + b
        else:
            i = _var(d, i)
        first = False


def _arglist(d, i):
    while True:
        b = d[i]
        if b == 0:
            return i + 1
        if b == 0x11:
            i = d.index(bytes(1), i + 1) + 1
        elif b == 0x0F:
            i = _var(d, i) + 1
        else:
            i = _expr(d, i)


def _text(d, i):
    mode = d[i]
    i += 1
    while d[i] != 0:
        b = d[i]
        i += 1 if mode == 2 or b == 4 or 0x18 <= b <= 0x7F or 0xA0 <= b <= 0xDF else 2
    return i + 1


def _assign(d, i):
    i = _var(d, i)
    while True:
        i = _var(d, i) + 1 if d[i] == 0x0E else _expr(d, i)
        while True:
            b = d[i]
            if b == 0:
                return i + 1
            if b == 0x30:
                return _var(d, i + 1) + 1
            if b != 0x31:
                break
            i += 2


def _args(d, i, fmt):
    words = []
    for f in fmt:
        if f == "W":
            words.append(i)
            i += 2
        elif f == "B":
            i += 1
        elif f in "XY":
            while d[i] != 0:
                i = _expr(d, i)
            i += 1 if f == "X" else 0
        elif f == "E":
            i = _expr(d, i)
        elif f == "L":
            i = _arglist(d, i)
        elif f == "V":
            while d[i] != 0:
                i = _var(d, i) + 1
            i += 1
        elif f == "v":
            i = _var(d, i)
        elif f == "T":
            i = _text(d, i)
    return i, words


def statement(d, i):
    """(the offset after the statement at i, the offsets of its address words)"""
    op = d[i]
    if op == 0:
        return i + 1, []
    if op == 0x43:
        return _assign(d, i + 1), []
    if op == 0x3A:
        sub = d[i + 1]
        if sub == 1:
            # (an expression; seven more when it is 1, else one)
            return _args(d, i + 2, "EEEEEEEE" if d[i + 2:i + 5] == b"\x01\x01\x00" else "EE")[0] + 1, []
        if sub not in SUB3A:
            raise Bad("3a sub-command %02x at %x" % (sub, i))
        return _args(d, i + 2, SUB3A[sub])[0] + 1, []
    if op in (0x6B, 0x71):
        if d[i + 1] != 1 or d[i + 3] != 0:
            raise Bad("%02x without a constant sub-command at %x" % (op, i))
        fmt = (SUB71 if op == 0x71 else SUB6B).get(d[i + 2])
        if fmt is None:
            raise Bad("%02x sub-command %02x at %x" % (op, d[i + 2], i))
        return _args(d, i + 4, fmt)[0], []
    if op == 0x45:
        j = _var(d, i + 1)
        if d[j + 1] >= 5:
            return _var(d, j + 1) + 1, []
        return d.index(bytes(1), j) + 2, []
    if op == 0x44:
        j = _var(d, i + 1)
        w = struct.unpack_from("<H", d, j)[0]
        if w <= j:
            raise Bad("44 data end %x at %x" % (w, i))
        return w, [j]
    if op not in OPS:
        raise Bad("opcode %02x at %x" % (op, i))
    end, words = _args(d, i + 1, OPS[op])
    out = [words[n] for n in OPS_ADDRESS.get(op, ())]
    if op in OPS_CALL and struct.unpack_from("<H", d, words[OPS_CALL[op]])[0] < len(d):
        out.append(words[OPS_CALL[op]])
    return end, out


def tokenize(d):
    """[(start, end, address word offsets)] of every statement, the
    bytecode's start to its end."""
    i = struct.unpack_from("<H", d, 0)[0]
    out = []
    while i < len(d):
        s = i
        i, words = statement(d, i)
        out.append((s, i, words))
    if i != len(d):
        raise Bad("the last statement runs past the end")
    return out


def dictionary(d):
    """{byte: Shift-JIS character} of the file's dictionary."""
    start = struct.unpack_from("<H", d, 0)[0]
    out = {}
    for b in list(range(0x18, 0x80)) + list(range(0xA0, 0xE0)):
        k = b - (0x17 if b < 0x80 else 0x37)
        if 2 * k + 2 <= start:
            out[b] = d[2 * k:2 * k + 2]
    return out


def text_of(d, s, e, dic):
    """The Japanese of the text statement s..e ("\\n" for 04)."""
    mode = d[s + 1]
    out, i = "", s + 2
    while i < e - 1:
        b = d[i]
        if b == 4:
            out += "\n"
            i += 1
        elif mode == 2:
            out += bytes([b]).decode("cp932", "replace")
            i += 1
        elif b in dic:
            out += dic[b].decode("cp932", "replace")
            i += 1
        else:
            out += d[i:i + 2].decode("cp932", "replace")
            i += 2
    return out


def rebuild(d, toks, new):
    """The script with the statements new names ({start: bytes}) replaced
    and every address moved with the statements."""
    start = struct.unpack_from("<H", d, 0)[0]
    out = bytearray(d[:start])
    where = {}
    fixups = []
    for s, e, words in toks:
        where[s] = len(out)
        body = new.get(s, d[s:e])
        if s not in new:
            fixups += [(len(out) + (w - s), struct.unpack_from("<H", d, w)[0]) for w in words]
        out += body
    where[len(d)] = len(out)
    for at, target in fixups:
        if target not in where:
            raise Bad("an address %x lands on no statement" % target)
        if where[target] > 0xFFFF:
            raise SystemExit("a script grows past 64 KB")
        struct.pack_into("<H", out, at, where[target])
    return bytes(out)
