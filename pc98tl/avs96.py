"""The scripts (*.BIN) of Mink's "Game System AVS96" (AVS96.EXE: Mashou no Kao).

A script file is packed (`unpack`, `pack`): a word, the file's length; then a byte stream where a byte
A0h-BFh followed by a non-zero byte is a copy of (that byte - A0h) bytes from that far back in the
output (the distance 80h or more in two bytes, big-endian, less 7F80h), "Ax 00" the byte Ax itself, and
every other byte itself.  The first script (LOGO.BIN, named on AVS96.EXE's command line) is not packed.
The unpacked script is read in one 64 KB segment.

The script is bytecode (the interpreter's table at 0000:1948; `parse`):

* 01, text, 00: a message (Shift-JIS; "＠００" the hero's name).  The window's place and size are set by
  51 x, 52 y, 53 cells, 54 rows (each "A" and a word, 4 bytes; 55-57 the same length, unused); the
  program breaks a line at the window's width and waits for a click when the window is full.
* 3C a b rel 0F ... 3D: a test (a, b: "A" a number, "J" a word variable, "K" a byte variable, each with a
  word; rel 31-36), 3E ... 3D: an assignment ("3E 4C n name 00 ... 3D" a character's name); both end at
  the next 3D after what the program reads.
* A1 place: a jump; A2 / A3 place: a jump when the last test held / failed; B5 place: a call; B4: a
  return; B2, FF: the end.
* C3 n args C5: a system function (args: "A"/"J"/"K" and a word, 01 string 00, C4 between them); function
  4 is a menu, its items strings.
* F1 / F2 / F3 file 00: go to another script (from its start, the call stack emptied) / save / load.

`build` writes scripts with new strings: the jumps and calls moved; a script past the segment is split
(`split`): its scenes (the routines its first part calls, each once) go to further files, each with a
copy of the routines they share, reached through a variable and F1 both ways.
"""
import struct

OPND = (0x41, 0x4A, 0x4B)
JUMPS = (0xA1, 0xA2, 0xA3)
CALL, RET = 0xB5, 0xB4
LIMIT = 0xFF00          # an unpacked script's room (the segment, less a margin)
PACKED_LIMIT = 0xFFF0   # a packed file's (read in one segment)


def unpack(src):
    n = struct.unpack_from("<H", src, 0)[0] - 2
    i, out = 2, bytearray()
    while n > 0:
        a = src[i]
        i += 1
        if 0xA0 <= a < 0xC0 and src[i]:
            c = src[i]
            i += 1
            n -= 1
            if c >= 0x80:
                c = ((c << 8) | src[i]) - 0x7F80
                i += 1
                n -= 1
            for _k in range(a - 0xA0):
                out.append(out[-c])
        elif 0xA0 <= a < 0xC0:
            i += 1
            n -= 1
            out.append(a)
        else:
            out.append(a)
        n -= 1
    return bytes(out)


def pack(data):
    """`unpack`'s format: the longest earlier match (3 to 31 bytes, up to 807Fh back) else a byte."""
    out = bytearray(b"\0\0")
    chains, i, n = {}, 0, len(data)

    def add(p):
        if p + 3 <= n:
            chains.setdefault(data[p:p + 3], []).append(p)
    while i < n:
        best, at = 0, 0
        for j in reversed(chains.get(data[i:i + 3], [])[-64:]):
            if i - j > 0x807F:
                break
            k = 0
            while k < 31 and i + k < n and data[j + k] == data[i + k]:
                k += 1
            if k > best:
                best, at = k, j
                if k == 31:
                    break
        if best >= 3:
            dist = i - at
            out.append(0xA0 + best)
            if dist < 0x80:
                out.append(dist)
            else:
                out += struct.pack(">H", dist + 0x7F80)
            for p in range(i, i + best):
                add(p)
            i += best
        else:
            b = data[i]
            out += bytes([b, 0]) if 0xA0 <= b < 0xC0 else bytes([b])
            add(i)
            i += 1
    struct.pack_into("<H", out, 0, len(out))
    return bytes(out)


def _to_eq(d, i):
    while d[i] != 0x3D:
        i += 1
    return i + 1


def parse(d):
    """[(place, op, bytes)]."""
    i, out = 0, []
    while i < len(d):
        op, a = d[i], i
        if op == 0x01:
            i = d.index(0, i + 1) + 1
        elif 0x51 <= op <= 0x57:
            i += 4
        elif op == 0x3C:
            i = _to_eq(d, i + 9)
        elif op == 0x3E:
            i += 1
            if d[i] == 0x4C:
                i = _to_eq(d, d.index(0, i + 3) + 1)
            else:
                while True:
                    c = d[i]
                    if c in OPND:
                        i += 3
                    elif c == 0x37:
                        i += 2
                        if d[i] in (0x4A, 0x4B):
                            i += 3
                        i = _to_eq(d, i)
                        break
                    elif c == 0x3D:
                        i += 1
                        break
                    elif c & 0xF0 == 0x30:
                        i += 2
                    else:
                        i = _to_eq(d, i)
                        break
        elif op in JUMPS or op == CALL:
            i += 3
        elif op in (RET, 0xB2, 0xFF):
            i += 1
        elif op == 0xC3:
            i += 3
            while True:
                c = d[i]
                if c == 0xC5:
                    i += 1
                    break
                elif c == 0xC4:
                    i += 1
                elif c == 0x01:
                    i = d.index(0, i + 1) + 1
                elif c in OPND:
                    i += 3
                else:
                    raise ValueError("system function argument %02X at %X" % (c, i))
        elif op in (0xF1, 0xF2, 0xF3):
            i = d.index(0, i + 1) + 1
        else:
            raise ValueError("unknown operation %02X at %X" % (op, i))
        out.append((a, op, d[a:i]))
    return out


def target(b):
    return struct.unpack_from("<H", b, 1)[0]


def strings(ops):
    """[(index in ops, kind, place in the operation's bytes, text bytes)]: messages ("msg"), menu items
    (system function 4: "item") and characters' names ("name")."""
    out = []
    for k, (_a, op, b) in enumerate(ops):
        if op == 0x01:
            out.append((k, "msg", 1, b[1:-1]))
        elif op == 0x3E and b[1] == 0x4C:
            out.append((k, "name", 4, b[4:b.index(0, 4)]))
        elif op == 0xC3 and struct.unpack_from("<H", b, 1)[0] == 4:
            i = 3
            while b[i] != 0xC5:
                if b[i] == 0x01:
                    e = b.index(0, i + 1)
                    out.append((k, "item", i + 1, b[i + 1:e]))
                    i = e + 1
                elif b[i] == 0xC4:
                    i += 1
                else:
                    i += 3
    return out


def _with(b, new):
    """An operation's bytes with new {place: text} for its strings."""
    out, last = bytearray(), 0
    for at in sorted(new):
        e = b.index(0, at)
        out += b[last:at] + new[at]
        last = e
    return bytes(out + b[last:])


def _set(var, value):
    return b"\x3e\x41" + struct.pack("<H", value) + b"\x37\x0f\x4a" + struct.pack("<H", var) + b"\x3d"


def _test(var, value):
    return b"\x3c\x4a" + struct.pack("<H", var) + b"\x41" + struct.pack("<H", value) + b"\x31\x0f\x3d"


def _assemble(items):
    """items: (label or None, bytes, jump label or None): bytes with each jump's word set to its label's
    place."""
    at, places = 0, {}
    for lab, b, _j in items:
        if lab is not None:
            places.setdefault(lab, at)
        at += len(b)
    out = bytearray()
    for _lab, b, j in items:
        if j is not None:
            b = b[:1] + struct.pack("<H", places[j]) + b[3:]
        out += b
    return bytes(out)


def _items(ops, idx, new, tag):
    """The operations idx of ops as items labelled (tag, original place); new {index: bytes}."""
    out = []
    for k in idx:
        a, op, b = ops[k]
        b = new.get(k, b)
        out.append(((tag, a), b, (tag, target(b)) if op in JUMPS or op == CALL else None))
    return out


def layout(ops):
    """The script's parts for `split`: (hub indices, [(entry place, indices)] the scenes, shared
    indices, {call's index: scene's number}), or None when it isn't laid out as a hub calling scenes."""
    calls = {}
    for k, (a, op, b) in enumerate(ops):
        if op == CALL:
            calls.setdefault(target(b), []).append(a)
    if not calls:
        return None
    entries = sorted(calls)
    hub_end = entries[0]
    region = {}
    bounds = entries + [ops[-1][0] + len(ops[-1][2])]
    for n, e in enumerate(entries):
        region[e] = (e, bounds[n + 1])
    first = next((e for e in entries if any(c >= hub_end for c in calls[e]) or len(calls[e]) > 1), None)
    if first is None:
        return None
    scenes = [e for e in entries if e < first]          # (the shared routines: the file's tail)
    shared = [e for e in entries if e >= first]
    if not scenes:
        return None

    def inside(t, ranges):
        return any(lo <= t < hi for lo, hi in ranges)
    shared_r = [region[e] for e in shared]
    for k, (a, op, b) in enumerate(ops):
        if a < hub_end:
            continue
        own = next(region[e] for e in entries if region[e][0] <= a < region[e][1])
        if op in JUMPS and not inside(target(b), [own] + (shared_r if own in shared_r else [])):
            return None
        if op == CALL and not inside(target(b), [own] + shared_r):
            return None
    hub = [k for k, (a, _o, _b) in enumerate(ops) if a < hub_end]
    for k in hub:
        a, op, b = ops[k]
        if op in JUMPS and target(b) >= hub_end:
            return None
    sc = [(e, [k for k, (a, _o, _b) in enumerate(ops) if region[e][0] <= a < region[e][1]]) for e in scenes]
    sh = [k for k, (a, _o, _b) in enumerate(ops) if inside(a, shared_r)]
    site = {}
    for k in hub:
        if ops[k][1] == CALL and target(ops[k][2]) in scenes:
            site[k] = scenes.index(target(ops[k][2]))
    return hub, sc, sh, site


def split(name, ops, new, var, names, first=None):
    """[(file name, bytes)]: the script in parts each within LIMIT (see the docstring); names(i) gives
    part i's file name (part 0 is `name`).  `first`: the room for part 0's scenes (LIMIT)."""
    lay = layout(ops)
    if lay is None:
        raise ValueError("%s: past the segment and not laid out as scenes to split" % name)
    hub, scenes, shared, site = lay
    sizes = [sum(len(new.get(k, ops[k][2])) for k in idx) + 80 for _e, idx in scenes]
    base = sum(len(new.get(k, ops[k][2])) for k in hub + shared) + 40 * len(site) + 64
    parts, cur = [[]], base
    for n, s in enumerate(sizes):
        if cur + s > (LIMIT if first is None or len(parts) > 1 else first) and (parts[-1] or len(parts) == 1):
            parts.append([])
            cur = base - sum(len(new.get(k, ops[k][2])) for k in hub) + 64
        parts[-1].append(n)
        cur += s
        if cur > LIMIT:
            raise ValueError("%s: a scene alone is past the segment" % name)
    part_of = {n: p for p, ns in enumerate(parts) for n in ns}
    fname = [names(p) for p in range(len(parts))]
    f1 = [b"\xf1" + f.lower().encode("ascii") + b"\0" for f in fname]
    out = []
    # part 0: a dispatcher back to the hub's calls into other parts, then the hub, its scenes and shared
    items, back = [], []
    for k in sorted(site):
        if part_of[site[k]] != 0:
            back.append(k)
    for r, k in enumerate(back, 1):
        nxt = ("d", r)
        items += [(None, _test(var, r), None), (None, b"\xa3\0\0", nxt), (None, _set(var, 0), None),
                  (None, b"\xa1\0\0", ("o", ops[k + 1][0])), (nxt, b"", None)]
    hub_new = dict(new)
    for r, k in enumerate(back, 1):
        n = site[k]
        hub_new[k] = _set(var, n + 1) + f1[part_of[n]]
    items += [(("o", ops[k][0]), hub_new.get(k, ops[k][2]),
               ("o", target(ops[k][2])) if ops[k][1] in JUMPS or (ops[k][1] == CALL and k not in back) else None)
              for k in hub]
    for n in parts[0]:
        items += _items(ops, scenes[n][1], new, "o")
    items += _items(ops, shared, new, "o")
    out.append((fname[0], _assemble(items)))
    for p in range(1, len(parts)):
        items = []
        for n in parts[p]:
            r = back.index(next(k for k in back if site[k] == n)) + 1
            nxt = ("d", n)
            items += [(None, _test(var, n + 1), None), (None, b"\xa3\0\0", nxt), (None, _set(var, 0), None),
                      (None, b"\xb5\0\0", ("o", scenes[n][0])), (None, _set(var, r), None),
                      (None, f1[0], None), (nxt, b"", None)]
        items.append((None, f1[0], None))
        for n in parts[p]:
            items += _items(ops, scenes[n][1], new, "o")
        items += _items(ops, shared, new, "o")
        out.append((fname[p], _assemble(items)))
    for f, d in out:
        if len(d) > LIMIT:
            raise ValueError("%s: a part past the segment" % f)
    return out


def build(name, ops, new, var, names):
    """[(file name, unpacked bytes)]: the script with new {index: bytes} (operations written anew), the
    jumps and calls moved; split when past the segment."""
    items = _items(ops, range(len(ops)), new, "o")
    if sum(len(b) for _l, b, _j in items) <= LIMIT:
        return [(name, _assemble(items))]
    return split(name, ops, new, var, names)
