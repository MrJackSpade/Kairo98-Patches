"""Active's Angel Halo (MAIN98.EXE): FDHALO.PAK and its scripts.

FDHALO.PAK: a word (4000h), the files' count, a (key, offset) pair of dwords for each file in the
keys' order (the key a hash of its name, the program's binary search; the last (0, the archive's size)
an empty file's), then for each its 12-byte name (8 and 3, NUL-padded) and its size, then the files one
after another (`Pak`).

A script (*.HGO): a word, its entries' count, the entries (six words: the kind, a byte; the start and
end of its marker in the code; a case's value; the name's place; the condition's place), then the code.
The places are offsets in the code.  The kinds: `$` a label, `I` a choice's item (its name the item's
text; the items after a label are its menu), `!` the script's entry, `[` a jump's target, `{` `}` a
switch's braces and `S` its cases (their code the switch's own ops).  A named entry's marker is 0Dh (0Ch
for `[`), its kind and its name, up to a NUL; the code runs past it.

The code is ops (`MAIN`): 00h an expression (sub-codes up to 05h: 01h an operand (`@`/`_` and a
variable's name, `$` and a label's, `n` and a word), 02h an operator byte), 01h an operand, 03h a
picture's name, 04h a text (Shift-JIS up to a NUL, its controls a backslash and a capital: `\\W` the key
wait and a cleared window, `\\P` the key wait, `\\N` a new line, `\\\\` no new line after the text; `\\C`,
`\\K`, `\\S`, `\\V` with two bytes more), 06h a switch (its word the place after the switch), 08h and 09h
conditions (their word the place they go to when the condition does not hold), 0Ah a label's name, 0Bh a
sub-op and its operands (`SUB`), 0Ch a byte and a string, 0Dh a byte (the end of a section).  Every place
is an offset in the code, so a script can be laid out anew with them moved (`rebuild`).

*.GMO (the main menu's): the items' records, at 172h (an item, the place of its description) pairs up to
7FFFh, at 1FAh the descriptions' length, from 21Ch the descriptions (Shift-JIS up to a NUL) (`gmo`,
`gmo_build`).

OPENING.DAT: lines of text: `G` and a picture, `V` and a wait, `W` and a voice, `M`, and `>N` and the N
lines shown together.

MAIN98.EXE draws a text a Shift-JIS character or an ASCII letter at a time (a letter half-width) and
breaks the line at the window's edge (window A 56 half-width cells and 4 lines, window B 76 and 3; the
pictures' sizes choose them); a text starts a new line and the window pages itself.
"""
import struct

MAIN = {0: "X", 1: "O", 2: "B", 3: "S", 4: "T", 5: "", 6: "P", 7: "", 8: "P", 9: "P", 0xA: "S", 0xB: "D",
        0xC: "BS", 0xD: "B"}
SUB = {0: "S", 1: "SWWW", 2: "SWWW", 3: "SSW", 4: "", 5: "W", 6: "W", 7: "W", 8: "S", 9: "W", 0xA: "WWWWW",
       0xB: "WWW", 0xC: "", 0xD: "S", 0xE: "W", 0xF: "W", 0x19: "", 0x1A: "", 0x1B: "S", 0x1C: "S", 0x1D: "",
       0x1E: "S", 0x1F: "", 0x20: "", 0x21: "", 0x22: "", 0x23: "", 0x24: "W", 0x80: "", 0x8A: "W", 0x8C: "S",
       0x90: "S", 0x96: "", 0x97: "", 0x9B: "WWWWWWWWW"}
for _k in range(0x10, 0x19):
    SUB[_k] = ""
NAMED = b"$I!["                  # the entries whose marker is 0Dh, the kind and a name
ESC_ARG = set(b"CKSV")           # the controls with two bytes after them
LINE = 56                        # window A's width (the narrower), in half-width cells


class Pak:
    def __init__(self, raw):
        self.head, n = struct.unpack_from("<HH", raw, 0)
        keys = [struct.unpack_from("<II", raw, 4 + 8 * k) for k in range(n)]
        p = 4 + 8 * n
        self.files = []
        for k in range(n):
            name, size = raw[p:p + 12], struct.unpack_from("<I", raw, p + 12)[0]
            off = keys[k][1]
            self.files.append([name, keys[k][0], raw[off:off + size]])
            p += 16

    @staticmethod
    def show(name):
        b = name.rstrip(b"\0")
        base, ext = b[:8].rstrip(b" \0"), b[8:11].rstrip(b" \0")
        return (base + (b"." + ext if ext else b"")).decode("ascii", "replace")

    def names(self):
        return [self.show(f[0]) for f in self.files]

    def read(self, name):
        return next(f[2] for f in self.files if self.show(f[0]) == name)

    def replace(self, name, data):
        next(f for f in self.files if self.show(f[0]) == name)[2] = data

    def build(self):
        n = len(self.files)
        out = bytearray(struct.pack("<HH", self.head, n))
        off = 4 + 24 * n
        table, names = bytearray(), bytearray()
        for name, key, data in self.files:
            table += struct.pack("<II", key, off)
            names += name + struct.pack("<I", len(data))
            off += len(data)
        return bytes(out + table + names + b"".join(f[2] for f in self.files))


GMO_INDEX, GMO_SIZE, GMO_TEXT = 0x172, 0x1FA, 0x21C


def gmo(d):
    """[(item, its description's bytes)] in the file's order."""
    out, i = [], GMO_INDEX
    while i + 4 <= GMO_SIZE:
        item, off = struct.unpack_from("<HH", d, i)
        if item == 0x7FFF:
            break
        s = GMO_TEXT + off
        out.append((item, d[s:d.index(0, s)]))
        i += 4
    return out


def gmo_build(d, texts):
    """The menu with the descriptions texts {item: bytes} put in, the places and the length set."""
    out = bytearray(d[:GMO_TEXT])
    body = bytearray()
    for k, (item, old) in enumerate(gmo(d)):
        struct.pack_into("<HH", out, GMO_INDEX + 4 * k, item, len(body))
        body += texts.get(item, old) + b"\0"
    struct.pack_into("<H", out, GMO_SIZE, len(body))
    return bytes(out + body)


def string(d, i):
    return d.index(0, i) + 1


def operand(d, i):
    c = d[i]
    if c in (0x5F, 0x40):
        return string(d, i)
    if c == 0x24:
        return string(d, i + 1)
    if c == 0x6E:
        return i + 3
    raise ValueError("an operand's %02x at %x" % (c, i))


def header(h):
    n = struct.unpack_from("<H", h, 0)[0]
    return [list(struct.unpack_from("<6H", h, 2 + 12 * k)) for k in range(n)], 2 + 12 * n


def walk(h):
    """(the code, the entries, [the places of the code's pointer words], events in the code's order:
    ("text", start, end) an op 04h's text (end past its NUL), ("item", entry index), ("op", place, op,
    sub-op)); every pointer checked to land on an op."""
    ents, code = header(h)
    d = h[code:]
    marks = {e[1]: e[2] for e in ents if e[0] in NAMED}
    names = {e[1]: k for k, e in enumerate(ents) if e[0] in NAMED}
    i, starts, ptrs, ev = 0, set(), [], []
    while i < len(d):
        starts.add(i)
        if i in marks:
            if d[i] not in (0x0C, 0x0D):
                raise ValueError("a marker at %x is no op 0Ch or 0Dh" % i)
            if ents[names[i]][0] == ord("I"):
                ev.append(("item", names[i]))
            i = marks[i]
            continue
        op = d[i]
        start = i
        i += 1
        f = MAIN.get(op)
        if f is None:
            raise ValueError("op %02x at %x" % (op, start))
        sub = None
        if f == "X":
            while True:
                s = d[i]
                i += 1
                if s == 5:
                    break
                if s == 1:
                    i = operand(d, i)
                elif s == 2:
                    i += 1
                elif s != 0:
                    raise ValueError("an expression's %02x at %x" % (s, i - 1))
            ev.append(("op", start, op, None))
            continue
        if f == "O":
            i = operand(d, i)
            ev.append(("op", start, op, None))
            continue
        if f == "D":
            sub = d[i]
            i += 1
            if sub not in SUB:
                raise ValueError("op 0Bh's sub-op %02x at %x" % (sub, start))
            f = SUB[sub]
        ev.append(("op", start, op, sub))
        for c in f:
            if c == "S":
                i = string(d, i)
            elif c == "T":
                j = string(d, i)
                ev.append(("text", i, j))
                i = j
            elif c == "B":
                i += 1
            elif c == "W":
                i += 2
            elif c == "P":
                ptrs.append(i)
                i += 2
    if i != len(d):
        raise ValueError("the code runs past its end")
    starts.add(len(d))
    for p in ptrs:
        if struct.unpack_from("<H", d, p)[0] not in starts:
            raise ValueError("a pointer at %x to %x, no op's start" % (p, struct.unpack_from("<H", d, p)[0]))
    for e in ents:
        if e[1] not in starts or e[2] not in starts:
            raise ValueError("an entry (%s) off the ops" % chr(e[0]))
    return d, ents, ptrs, ev


def item_name(d, e):
    return d[e[4]:d.index(0, e[4])]


def rebuild(h, new):
    """The script with new {start: (end, bytes)} put in place of the code's bytes start:end (an item's
    marker by its start), every place moved."""
    d, ents, ptrs, _ev = walk(h)
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
    head = bytearray(struct.pack("<H", len(ents)))
    for e in ents:
        e = list(e)
        e[1], e[2] = moved(e[1]), moved(e[2])
        if e[0] in NAMED:
            e[4] = moved(e[4])
        if e[5]:
            e[5] = moved(e[5])
        head += struct.pack("<6H", *e)
    return bytes(head + out)
