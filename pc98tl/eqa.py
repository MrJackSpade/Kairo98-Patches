"""The scripts (*.EQA, in LOVE.EAR: pc98tl/ear.py) of the EQAP32 engine (EQAP32.EXE: Love Escalator).

A script is read into a 64 KB buffer and run from its start; places in it are words, offsets from its
start.  An operation is a byte (the interpreter's table at 23150h, `parse`) and its operands:

* 00 text 00: a message.  The text is words, each a JIS character less 2020h stored first byte first
  (the text layer's code); a byte from 80h on is a control: 80 wait for a click, 81 a new line, 82 / 83
  draw slowly / at once, 84 clear the window, 90h-CFh the string in slot (byte - 90h) (op 2D).
* 01: the window (a dword: column, row, width in cells, rows; a byte, the column a wrapped line starts).
* 0F / 10: a menu: an 8-byte header (+2 a column's width, +3 its rows, +4 an item's width in cells,
  +6 the variable the choice goes to, +7 the count), then the items, each words ended by a 00 byte
  (in 10 each after a variable: the item is left out when it is 0).
* 2D slot text 00: a string into a 16-byte slot (a longer one runs on into the next).
* 14 / 15 place: a jump / a call (16 returns); 17-1C, 7A, 7B var, value, place: a test and a jump;
  1D var then a table of places (it ends at the lowest of them).
* 30-34, 36-38, 3A, 3B: a byte (1) and a file name, ended by a NUL (36, 37 then a byte); 32 goes to
  another script, 38 calls one (39 returns to the caller).
* 05: two bytes and a string of glyph codes; 50 / 52: four / five bytes then words ended by a 00 byte
  (an animation's frames); the rest a fixed count of bytes (`FIXED`).

`build` writes a script with new strings: the places moved.  `split` cuts one past its buffer into
further scripts, each part going on to the next with 32 (a cut only before a message no jump, call or
table reaches across).
"""
import struct

FIXED = {0x01: 5, 0x02: 2, 0x03: 1, 0x04: 1, 0x06: 0, 0x07: 0, 0x08: 0, 0x09: 34, 0x0A: 0, 0x0B: 4,
         0x0C: 0, 0x0D: 2, 0x0E: 2, 0x13: 0, 0x14: 2, 0x15: 2, 0x16: 0, 0x17: 4, 0x18: 4, 0x19: 4,
         0x1A: 4, 0x1B: 4, 0x1C: 4, 0x1E: 2, 0x1F: 2, 0x20: 2, 0x21: 2, 0x22: 2, 0x24: 1, 0x25: 1,
         0x26: 2, 0x27: 2, 0x28: 2, 0x2A: 0, 0x2B: 1, 0x2C: 1, 0x2E: 0, 0x2F: 0, 0x39: 0, 0x3C: 1,
         0x3D: 1, 0x3E: 1, 0x3F: 1, 0x40: 51, 0x41: 1, 0x46: 8, 0x47: 0, 0x48: 1, 0x49: 2, 0x4A: 2,
         0x4B: 2, 0x4C: 13, 0x4D: 2, 0x4E: 6, 0x4F: 12, 0x51: 0, 0x53: 1, 0x54: 1, 0x55: 17,
         0x56: 18, 0x57: 0, 0x59: 0, 0x5A: 1, 0x5B: 0, 0x5C: 0, 0x5D: 1, 0x5E: 2, 0x5F: 0, 0x60: 1,
         0x61: 1, 0x62: 2, 0x64: 1, 0x65: 0, 0x66: 1, 0x67: 0, 0x68: 1, 0x69: 1, 0x6B: 1, 0x6C: 1,
         0x76: 0, 0x77: 0, 0x78: 1, 0x7A: 4, 0x7B: 4, 0x7C: 1, 0x7D: 1, 0x7E: 0, 0x7F: 2, 0x80: 2,
         0x81: 1, 0x82: 0, 0x83: 0, 0x84: 1, 0x85: 2, 0x86: 2, 0x87: 2, 0x88: 1, 0x89: 1}
NAMED = (0x30, 0x31, 0x32, 0x33, 0x34, 0x38, 0x3A, 0x3B)
TARGET = {0x14: 1, 0x15: 1, 0x17: 3, 0x18: 3, 0x19: 3, 0x1A: 3, 0x1B: 3, 0x1C: 3, 0x7A: 3, 0x7B: 3}
LIMIT = 0x10000         # a script's buffer


def _z(d, i):
    return d.index(0, i) + 1


def _words(d, i):
    while d[i] != 0:
        i += 2
    return i + 1


def parse(d):
    """[(place, op, bytes)]."""
    out, i = [], 0
    while i < len(d):
        a, op = i, d[i]
        i += 1
        if op == 0x00:
            i = _z(d, i)
        elif op in FIXED:
            i += FIXED[op]
        elif op in NAMED or op == 0x2D:
            i = _z(d, i + 1)
        elif op == 0x05:
            i = _z(d, i + 2)
        elif op in (0x36, 0x37):
            i = _z(d, i + 1) + 1
        elif op == 0x0F:
            n = d[i + 7]
            i += 8
            for _k in range(n):
                i = _words(d, i)
        elif op == 0x10:
            n = d[i + 7]
            i += 8
            for _k in range(n):
                i = _words(d, i + 1)
        elif op == 0x50:
            i = _words(d, i + 4)
        elif op == 0x52:
            i = _words(d, i + 5)
        elif op == 0x1D:
            i += 1
            low = None
            while low is None or i < low:
                t = struct.unpack_from("<H", d, i)[0]
                low = t if low is None else min(low, t)
                i += 2
            if i != low:
                raise ValueError("a table at %X ending at %X, its lowest place %X" % (a, i, low))
        else:
            raise ValueError("unknown operation %02X at %X" % (op, a))
        out.append((a, op, d[a:i]))
    return out


def strings(op, b):
    """[(offset in the operation, bytes, kind)]: its text: "msg" (00), "item" (0F, 10), "slot" (2D)."""
    if op == 0x00:
        return [(1, b[1:-1], "msg")]
    if op == 0x2D:
        return [(2, b[2:-1], "slot")]
    if op in (0x0F, 0x10):
        out, i = [], 9
        for _k in range(b[8]):
            if op == 0x10:
                i += 1
            j = _words(b, i)
            out.append((i, b[i:j - 1], "item"))
            i = j
        return out
    return []


def with_strings(op, b, new):
    """The operation with its strings replaced ({offset: bytes})."""
    out, last = bytearray(), 0
    for at, s, _k in strings(op, b):
        out += b[last:at] + new.get(at, s)
        last = at + len(s)
    return bytes(out + b[last:])


def _places(op, b):
    if op in TARGET:
        return [TARGET[op]]
    if op == 0x1D:
        return list(range(2, len(b), 2))
    return []


def _write(ops, new, end, base=0):
    moved, at = {}, 0
    for a, op, b in ops:
        moved[a] = at
        at += len(new.get(a, b))
    moved[end] = at
    if at > LIMIT:
        raise ValueError("a script past %d bytes" % LIMIT)
    out = bytearray()
    for a, op, b in ops:
        b = bytearray(new.get(a, b))
        for at, op2, b2 in (parse(bytes(b)) if a in new else [(0, op, b)]):   # (operations written anew)
            for t in _places(op2, b2):
                struct.pack_into("<H", b, at + t, moved[struct.unpack_from("<H", b2, t)[0] - base])
        out += b
    if len(out) > LIMIT:
        raise ValueError("a script past %d bytes" % LIMIT)
    return bytes(out)


def build(d, new):
    """The script with new {operation place: bytes} (operations of the same kind)."""
    return _write(parse(d), new, len(d))


def _tail(d, ops):
    """The index the script's shared routines start at (after its body: reached only by calls, their
    jumps among themselves), or len(ops)."""
    idx = {a: k for k, (a, _o, _b) in enumerate(ops)}
    for t in sorted({struct.unpack_from("<H", b, 1)[0] for _a, op, b in ops if op == 0x15}):
        if t not in idx:
            continue
        ok = True
        for a, op, b in ops:
            for at in _places(op, b):
                p = struct.unpack_from("<H", b, at)[0]
                if (a >= t and p < t) or (a < t <= p and op != 0x15):
                    ok = False
        if ok:
            return idx[t]
    return len(ops)


def _cuts(d, ops, tail=None):
    """The indices a script's body may be cut before: a message no jump, table or call (but one into
    the shared routines after the body) reaches across, nor a routine it calls."""
    tail = len(ops) if tail is None else tail
    end = ops[tail][0] if tail < len(ops) else len(d)
    spans = []
    for a, op, b in ops[:tail]:
        for t in _places(op, b):
            p = struct.unpack_from("<H", b, t)[0]
            if op == 0x15 and p >= end:
                continue
            spans.append((min(a, p), max(a, p)))
            if op == 0x15:
                r = next((x for x, o, _b in ops if x >= p and o == 0x16), len(d))
                spans.append((p, r))
    out = []
    for k, (a, op, b) in enumerate(ops[:tail]):
        if op == 0x00 and k and not any(lo < a <= hi for lo, hi in spans):
            out.append(k)
    return out


def _target(op, b):
    return struct.unpack_from("<H", b, TARGET[op])[0]


def layout(d, ops):
    """(hub, [scene], tail) as lists of op indices, when the script is a hub of jumps (14, before its
    first message) to scenes that end by returning to the calling script (39), sharing routines after
    the last scene; else None."""
    first_msg = next((k for k, (_a, op, _b) in enumerate(ops) if op == 0x00), len(ops))
    starts = sorted({_target(op, b) for a, op, b in ops[:first_msg] if op == 0x14 and _target(op, b) > a})
    if len(starts) < 2:
        return None
    hub_end = starts[0]
    calls = [_target(op, b) for a, op, b in ops if op == 0x15 and a >= hub_end]
    tail = min((t for t in calls if t > starts[-1]), default=len(d))
    bounds = starts + [tail]
    regions = [(bounds[n], bounds[n + 1]) for n in range(len(starts))]

    def region(a):
        return next((r for r in regions if r[0] <= a < r[1]), None)
    for a, op, b in ops:
        for t in _places(op, b):
            p = struct.unpack_from("<H", b, t)[0]
            if a < hub_end:
                if not (p < hub_end or (op == 0x14 and p in starts)):
                    return None
            elif a >= tail:
                if not tail <= p <= len(d):
                    return None
            elif not (region(a)[0] <= p < region(a)[1] or (op == 0x15 and p >= tail)):
                return None
    idx = {a: k for k, (a, _o, _b) in enumerate(ops)}
    if any(s not in idx for s in starts) or (tail < len(d) and tail not in idx):
        return None
    hub = list(range(idx[hub_end]))
    scenes = [list(range(idx[lo], idx[hi] if hi < len(d) else len(ops))) for lo, hi in regions]
    return hub, scenes, list(range(idx[tail] if tail < len(d) else len(ops), len(ops)))


def split_scenes(d, ops, new, name, var, first=None):
    """[(script name, bytes)]: a hub's scenes (`layout`) in parts: part 0 the hub, the scenes that fit
    and the tail; part p a table on `var` (1D) to its scenes, then them and a copy of the tail.  The
    hub's jump to a scene in part p sets `var` to its place in the table and goes to part p (32)."""
    lay = layout(d, ops)
    if lay is None:
        raise ValueError("a script past %d bytes, with nowhere to cut it" % LIMIT)
    hub, scenes, tail = lay

    def size(ks):
        return sum(len(new.get(ops[k][0], ops[k][2])) for k in ks)
    link = 8 + max(len(name(i).rsplit(".", 1)[0]) for i in range(1, 10))
    jumps = sum(1 for k in hub if ops[k][1] == 0x14)
    parts, cur = [[]], size(hub) + size(tail) + link * jumps
    for n, ks in enumerate(scenes):
        room = first if first is not None and len(parts) == 1 else LIMIT
        if cur + size(ks) > room and (parts[-1] or len(parts) > 1):
            parts.append([])
            cur = size(tail) + 3
        parts[-1].append(n)
        cur += size(ks) + (2 if len(parts) > 1 else 0)
    part_of = {n: p for p, ns in enumerate(parts) for n in ns}
    start = [ops[ks[0]][0] for ks in scenes]
    out = []
    hub_new = dict(new)
    for k in hub:
        a, op, b = ops[k]
        if op == 0x14 and _target(op, b) in start:
            n = start.index(_target(op, b))
            p = part_of[n]
            if p:
                hub_new[a] = bytes([0x1E, var, parts[p].index(n), 0x32, 0x01]) + \
                    name(p).rsplit(".", 1)[0].encode("ascii") + b"\0"
    ks = hub + [k for n in parts[0] for k in scenes[n]] + tail
    out.append((name(0), _write([ops[k] for k in ks], hub_new, len(d))))
    for p in range(1, len(parts)):
        table = bytes([0x1D, var]) + b"".join(struct.pack("<H", start[n]) for n in parts[p])
        ks = [k for n in parts[p] for k in scenes[n]] + tail
        out.append((name(p), _write([(("table", p), 0x1D, table)] + [ops[k] for k in ks], new, len(d))))
    return out


def split(d, new, name, first=None, var=None):
    """[(script name, bytes)]: the script with new operations, and when it is past its buffer, its tail
    in further scripts (`name(i)`, i from 1), each part ending in 32 naming the next; a hub of scenes
    (`layout`) with its scenes in further scripts instead (`split_scenes`, through `var`).  `first`: the
    first part's room instead (a test of the cut)."""
    ops = parse(d)
    if first is None:
        try:
            return [(name(0), _write(ops, new, len(d)))]
        except ValueError:
            pass
    if var is not None and layout(d, ops) is not None:
        return split_scenes(d, ops, new, name, var, first)
    tail = _tail(d, ops)
    cuts = set(_cuts(d, ops, tail))
    size = [len(new.get(a, b)) for a, op, b in ops]
    shared = sum(size[tail:])
    parts, start, i = [], 0, 0
    while True:
        link = 3 + len(name(i + 1).rsplit(".", 1)[0])
        room = (first if first is not None and not i else LIMIT) - shared
        total, best = 0, None
        for k in range(start, tail):
            total += size[k]
            if k + 1 in cuts and total + link <= room:
                best = k + 1
        if total <= room:
            best = None
        elif best is None or best == start:
            raise ValueError("a script past %d bytes, with nowhere to cut it" % LIMIT)
        stop = best if best is not None else tail
        ks = list(range(start, stop))
        if best is not None:
            ks.append(("link", i))
        part = [ops[k] if not isinstance(k, tuple) else
                (k, 0x32, b"\x32\x01" + name(i + 1).rsplit(".", 1)[0].encode("ascii") + b"\0") for k in ks]
        parts.append((name(i), _write(part + ops[tail:], new, len(d))))
        if best is None:
            return parts
        start, i = best, i + 1
