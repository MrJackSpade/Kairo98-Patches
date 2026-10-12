"""Aaru's script engine (M Hard, Rose Blood): FL1 archives and *.AB scripts.

An FL1 archive: "FL1.0", 1Ah, two zeros, the files' count (a word), the directory's place (a dword), a
word; the files one after another from 10h; the directory at the end, a file's 12-byte name and its
size (`fl1`, `fl1_build`).  A file may be compressed (Rose Blood's scripts): two dwords, its compressed
and unpacked sizes, then LZSS (`unlz`: a flag byte, a set bit a literal, a clear one a reference, its
place the first byte and the second's top four bits, its length the low four plus 3; the 4 KB window
filled first (`window`) and written from FEEh).

A script (*.AB): ops one after another (`FMT`), each a word (its low byte FFh the end) and its operands:
words, bytes, strings (up to a NUL) and texts.  Op 00h shows a message (a text, `\\N` a new line), 01h a
choice's item (a word, the item; a word, its text's length; the text and a NUL), 02h a jump and 10h a
test (its last word where it goes when the test fails): their words are places in the script, so a
script can be laid out anew with them moved (`rebuild`).  The program draws ASCII half-width by itself
and breaks a message's line at its window's edge (60 half-width cells, 5 lines).
"""
import struct

MAGIC = b"FL1.0\x1a\x00\x00"
FMT = {0: "T", 1: "C", 2: "J", 3: "WWW", 4: "WBW", 5: "", 6: "", 7: "", 8: "", 9: "", 0xA: "", 0xB: "",
       0xC: "W", 0xD: "W", 0xE: "WW", 0xF: "WW", 0x10: "WBWJ", 0x11: "W", 0x12: "W", 0x13: "S", 0x14: "W",
       0x15: "W", 0x16: "S", 0x17: "WW", 0x18: "S", 0x19: "", 0x1B: "WB", 0x1C: "WWB", 0x1D: "WWW", 0x1E: "W",
       0x1F: "W", 0x20: "W", 0x21: "W", 0x22: "", 0x23: "", 0x24: "W", 0x25: "WWW", 0x26: "S", 0x27: "",
       0x28: "", 0x29: "", 0x2B: "B", 0x2C: "", 0x2D: "B", 0x30: "BWBW", 0x31: "B", 0x32: "", 0x33: ""}
LINE = 60                       # the message window's width in half-width cells


def fl1(raw):
    """[(name, place, size)]."""
    if raw[:8] != MAGIC:
        raise ValueError("not an FL1 archive")
    cnt, dirofs = struct.unpack_from("<HI", raw, 8)
    off, out = 16, []
    for k in range(cnt):
        e = raw[dirofs + 16 * k:dirofs + 16 * (k + 1)]
        out.append((e[:12].split(b"\0")[0].decode("ascii"), off, struct.unpack_from("<I", e, 12)[0]))
        off += out[-1][2]
    return out


def fl1_build(raw, new):
    """The archive with new {name: bytes} in place of those files."""
    files = fl1(raw)
    body, names = bytearray(), bytearray()
    cnt, dirofs = struct.unpack_from("<HI", raw, 8)
    for k, (nm, off, sz) in enumerate(files):
        data = new.get(nm, raw[off:off + sz])
        body += data
        names += raw[dirofs + 16 * k:dirofs + 16 * k + 12] + struct.pack("<I", len(data))
    head = bytearray(raw[:16])
    struct.pack_into("<I", head, 10, 16 + len(body))
    return bytes(head + body + names + raw[dirofs + 16 * cnt:])


def window():
    w = bytearray()
    for v in range(256):
        w += bytes([v]) * 13
    w += bytes(range(256)) + bytes(range(255, -1, -1)) + bytes(0x80) + b" " * 0x6E
    return w + bytes(4096 - len(w))


def compressed(data):
    """Whether a file is LZSS (its first dword its size less 8, the second a plausible size)."""
    return len(data) >= 8 and struct.unpack_from("<I", data, 0)[0] == len(data) - 8 and \
        0 < struct.unpack_from("<I", data, 4)[0] < 0x10000


def unlz(src):
    rsize = struct.unpack_from("<I", src, 4)[0]
    win = window()
    r, out, i = 0xFEE, bytearray(), 8
    while len(out) < rsize:
        flags = src[i]
        i += 1
        for _b in range(8):
            if len(out) >= rsize:
                break
            if flags & 1:
                c = src[i]
                i += 1
                out.append(c)
                win[r] = c
                r = (r + 1) & 0xFFF
            else:
                lo, hi = src[i], src[i + 1]
                i += 2
                pos = lo | ((hi & 0xF0) << 4)
                for k in range((hi & 0xF) + 3):
                    c = win[(pos + k) & 0xFFF]
                    out.append(c)
                    win[r] = c
                    r = (r + 1) & 0xFFF
            flags >>= 1
    return bytes(out)


def lz(data):
    """data as `unlz` reads it: the longest earlier match (3 to 18 bytes, within the window's last
    4078) else a literal."""
    chains, items, i, n = {}, [], 0, len(data)

    def add(p):
        if p + 3 <= n:
            chains.setdefault(data[p:p + 3], []).append(p)
    while i < n:
        best, at = 0, 0
        for j in reversed(chains.get(data[i:i + 3], [])[-48:]):
            if i - j > 4078:
                break
            k = 0
            while k < 18 and i + k < n and data[j + k] == data[i + k]:
                k += 1
            if k > best:
                best, at = k, j
                if k == 18:
                    break
        if best >= 3:
            pos = (0xFEE + at) & 0xFFF
            items.append(bytes([pos & 0xFF, ((pos >> 4) & 0xF0) | (best - 3)]))
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
        out.append(sum(1 << b for b, it in enumerate(group) if len(it) == 1))
        for it in group:
            out += it
    return struct.pack("<II", len(out), n) + bytes(out)


def walk(d):
    """(pointer places, events: ("text", start, end) an op 00h's text (end past its NUL), ("item",
    the op's place, the text's start, its end), ("op", place, op)); every pointer checked to land on
    an op (or the script's end)."""
    i, starts, ptrs, ev = 0, set(), [], []
    while i < len(d):
        starts.add(i)
        op = struct.unpack_from("<H", d, i)[0]
        if op & 0xFF == 0xFF:
            ev.append(("op", i, op))
            i += 2
            break
        if op not in FMT:
            raise ValueError("op %04x at %x" % (op, i))
        ev.append(("op", i, op))
        start = i
        i += 2
        for c in FMT[op]:
            if c in "TS":
                j = d.index(0, i) + 1
                if c == "T":
                    ev.append(("text", i, j))
                i = j
            elif c == "W":
                i += 2
            elif c == "B":
                i += 1
            elif c == "J":
                ptrs.append(i)
                i += 2
            elif c == "C":
                n = struct.unpack_from("<H", d, i + 2)[0]
                ev.append(("item", start, i + 4, i + 4 + n))
                i += 4 + n + 1
    if i > len(d):
        raise ValueError("the script runs past its end")
    starts |= {i, len(d)}
    for p in ptrs:
        if struct.unpack_from("<H", d, p)[0] not in starts:
            raise ValueError("a pointer at %x to %x, no op's start" % (p, struct.unpack_from("<H", d, p)[0]))
    return ptrs, ev


def rebuild(d, texts, items):
    """The script with texts {start: (end, bytes with the NUL)} and items {the op's place: the text's
    bytes (no NUL)} put in, its pointers moved."""
    ptrs, ev = walk(d)
    new = dict(texts)
    for e in ev:
        if e[0] == "item" and e[1] in items:
            b = items[e[1]]
            head = bytearray(d[e[1]:e[2]])
            struct.pack_into("<H", head, 4, len(b))
            new[e[1]] = (e[3] + 1, bytes(head) + b + b"\0")
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
