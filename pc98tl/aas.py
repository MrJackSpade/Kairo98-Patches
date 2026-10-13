"""The scripts (*.SCP, packed: pc98tl/lz96.py) of K. Hoshino's "AVG and ANIME SYSTEM" (ANI.EXE: Rookies).

A script is read from its start (the interpreter's table at 58C9h, `parse`).  A byte from 21h on starts
text: words, each a JIS character stored low byte first (the JIS code's second byte, then its first),
"80 nn" a speaker's name (`nn` 0 the player's, else the program's name table), until a byte under 21h.
The operations (their lengths the interpreter's):

* 01, 08, 10, 18, 1B (return), 1C: one byte; 05 (a choice menu, its items the text after it, each
  ended by 01): three;
* 03 (a jump), 04 (a call): the place (a word); 0A (a test): four bytes, then the place to jump to;
* 00, 07, 0D, 13, 17, 1D, 1F, 20: two bytes; 11: three; 09: four; 0B, 0C: five; 19: eleven;
* 02 (a picture: a byte and a file name), 06 (two: a byte and a name each), 0E (go to a script by
  name), 12, 14, 15: names ended by a NUL;
* 0F, 16, 1A, 1E: a kind byte giving the length (16: 0 and 1 a count of bytes after four, 2 ten).

`build` writes a script with new text: the jumps' and calls' places moved; `split` cuts one past its
64 KB segment into further files, each part going on to the next with 0E (a cut only before a message
no jump or routine reaches across, and before anything 0E would free).
"""
import struct

FIXED = {0x00: 2, 0x01: 1, 0x03: 3, 0x04: 3, 0x05: 3, 0x07: 2, 0x08: 1, 0x09: 4, 0x0A: 6, 0x0B: 5, 0x0C: 5,
         0x0D: 2, 0x10: 1, 0x11: 3, 0x13: 2, 0x17: 2, 0x18: 1, 0x19: 11, 0x1B: 1, 0x1C: 1, 0x1D: 2,
         0x1F: 2, 0x20: 2}
TARGET = {0x03: 1, 0x04: 1, 0x0A: 4}
TEXT = "text"
LIMIT = 0xFFF0          # a script's room (read in one 64 KB segment)


def _end(d, i):
    return d.index(0, i) + 1


def parse(d):
    """[(place, op or TEXT, bytes)]."""
    i, out = 0, []
    while i < len(d):
        op, a = d[i], i
        if op >= 0x21:
            while i < len(d) and d[i] >= 0x21:
                i += 2
            out.append((a, TEXT, d[a:i]))
            continue
        if op in FIXED:
            i += FIXED[op]
        elif op == 0x02:
            i = _end(d, i + 2)
        elif op == 0x06:
            i = _end(d, _end(d, i + 2) + 1)
        elif op in (0x0E, 0x12, 0x14, 0x15):
            i = _end(d, i + 1)
        elif op == 0x0F:
            sub = d[i + 1]
            if sub == 0:
                i = _end(d, i + 2)
            else:
                i += {1: 2, 2: 2, 3: 3, 4: 3, 5: 3, 6: 3, 7: 2, 8: 2, 9: 2}[sub]
        elif op == 0x16:
            sub = d[i + 1]
            i += 4 + max(0, d[i + 3] - d[i + 2]) if sub in (0, 1) else {2: 10}[sub]
        elif op == 0x1A:
            i += {0: 4, 1: 2, 2: 3, 3: 2}[d[i + 1]]
        elif op == 0x1E:
            i += {1: 2, 2: 2, 4: 2, 5: 2, 6: 3, 7: 2, 8: 2, 9: 2}[d[i + 1]]
        else:
            raise ValueError("unknown operation %02X at %X" % (op, a))
        out.append((a, op, d[a:i]))
    return out


def _write(ops, new, end):
    moved, at = {}, 0
    for a, op, b in ops:
        moved[a] = at
        at += len(new.get(a, b)) if op == TEXT else len(b)
    moved[end] = at
    if at > LIMIT:
        raise ValueError("a script past %d bytes" % LIMIT)
    out = bytearray()
    for a, op, b in ops:
        if op == TEXT:
            out += new.get(a, b)
            continue
        b = bytearray(b)
        if op in TARGET:
            t = TARGET[op]
            struct.pack_into("<H", b, t, moved[struct.unpack_from("<H", b, t)[0]])
        out += b
    return bytes(out)


def build(d, new):
    """The script with new {text place: bytes} (each at least a word, all bytes from 21h on)."""
    return _write(parse(d), new, len(d))


def _cuts(d, ops):
    """The op indices a script may be cut before: a message (a text after 01, not a choice's item)
    that no jump, call or routine (a call's place to the return after it) reaches across, before the
    first operation keeping a loaded file or the saved screen (06, 07, 14, 15, 1E 04: the script
    command 0E frees them)."""
    spans = []
    for a, op, b in ops:
        if op in TARGET:
            t = struct.unpack_from("<H", b, TARGET[op])[0]
            spans.append((min(a, t), max(a, t)))
            if op == 0x04:
                r = next((x for x, o, _b in ops if x >= t and o == 0x1B), len(d))
                spans.append((t, r))
    out, items = [], 0
    for k, (a, op, b) in enumerate(ops):
        if op in (0x06, 0x07, 0x14, 0x15) or (op == 0x1E and b[1] == 4):
            break
        if op == 0x05:
            items = b[1]
        elif op == TEXT:
            if items:
                items -= 1
            elif k and ops[k - 1][1] == 0x01 and not any(lo < a <= hi for lo, hi in spans):
                out.append(k)
    return out


def split(d, new, name, first=None):
    """[(file name, script)]: the script with new text, and when it is past its room, its tail in
    further files (`name(i)`, i from 1), each part ending in 0E naming the next: the program reads one
    script in a 64 KB segment, and 0E loads a script from its start (a save keeps the script's name).
    `first`: the first part's room instead (a test of the cut)."""
    ops = parse(d)
    if first is None:
        try:
            return [(name(0), _write(ops, new, len(d)))]
        except ValueError:
            pass
    cuts = _cuts(d, ops)
    size = [len(new.get(a, b)) if op == TEXT else len(b) for a, op, b in ops]
    parts, start, i = [], 0, 0
    while True:
        link = 2 + len(name(i + 1))
        room = first if first is not None and not i else LIMIT
        total, best = 0, None
        for k in range(start, len(ops)):
            total += size[k]
            if k + 1 in cuts and total + link <= room:
                best = k + 1
        if total <= room:
            best = None
        elif best is None or best == start:
            raise ValueError("a script past %d bytes, with nowhere to cut it" % LIMIT)
        stop = best if best is not None else len(ops)
        end = ops[stop][0] if stop < len(ops) else len(d)
        part = [(a - ops[start][0], op, b) for a, op, b in ops[start:stop]]
        for j, (a, op, b) in enumerate(part):
            if op in TARGET:
                b = bytearray(b)
                struct.pack_into("<H", b, TARGET[op], struct.unpack_from("<H", b, TARGET[op])[0] - ops[start][0])
                part[j] = (a, op, bytes(b))
        moved_new = {a - ops[start][0]: v for a, v in new.items() if ops[start][0] <= a < end}
        data = _write(part, moved_new, end - ops[start][0])
        if best is None:
            parts.append((name(i), data))
            return parts
        parts.append((name(i), data + b"\x0e" + name(i + 1).lower().encode("ascii") + b"\0"))
        start, i = best, i + 1
