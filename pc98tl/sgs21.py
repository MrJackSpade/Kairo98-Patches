"""Sogna's SGS21 (SGS21.COM: Viper F-40, Guynarock R): SGS.DAT and its *.WIN scripts.

SGS.DAT: "SGS.DAT 1.00", the files' count (a dword at 0Ch); from 10h a 32-byte entry each: the name
(16 bytes, NUL-padded), a flag dword (its top byte 01h: compressed), the stored size, the unpacked
size and the place (`dat`).  A compressed file (`unpack`): a flag byte read from its top bit, a
clear bit a literal, a set one a word (little-endian): (word >> 12) + 1 bytes copied from that far
back as its low 12 bits (`pack` writes it).  `dat_build` puts changed files at the archive's end and
points their entries there (the archive is some hundred megabytes of pictures and sounds).

SGS21.COM runs in protected mode (its 32-bit segment at file 3460h of the COM); its script loop
reads an op byte and jumps to the routine its table holds (`OPS`, the operands read off the
routines).  A script starts at its first byte.  The ops that go somewhere hold a word, a place in
the script (the goto 14h, the call 25h, the tests 2Eh-31h, 33h and 48h, and 15h, 16h, 29h, 2Bh and
53h, which set where a key or a timer goes); nothing else in a script is an address, so a script can
be laid out anew with them moved (`rebuild`; a script of at most 65535 bytes).

Op 21h shows a message: Shift-JIS up to a NUL, a byte below 80h drawn half-width by the program
itself (its column moves on by one, a full-width character's by two); 01h and a slot's number
draws the slot's text (a speaker's name), 814Fh "＾" clears the window, 818Fh "￥" starts a new
line, 8190h "＄" is skipped.  The window (op 20h: its place, its width in half-width cells and its
rows) breaks a line at its right edge and starts the next at the indent (op 22h, in cells); the
column carries on from one message to the next until a clear.  Op 24h sets a slot's text (Shift-JIS
up to a NUL, 64 bytes a slot); each script sets the speakers' names in a table it jumps over at its
start (`walk` reads those too, as items).  Op 3Eh shows a menu: its items' text inline (82 bytes an
item in the program's buffer) or 01h and a slot's number; the box is as wide as the longest item.
"""
import struct

MAGIC = b"SGS.DAT 1.00"
# an op's operands: B a byte, W a word, J a word that is a place in the script, S a string to its
# NUL, T a message, I a slot's text, N a count byte and that many 4-byte entries, Z byte pairs up to
# a lone 0, M a menu (see `walk`)
OPS = {
    0x00: "", 0x01: "WW", 0x02: "WW", 0x03: "BS", 0x04: "B", 0x05: "BW", 0x06: "BW", 0x07: "B",
    0x08: "", 0x09: "", 0x0A: "BWWWWZ", 0x0B: "B", 0x0C: "B", 0x0D: "", 0x0E: "", 0x0F: "",
    0x10: "B", 0x11: "", 0x12: "BBBWW", 0x13: "W", 0x14: "J", 0x15: "J", 0x16: "J",
    0x17: "BWWWWWWW", 0x18: "B", 0x19: "BB", 0x1A: "", 0x1B: "BS", 0x1C: "", 0x1D: "BS", 0x1E: "",
    0x1F: "", 0x20: "WWBB", 0x21: "T", 0x22: "B", 0x23: "B", 0x24: "BI", 0x25: "J", 0x26: "",
    0x27: "B", 0x28: "BWN", 0x29: "J", 0x2A: "", 0x2B: "J", 0x2C: "", 0x2D: "", 0x2E: "BWJ",
    0x2F: "BWJ", 0x30: "BWJ", 0x31: "BWJ", 0x32: "B", 0x33: "WJ", 0x34: "BW", 0x35: "B", 0x36: "B",
    0x37: "BW", 0x38: "BW", 0x39: "BW", 0x3A: "W", 0x3B: "", 0x3C: "", 0x3D: "WWWW", 0x3E: "M",
    0x3F: "B", 0x40: "B", 0x41: "N", 0x42: "", 0x43: "W", 0x44: "", 0x45: "B", 0x46: "", 0x47: "",
    0x48: "WJ", 0x49: "BBB", 0x4A: "S", 0x4B: "WW", 0x4C: "WWWW", 0x4D: "", 0x4E: "", 0x4F: "B",
    0x50: "BBBW", 0x51: "BBBW", 0x52: "B", 0x53: "J", 0x54: "", 0x55: "BB", 0x56: "S", 0x57: "S",
    0x58: "BB", 0x59: "BWWWWW", 0x5A: "B", 0x5B: "BN", 0x5C: "B", 0x5D: "B", 0x5E: "W", 0x5F: "",
    0x60: "BW", 0x61: "BWWWW", 0x62: "B",
}
STOP = {0x00, 0x14, 0x26, 0x4A}         # the end, the goto, the return, the next script
COMPRESSED = 0x01000000
ROOM = 0xFFFF                           # a script's places are words
SLOT = 0x40                             # a slot's room, its NUL in it
ITEM = 0x52                             # a menu item's room in the program's buffer, its NUL in it


def dat(raw):
    """[(name, flag, stored size, unpacked size, place)]."""
    if raw[:12] != MAGIC:
        raise ValueError("not an SGS.DAT")
    n = struct.unpack_from("<I", raw, 12)[0]
    out = []
    for k in range(n):
        e = raw[16 + 32 * k:48 + 32 * k]
        out.append((e[:16].split(b"\0")[0].decode("ascii"),) + struct.unpack_from("<IIII", e, 16))
    return out


def unpack(src, rsize):
    out, i = bytearray(), 0
    while len(out) < rsize:
        flags = src[i]
        i += 1
        for b in range(8):
            if len(out) >= rsize:
                break
            if flags & (0x80 >> b):
                w = src[i] | src[i + 1] << 8
                i += 2
                at = len(out) - (w & 0xFFF)
                for k in range((w >> 12) + 1):
                    out.append(out[at + k])
            else:
                out.append(src[i])
                i += 1
    return bytes(out)


def pack(data):
    """data as `unpack` reads it: the longest earlier match (3 to 16 bytes, within 4095) else a
    literal."""
    chains, items, i, n = {}, [], 0, len(data)

    def add(p):
        if p + 3 <= n:
            chains.setdefault(data[p:p + 3], []).append(p)
    while i < n:
        best, at = 0, 0
        for j in reversed(chains.get(data[i:i + 3], [])[-64:]):
            if i - j > 0xFFF:
                break
            k = 0
            while k < 16 and i + k < n and data[j + k] == data[i + k]:
                k += 1
            if k > best:
                best, at = k, j
                if k == 16:
                    break
        if best >= 3:
            items.append(struct.pack("<H", (best - 1) << 12 | (i - at)))
            for p in range(i, i + best):
                add(p)
            i += best
        else:
            items.append(data[i:i + 1])
            add(i)
            i += 1
    out = bytearray()
    for k in range(0, len(items), 8):
        group = items[k:k + 8]
        out.append(sum(0x80 >> b for b, it in enumerate(group) if len(it) == 2))
        for it in group:
            out += it
    return bytes(out)


def read(raw, name):
    for nm, flag, cs, rs, off in dat(raw):
        if nm.upper() == name.upper():
            d = raw[off:off + cs]
            return unpack(d, rs) if flag & COMPRESSED else d
    raise KeyError(name)


def dat_build(raw, new):
    """The archive with new {name: unpacked bytes} (stored compressed) at its end."""
    out = bytearray(raw)
    for k, (nm, flag, cs, rs, off) in enumerate(dat(raw)):
        if nm in new:
            b = pack(new[nm]) if flag & COMPRESSED else new[nm]
            struct.pack_into("<IIII", out, 32 + 32 * k, flag, len(b), len(new[nm]), len(out))
            out += b
    return bytes(out)


def _op_end(d, i):
    """(the op's end, its texts [(kind, start, end past the NUL)], its pointers' places)."""
    op = d[i]
    texts, ptrs = [], []
    i += 1
    for c in OPS[op]:
        if c == "B":
            i += 1
        elif c == "W":
            i += 2
        elif c == "J":
            ptrs.append(i)
            i += 2
        elif c in "STI":
            j = d.index(0, i) + 1
            if c != "S":
                texts.append(({"T": "text", "I": "item"}[c], i, j))
            i = j
        elif c == "N":
            i += 1 + 4 * d[i]
        elif c == "Z":
            while d[i]:
                i += 2
            i += 1
        elif c == "M":
            i += 7
            for _k in range(d[i - 1]):
                if d[i] == 1:
                    i = d.index(0, i + 2) + 1
                else:
                    j = d.index(0, i) + 1
                    texts.append(("menu", i, j))
                    i = j
    return i, texts, ptrs


def walk(d):
    """(pointer places, events: ("op", place, op, end), ("text", start, end past its NUL) a message,
    ("item", start, end) a slot's text (op 24h), ("menu", start, end) a menu's inline item); the
    code followed from the start through every jump, and the slots' table each script jumps over;
    every pointer checked to land on an op."""
    todo, starts, ptrs, ev = [(0, None)], set(), set(), set()
    while todo:
        i, origin = todo.pop()
        while i < len(d) and i not in starts:
            op = d[i]
            if op not in OPS:
                raise ValueError("op %02x at %x (reached from the jump at %s)" % (
                    op, i, "start" if origin is None else "%x" % origin))
            j, texts, ps = _op_end(d, i)
            starts.add(i)
            ev.add(("op", i, op, j))
            ev.update(texts)
            for p in ps:
                ptrs.add(p)
                todo.append((struct.unpack_from("<H", d, p)[0], i))
            if op in STOP:
                break
            i = j
    for e in sorted(ev):
        if e[0] == "op" and e[2] in STOP:
            i = e[3]
            while i < len(d) and i not in starts and d[i] == 0x24:
                j, texts, _ps = _op_end(d, i)
                ev.add(("op", i, 0x24, j))
                ev.update(texts)
                starts.add(i)
                i = j
    for p in ptrs:
        if struct.unpack_from("<H", d, p)[0] not in starts:
            raise ValueError("a pointer at %x to %x, no op's start" % (p, struct.unpack_from("<H", d, p)[0]))
    return sorted(ptrs), sorted(ev, key=lambda e: (e[1], e[0] != "op"))


def rebuild(d, new):
    """The script with new {start: (end, bytes)} spans put in, its pointers moved."""
    ptrs, _ev = walk(d)
    out, at, shift = bytearray(), 0, []
    for s, (e, b) in sorted(new.items()):
        out += d[at:s]
        shift.append((s, e, len(out) - s, len(out) + len(b) - e))
        out += b
        at = e
    out += d[at:]

    def moved(t):
        dt = 0
        for s, e, before, after in shift:
            if t >= e:
                dt = after
            elif t >= s:
                return t + before
        return t + dt
    for p in ptrs:
        struct.pack_into("<H", out, moved(p), moved(struct.unpack_from("<H", d, p)[0]))
    return bytes(out)
