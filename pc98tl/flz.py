"""The *.TXB message files of Yumemizaka's and Hiiragizaka no Kyuukan's engine (YUMEMI.EXE,
HIRAGI.EXE): FLZ0 blocks of strings.

A TXB file: a table of 128 dwords at its start, each block's place (the last place the file's end, the
rest zero), then the blocks.  A block: "FLZ0", its unpacked size and its packed size (words), then LZSS
(`unpack`: a flag byte read from its low bit, a set bit a literal, a clear one a reference, its place
the first byte and the second's top four bits, its length the low four plus 3; the 4 KB window filled
with spaces and written from FEEh; `pack` writes it).  Unpacked: the strings' count (a word), their
places (a word each) and the strings, each ended by a NUL; CR (0Dh) a new line.  The scripts name a
message by its block and number, so a string may take any length (`txb`, `txb_build`).  A block
the English takes past 64 KB is written in the wide form instead (`wide_block`), which the patched
program reads (`flz_tl.widen`).
"""
import struct

MAGIC = b"FLZ0"
TABLE = 128


def unpack(src, rsize):
    win = bytearray(b" " * 4096)
    r, out, i = 0xFEE, bytearray(), 0
    while len(out) < rsize:
        flags = src[i]
        i += 1
        for b in range(8):
            if len(out) >= rsize:
                break
            if (flags >> b) & 1:
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
    return bytes(out)


def pack(data):
    """data as `unpack` reads it: the longest earlier match in the data (3 to 18 bytes, within the
    window's last 4078) else a literal."""
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
    return bytes(out)


def txb(raw):
    """[[string bytes (no NUL)] per block]."""
    offs = [o for o in struct.unpack_from("<%dI" % TABLE, raw, 0) if o]
    if offs[-1] != len(raw):
        raise ValueError("not a TXB file")
    out = []
    for o in offs[:-1]:
        if raw[o:o + 4] != MAGIC:
            raise ValueError("no FLZ0 block at %x" % o)
        rs = struct.unpack_from("<H", raw, o + 4)[0]
        b = unpack(raw[o + 8:], rs)
        n = struct.unpack_from("<H", b, 0)[0]
        places = list(struct.unpack_from("<%dH" % n, b, 2))
        out.append([b[p:b.index(0, p)] for p in places])
    return out


def block(strings):
    base = 2 + 2 * len(strings)
    if base + sum(len(s) + 1 for s in strings) > 0xFFFF:
        raise ValueError("a block past 65535 bytes")
    head = bytearray(struct.pack("<H", len(strings)))
    body = bytearray()
    for s in strings:
        head += struct.pack("<H", base + len(body))
        body += s + b"\0"
    return bytes(head + body)


def wide_block(strings):
    """A block in the wide form (`flz_tl.widen`'s loader): the strings' count, their places in
    paragraphs, then the strings, each from a paragraph's start; any length, not packed."""
    out = bytearray(struct.pack("<H", len(strings)) + bytes(2 * len(strings)))
    for j, s in enumerate(strings):
        out += bytes(-len(out) % 16)
        if len(out) // 16 > 0xFFFF:
            raise ValueError("a block past 1 MB")
        struct.pack_into("<H", out, 2 + 2 * j, len(out) // 16)
        out += s + b"\0"
    return bytes(out)


def txb_build(raw, new, wide=False):
    """The file with new {(block, number): bytes}; an unchanged block kept as it was (`wide`: every
    block written in the wide form)."""
    offs = [o for o in struct.unpack_from("<%dI" % TABLE, raw, 0) if o]
    blocks = txb(raw)
    out = bytearray(4 * TABLE)
    for k, strings in enumerate(blocks):
        struct.pack_into("<I", out, 4 * k, len(out))
        if wide:
            out += wide_block([new.get((k, j), s) for j, s in enumerate(strings)])
        elif any((k, j) in new for j in range(len(strings))):
            data = block([new.get((k, j), s) for j, s in enumerate(strings)])
            packed = pack(data)
            out += MAGIC + struct.pack("<HH", len(data), len(packed)) + packed
        else:
            out += raw[offs[k]:offs[k + 1]]
    struct.pack_into("<I", out, 4 * len(blocks), len(out))
    return bytes(out)
