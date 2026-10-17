"""Melody's PCK archives and MAXPACK compression (Kurayami; served by its disk driver EXDD).

A PCK archive: 4000h bytes of header and directory, then the files.  The header and directory are
stored with every 16-bit big-endian word rotated right one bit (`rotate`/`unrotate`): "PCK Version
1.00" and 16 bytes, then 511 entries of 32 bytes: the name (16 bytes, NUL-padded), the place and size
(dwords), 8 bytes kept as they are; an unused entry is named with spaces.

A file may be MAXPACK-compressed: "MAXPACK\\0", the unpacked size, the packed size (words), 0, the
unpacked size and 0, then LZSS: a flag byte per 8 items (low bit first, 1 a literal byte), a copy two
bytes (12-bit place in a 4096-byte window, 4-bit count less 3); the window starts at 0FEEh and is
filled first with 13 copies of each byte value, the values up and down, 128 zeros and spaces
(`window`).  EXDD reads the packed bytes into a buffer the size of the unpacked file: a packed file
may not be larger than its unpacked size.
"""
import struct

HEAD = 0x4000
ENTRY = 32
N, F, T = 4096, 18, 2


def unrotate(b):
    o = bytearray(b)
    for i in range(0, len(b) - 1, 2):
        w = b[i] << 8 | b[i + 1]
        w = ((w << 1) | (w >> 15)) & 0xFFFF
        o[i], o[i + 1] = w >> 8, w & 0xFF
    return bytes(o)


def rotate(b):
    o = bytearray(b)
    for i in range(0, len(b) - 1, 2):
        w = b[i] << 8 | b[i + 1]
        w = ((w >> 1) | (w << 15)) & 0xFFFF
        o[i], o[i + 1] = w >> 8, w & 0xFF
    return bytes(o)


def entries(arc):
    """[(index, name, place, size)] of the archive's files (unused entries left out)."""
    d = unrotate(arc[:HEAD])
    if not d.startswith(b"PCK Version"):
        raise ValueError("not a PCK archive")
    out = []
    for k in range(1, HEAD // ENTRY):
        e = d[k * ENTRY:(k + 1) * ENTRY]
        name = e[:16].split(b"\0", 1)[0].decode("ascii", "replace").strip()
        place, size = struct.unpack_from("<II", e, 16)
        if name and size:
            out.append((k, name, place, size))
    return out


def files(arc):
    """{name: stored bytes}."""
    return {name: arc[place:place + size] for _k, name, place, size in entries(arc)}


def rebuild(arc, new):
    """The archive with some files' stored bytes replaced ({name: bytes}); the files laid out anew."""
    d = bytearray(unrotate(arc[:HEAD]))
    out = bytearray(HEAD)
    for k, name, place, size in entries(arc):
        blob = new.get(name, arc[place:place + size])
        struct.pack_into("<II", d, k * ENTRY + 16, len(out), len(blob))
        out += blob
    out[:HEAD] = rotate(bytes(d))
    return bytes(out)


def window():
    w = bytearray()
    for i in range(256):
        w += bytes([i]) * 13
    w += bytes(range(256)) + bytes(range(255, -1, -1)) + bytes(128)
    return w + b" " * (N - len(w))


def is_packed(blob):
    return blob[:8] == b"MAXPACK\0"


def unpack(blob):
    n = struct.unpack_from("<H", blob, 8)[0]
    src = blob[18:]
    win, r, out, p, flags = window(), N - F, bytearray(), 0, 0
    while len(out) < n and p < len(src):
        flags >>= 1
        if not flags & 0x100:
            flags = src[p] | 0xFF00
            p += 1
        if flags & 1:
            c = src[p]
            p += 1
            out.append(c)
            win[r] = c
            r = (r + 1) % N
        else:
            i, j = src[p], src[p + 1]
            p += 2
            i |= (j & 0xF0) << 4
            for k in range((j & 0x0F) + T + 1):
                c = win[(i + k) % N]
                out.append(c)
                win[r] = c
                r = (r + 1) % N
    return bytes(out[:n])


def pack(raw):
    """MAXPACK (greedy LZSS; copies only of bytes already written, so the window's first contents
    are never read)."""
    if len(raw) > 0xFFFF:
        raise ValueError("a file over 64K cannot be packed")
    out, i, n, heads = bytearray(), 0, len(raw), {}

    def add(p):
        if p + 3 <= n:
            heads.setdefault(raw[p:p + 3], []).append(p)

    while i < n:
        at = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if i >= n:
                break
            best, pos = 0, 0
            if i + 3 <= n:
                for p in reversed(heads.get(raw[i:i + 3], [])[-96:]):
                    if i - p > N - F:
                        break
                    ln = 3
                    while ln < F and i + ln < n and raw[p + ln] == raw[i + ln]:
                        ln += 1
                    if ln > best:
                        best, pos = ln, p
                        if ln == F:
                            break
            if best >= 3:
                wp = (pos + N - F) % N
                out += bytes([wp & 0xFF, ((wp >> 4) & 0xF0) | (best - 3)])
                for k in range(best):
                    add(i + k)
                i += best
            else:
                flags |= 1 << bit
                out.append(raw[i])
                add(i)
                i += 1
        out[at] = flags
    if len(out) > n:
        raise ValueError("a packed file would be larger than itself")
    return b"MAXPACK\0" + struct.pack("<HHHHH", n, len(out), 0, n, 0) + bytes(out)
