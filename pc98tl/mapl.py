"""The scene files (*.MPX) of MBS Truse's "MAPL" system (MAPL.EXE: Doop, Coming Heart).

An MPX file: "Mp16", the text's place in the file (a word, A), the text's length (a word, B), then
words the program reads after them (its variables' count and tables'); the code from 10h to A; the
text, A to A + B, every byte XORed with 24h: Shift-JIS strings each ended by a NUL; after the text,
the variables' names.  The code names a string by its place in the text (a word) and a place in the
code by its place in the file (a word), so the text may be laid out anew without moving the code.

The code (the interpreter's table at 0A42:503B, `parse`): an operation byte, then
* 00, 08, FE (wait for the player's choice), FF (the scene's end): nothing;
* 01, 03 (a menu's command): the place to go to, a string (its name), a condition;
* 04, 0A: a variable, a byte, a string; 05: the same and an assignment list;
* 06, 07 (a choice / a message, shown when the condition holds): a string, a condition, an assignment
  list;
* 09: a variable, a byte;
* 0B: an expression, words until the store operator (`store`: FDFAh in Doop's MAPL, FDFFh in Coming
  Heart's) and the variable it stores into.
A condition: items until a 00 byte, 08 / 09 (and / or) one byte, a comparison five (its kind, two
words).  An assignment list: five-byte items until a 00 byte.

The text: Shift-JIS; "%" and a letter (or two, as "%GF") is a command, its arguments after a comma up
to ";" ("%K" a key wait and a new window, "%N" a new line, "%R" a new line and a key wait).
"""
import struct

KEY = 0x24
ROOM = 0xFFF0        # the text's room (its places are words)


def cond(c, i):
    while c[i] != 0:
        i += 1 if c[i] in (8, 9) else 5
    return i + 1


def assign(c, i):
    while c[i] != 0:
        i += 5
    return i + 1


def parse(d, store):
    """[(place, op, [places of string words])]."""
    end = struct.unpack_from("<H", d, 4)[0]
    i, out = 0x10, []
    while i < end:
        op, a = d[i], i
        refs = []
        i += 1
        if op in (0x00, 0x08, 0xFE, 0xFF):
            pass
        elif op in (0x01, 0x03):
            refs.append(i + 2)
            i = cond(d, i + 4)
        elif op in (0x04, 0x0A):
            refs.append(i + 3)
            i += 5
        elif op == 0x05:
            refs.append(i + 3)
            i = assign(d, i + 5)
        elif op in (0x06, 0x07):
            refs.append(i)
            i = assign(d, cond(d, i + 2))
        elif op == 0x09:
            i += 3
        elif op == 0x0B:
            while True:
                w = struct.unpack_from("<H", d, i)[0]
                i += 2
                if w == store:
                    i += 2
                    break
        else:
            raise ValueError("unknown operation %02X at %X" % (op, a))
        out.append((a, op, refs))
    if i != end:
        raise ValueError("the code runs past the text's start")
    return out


def text(d):
    a, b = struct.unpack_from("<HH", d, 4)
    return bytes(x ^ KEY for x in d[a:a + b])


def strings(d, store):
    """[(text place, bytes, op)]: the strings the code names (in the text's order), with the operation
    that names it first."""
    t = text(d)
    by = {}
    for a, op, refs in parse(d, store):
        for r in refs:
            by.setdefault(struct.unpack_from("<H", d, r)[0], op)
    out = []
    for at in sorted(by):
        out.append((at, t[at:t.index(0, at)], by[at]))
    return out


def build(d, store, new):
    """The file with new {text place: bytes}: the text laid out again (every string, in its order) and
    the code's string words moved."""
    a, b = struct.unpack_from("<HH", d, 4)
    t = text(d)
    out, moved, at = bytearray(), {}, 0
    while at < len(t):
        e = t.index(0, at)
        moved[at] = len(out)
        out += new.get(at, t[at:e]) + b"\0"
        at = e + 1
    if len(out) > ROOM:
        raise ValueError("the text past 65520 bytes")
    code = bytearray(d[:a])
    for _p, _op, refs in parse(d, store):
        for r in refs:
            struct.pack_into("<H", code, r, moved[struct.unpack_from("<H", d, r)[0]])
    struct.pack_into("<H", code, 6, len(out))
    return bytes(code) + bytes(x ^ KEY for x in out) + d[a + b:]
