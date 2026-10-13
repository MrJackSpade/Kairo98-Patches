"""The scripts (*.DIA) of Silky's "Image Gaming System" (IGS.EXE, 1995, by spinout: Koihime).

A DIA file is a word, the data's length, the data (each byte XOR 80h), a word, the code's length, and
the code.  The program (`load`) reads the data into its segment at 0C00h (0000-0BFFh are its own
variables) and the code at the segment's top, ending at 8000h; the stack is between the two.

The data is NUL-ended strings (Shift-JIS) and variables; the code refers to a string by its address
(0C00h + its place), pushed as a word immediate ("27 0F" and the word).

The code is a stack machine's (the interpreter at 4182h, `parse`).  An operand is a mode byte: from
80h a register (its low nibble); else an immediate or a memory reference (bits 2-3: 0 the frame, 4 a
second base, 8 absolute, 0C an immediate), with no further bytes, a word or a byte (bits 0-1: 0; 1 or
3; 2).  The operations:

* 01-04, 1C: none (04 returns); 05-08: an operand; 09: a byte; 0A: a word; 0B: two operands;
* 0C (a call), 0E-19 (jumps): a word, the place relative to the next operation; 0D: a word, a
  system function (its low byte) and its count of arguments (the high byte), popped from the stack;
* 1A, 1B: a word (a call through a table);
* 20h-5Fh: the high nibble the operation, the low a register, or 7 and an operand; 60h-FFh the
  same, then a second operand.

A message is drawn by the script's own routine for its window (`DRAW`: function 05 with the string,
-1, -1 and the window), the string pushed before the call.
"""
import bisect
import re
import struct

DATA_AT = 0x0C00
TOP = 0x8000
STACK = 0x200           # (the room the build keeps for the stack, between the data and the code)
WORD = set(range(0x0C, 0x1C))
ZERO = {0x01, 0x02, 0x03, 0x04, 0x1C}
BRANCH = {0x0C} | set(range(0x0E, 0x1A))
DRAW = re.compile(rb"\x24\xf4\x85\x27\x12\x04\x27\x0e\xff\x27\x0e\xff(\x27\x0c|\x27\x0e.)"
                  rb"\x0d\x05\x04\xc5\x0e\x08\x34\x04", re.S)


def load(d):
    """(data, code): the data decoded."""
    dl = struct.unpack_from("<H", d, 0)[0]
    cl = struct.unpack_from("<H", d, 2 + dl)[0]
    if 4 + dl + cl != len(d):
        raise ValueError("not a DIA file")
    return bytes(b ^ 0x80 for b in d[2:2 + dl]), d[4 + dl:]


def save(data, code):
    if DATA_AT + len(data) + len(code) > TOP:
        raise ValueError("the data and the code past the segment")
    return (struct.pack("<H", len(data)) + bytes(b ^ 0x80 for b in data) +
            struct.pack("<H", len(code)) + code)


def operand(c, i):
    m = c[i]
    if m & 0x80:
        return i + 1
    return i + 1 + {0: 0, 1: 2, 2: 1, 3: 2}[m & 3]


def parse(c):
    """[(place, op, bytes)], places from the code's start."""
    out, i = [], 0
    while i < len(c):
        a, op = i, c[i]
        i += 1
        if op in ZERO:
            pass
        elif 0x05 <= op <= 0x08:
            i = operand(c, i)
        elif op == 0x09:
            i += 1
        elif op == 0x0A:
            i += 2
        elif op == 0x0B:
            i = operand(c, operand(c, i))
        elif op in WORD:
            i += 2
        elif op >= 0x20:
            if op & 0x0F == 7:
                i = operand(c, i)
            if op >= 0x60:
                i = operand(c, i)
        else:
            raise ValueError("unknown operation %02X at %X" % (op, a))
        out.append((a, op, c[a:i]))
    if i != len(c):
        raise ValueError("the code runs past its end")
    return out


def target(a, b):
    return a + 3 + struct.unpack_from("<h", b, 1)[0]


def strings(data):
    """{address: bytes}: the data's NUL-ended strings."""
    out, i = {}, 0
    while i < len(data):
        j = data.index(0, i)
        out[DATA_AT + i] = data[i:j]
        i = j + 1
    return out


def draws(code):
    """{routine's place: window}: the script's message routines."""
    return {m.start(): (0 if m.group(1) == b"\x27\x0c" else m.group(1)[2]) for m in DRAW.finditer(code)}


def pushed(b):
    """The word an operation pushes as an immediate ("27 0F" and the word), or None."""
    if len(b) == 4 and b[0] == 0x27 and b[1] == 0x0F:
        return struct.unpack_from("<H", b, 2)[0]
    return None


def words(b):
    """The words an operation's operands hold (immediates and displacements)."""
    op, out = b[0], []

    def one(i):
        m = b[i]
        if m & 0x80:
            return i + 1
        n = {0: 0, 1: 2, 2: 1, 3: 2}[m & 3]
        if n == 2:
            out.append(struct.unpack_from("<H", b, i + 1)[0])
        return i + 1 + n
    if 0x05 <= op <= 0x08:
        one(1)
    elif op == 0x0B:
        one(one(1))
    elif op >= 0x20:
        i = 1
        if op & 0x0F == 7:
            i = one(i)
        if op >= 0x60:
            one(i)
    return out


def regions(ops):
    """The routines' starts (sorted): 0 and every call's target; an operation belongs to the last
    start at or before it."""
    return sorted({0} | {target(a, b) for a, op, b in ops if op == 0x0C})


def _owner(starts, a):
    lo, hi = 0, len(starts)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if starts[mid] <= a:
            lo = mid
        else:
            hi = mid
    return starts[lo]


def layout(ops):
    """(main, [routine]): the routine the entry calls first and the routines it calls (a scene's
    parts, called one after another as the saved state says)."""
    first = next((target(a, b) for a, op, b in ops if op == 0x0C), None)
    if first is None:
        return None, []
    starts = regions(ops)
    parts = [target(a, b) for a, op, b in ops if op == 0x0C and _owner(starts, a) == first]
    return first, sorted(set(t for t in parts if t != first))


def reachable(ops, roots):
    """The routines (starts) the roots reach through calls."""
    starts = regions(ops)
    calls = {}
    for a, op, b in ops:
        if op == 0x0C:
            calls.setdefault(_owner(starts, a), set()).add(target(a, b))
    seen, todo = set(), list(roots)
    while todo:
        r = todo.pop()
        if r in seen:
            continue
        seen.add(r)
        todo.extend(calls.get(r, ()))
    return seen


def pushes_in(ops, routines):
    """The words pushed as immediates by the routines' operations."""
    starts = regions(ops)
    return {pushed(b) for a, op, b in ops if pushed(b) is not None and _owner(starts, a) in routines}


def build(d, new, extra=None, calls=None, more=None, drop=(), pokes=None):
    """The script with new strings ({address: bytes}, the strings pushed as "27 0F"), further strings
    (`more`: {key: bytes}, no old place), code appended (`extra(moved, place)`: the code for `place`,
    the strings' new addresses given), and calls moved (`calls`, {call's place: new target}, read
    after `extra`).  The old strings' room is freed and the new ones packed into it (the longest
    first, each into the smallest room it fits; the same string once), the rest after the data; the
    stack keeps at least STACK bytes between the data and the code."""
    data, code = load(d)
    data = bytearray(data)
    old = strings(bytes(data))
    refs = sorted({w for _a, _op, b in parse(code) for w in words(b)})
    free = []
    for at in set(new) | set(drop):             # (`drop`: strings no live code uses, left empty)
        n = len(old[at]) + 1
        k = bisect.bisect_right(refs, at)
        if k < len(refs) and refs[k] < at + n:  # (a place inside it the code uses: a table; kept)
            continue
        data[at - DATA_AT:at - DATA_AT + n] = bytes(n)
        free.append([at, n])
    moved, placed = {}, {}
    every = dict(new)
    every.update(more or {})
    for at, s in sorted(every.items(), key=lambda kv: -len(kv[1])):
        if s in placed:
            moved[at] = placed[s]
            continue
        need = len(s) + 1
        fits = [f for f in free if f[1] >= need]
        if fits:
            f = min(fits, key=lambda f: f[1])
            where = f[0]
            f[0] += need
            f[1] -= need
        else:
            where = DATA_AT + len(data)
            data += bytes(need)
        data[where - DATA_AT:where - DATA_AT + need] = s + b"\0"
        moved[at] = placed[s] = where
    out = bytearray(code)
    for a, op, b in parse(code):
        v = pushed(b)
        if v is not None and v in moved and moved[v] != v:
            struct.pack_into("<H", out, a + 2, moved[v])
    tail = extra(moved, len(code)) if extra else b""
    for at, b in (pokes(moved) if pokes else {}).items():   # (code changed in place: `pokes(moved)`)
        out[at:at + len(b)] = b
    for at, t in (calls or {}).items():
        struct.pack_into("<h", out, at + 1, t - (at + 3))
    room = TOP - DATA_AT - len(data) - len(code) - len(tail)
    if room < STACK:
        raise ValueError("%d bytes left for the stack (%d needed)" % (room, STACK))
    return save(bytes(data), bytes(out) + tail), moved
