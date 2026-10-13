"""Elf's archives for Isaku (ISAKU_A ... ISAKU_G, read by its AI5.EXE):

* a word, the members' count n; a word, the directory's key (low byte r, high byte k);
* the directory: n entries of 20 bytes (a name, 14 bytes NUL padded; the member's offset from the
  directory's end, a dword; its size, a word), encrypted: each byte XORed with k (k rising by one a
  byte, from the high byte) and rotated right by r & 7;
* the members: a flag byte, then 'N' the data as it is, or 'P' packed: LZSS, bit by bit from the top
  of each byte, a 1 and 8 bits a literal, a 0 and 11 bits a position in a 2 KB ring (spaces, filled
  from 7EFh) and 4 bits a length less 2.

A rebuilt archive keeps its key and the members it does not change byte for byte; a changed or added
member is stored ('N'), the offsets laid out anew (a member may take 65535 bytes with its flag).
"""
import struct


def _crypt(raw, key, decrypt):
    r, k = key & 7, key >> 8
    out = bytearray(len(raw))
    for i, b in enumerate(raw):
        if decrypt:
            b = ((b << r) | (b >> (8 - r))) & 0xFF if r else b
            out[i] = b ^ k
        else:
            b ^= k
            out[i] = ((b >> r) | (b << (8 - r))) & 0xFF if r else b
        k = (k + 1) & 0xFF
    return out


def unpack(data):
    """A member's data (its flag byte first)."""
    if not data or data[0] != 0x50:
        return bytes(data[1:])
    src = data[1:]
    ring = bytearray(b" " * 0x800)
    pos, bit, total = 0x7EF, 0, len(src) * 8
    out = bytearray()

    def bits(n):
        nonlocal bit
        v = 0
        for _ in range(n):
            v = v << 1 | (src[bit >> 3] >> (7 - (bit & 7))) & 1
            bit += 1
        return v
    while bit + 9 <= total:
        if bits(1):
            c = bits(8)
            out.append(c)
            ring[pos] = c
            pos = (pos + 1) & 0x7FF
        else:
            if bit + 15 > total:
                break
            p, n = bits(11), bits(4) + 2
            for _ in range(n):
                c = ring[p]
                out.append(c)
                ring[pos] = c
                pos = (pos + 1) & 0x7FF
                p = (p + 1) & 0x7FF
    return bytes(out)


class Archive:
    def __init__(self, raw):
        self.raw = raw
        n, self.key = struct.unpack_from("<HH", raw, 0)
        d = _crypt(raw[4:4 + 20 * n], self.key, True)
        self.base = 4 + 20 * n
        self.entries = []
        for k in range(n):
            e = d[20 * k:20 * k + 20]
            off, size = struct.unpack_from("<IH", e, 14)
            self.entries.append([bytes(e[:14]), off, size])

    def names(self):
        return [e[0].split(b"\0")[0].decode("ascii", "replace") for e in self.entries]

    def _find(self, name):
        for e in self.entries:
            if e[0].split(b"\0")[0].decode("ascii", "replace").upper() == name.upper():
                return e
        raise KeyError(name)

    def name_first(self, known):
        """(the names need no key from elsewhere)"""

    def read(self, name):
        _n, off, size = self._find(name)
        return unpack(self.raw[self.base + off:self.base + off + size])

    def rebuilt(self, files):
        """The archive with files ({name: data}) stored in it anew (a name it does not hold added at
        its end)."""
        changed = {k.upper(): v for k, v in files.items()}
        dirs, body = bytearray(), bytearray()
        have = {e[0].split(b"\0")[0].decode("ascii", "replace").upper() for e in self.entries}
        entries = list(self.entries) + [[k.encode("ascii").ljust(14, b"\0"), 0, 0] for k in sorted(changed)
                                        if k not in have]
        for name, off, size in entries:
            key = name.split(b"\0")[0].decode("ascii", "replace").upper()
            if key in changed:
                member = b"N" + changed[key]
            else:
                member = self.raw[self.base + off:self.base + off + size]
            if len(member) > 0xFFFF:
                raise SystemExit("%s: %d bytes with its English, an archive's member may take 65535" % (
                    key, len(member)))
            dirs += name + struct.pack("<IH", len(body), len(member))
            body += member
        return struct.pack("<HH", len(entries), self.key) + _crypt(dirs, self.key, False) + body
