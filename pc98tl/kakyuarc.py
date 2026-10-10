"""Elf's archives for Kakyuusei (KAKYUSEI.ARC, and the special disk's KSP.ARC; read by its AI5.EXE and
KSP5.EXE):

* 16 bytes: "KAKYUSEI.ARC", 1Ah, "elf";
* a directory of 2300 entries of 20 bytes (a name, 14 bytes NUL padded; the member's offset in the
  archive, a dword; its size, a word), every byte encrypted: rotated left by one, then XORed with
  55h (the engine reads them so); the slots past the last entry are zeros;
* the members: a script (.MES) packed (the engine unpacks a member by its extension), any other stored
  as it is.  Packed: LZSS, bit by bit from the top of each byte, a 1 and 8 bits a literal, a 0 and 12
  bits a position in a 4 KB ring (written from 1) and 4 bits a length less 2; position 0 ends it.

A rebuilt archive keeps the members it does not change byte for byte (an archive with none changed is
itself); a changed or added script is packed again (pack), any other added member stored, the offsets
laid out anew.
"""
import struct

HEAD = 16
SLOTS = 2300


def _dec(b):
    return bytes((((x << 1) | (x >> 7)) & 0xFF) ^ 0x55 for x in b)


def _enc(b):
    return bytes((((x ^ 0x55) >> 1) | ((x ^ 0x55) << 7)) & 0xFF for x in b)


def unpack(src):
    ring = bytearray(0x1000)
    pos, bit, total, out = 1, 0, len(src) * 8, bytearray()

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
            pos = (pos + 1) & 0xFFF
            continue
        if bit + 12 > total:
            break
        p = bits(12)
        if not p:
            break
        for _ in range(bits(4) + 2):
            c = ring[p]
            out.append(c)
            ring[pos] = c
            pos = (pos + 1) & 0xFFF
            p = (p + 1) & 0xFFF
    return bytes(out)


def pack(data):
    """LZSS of data (greedy: the longest match of 3 to 17 bytes in the last 4 KB written, the ring's
    position 0 never used), and the end (position 0)."""
    codes = []
    heads = {}
    k = 0
    while k < len(data):
        best, at = 0, 0
        for j in reversed(heads.get(data[k:k + 3], [])[-64:]):
            if k - j >= 0xFFF - 17:
                break
            if (j + 1) & 0xFFF == 0:
                continue
            n = 0
            while n < 17 and k + n < len(data) and data[j + n] == data[k + n]:
                n += 1
            if n > best:
                best, at = n, j
                if n == 17:
                    break
        if best >= 3:
            # (the ring position of byte j: written from 1)
            codes.append((17, ((at + 1) & 0xFFF) << 4 | (best - 2)))
            step = best
        else:
            codes.append((9, 0x100 | data[k]))
            step = 1
        for j in range(k, k + step):
            heads.setdefault(data[j:j + 3], []).append(j)
        k += step
    codes.append((13, 0))
    out, acc, n = bytearray(), 0, 0
    for width, v in codes:
        acc = (acc << width) | v
        n += width
        while n >= 8:
            out.append((acc >> (n - 8)) & 0xFF)
            n -= 8
        acc &= (1 << n) - 1
    if n:
        out.append((acc << (8 - n)) & 0xFF)
    return bytes(out)


class Archive:
    def __init__(self, raw):
        self.raw = raw
        self.entries = []
        for k in range(SLOTS):
            e = _dec(raw[HEAD + 20 * k:HEAD + 20 * k + 20])
            name = e[:14].split(b"\0")[0]
            if not name or name == b"U" * len(name) or not all(0x21 <= c < 0x7F for c in name):
                break
            off, size = struct.unpack_from("<IH", e, 14)
            self.entries.append([e[:14], off, size])
        self.base = HEAD + 20 * SLOTS

    def names(self):
        return [e[0].split(b"\0")[0].decode("ascii") for e in self.entries]

    def _find(self, name):
        for e in self.entries:
            if e[0].split(b"\0")[0].decode("ascii").upper() == name.upper():
                return e
        raise KeyError(name)

    def name_first(self, known):
        """(the names need no key from elsewhere)"""

    def read(self, name):
        _n, off, size = self._find(name)
        data = self.raw[off:off + size]
        return unpack(data) if name.upper().endswith(".MES") else bytes(data)

    def rebuilt(self, files):
        """The archive with files ({name: data}) stored in it anew (a name it does not hold added)."""
        changed = {k.upper(): v for k, v in files.items()}
        if not changed:
            return self.raw
        have = {e[0].split(b"\0")[0].decode("ascii").upper() for e in self.entries}
        entries = list(self.entries) + [[k.encode("ascii").ljust(14, b"\0"), 0, 0] for k in sorted(changed)
                                        if k not in have]
        if len(entries) > SLOTS:
            raise SystemExit("the archive's directory holds %d entries, not %d" % (SLOTS, len(entries)))
        dirs, body = bytearray(), bytearray()
        at = self.base
        for name, off, size in entries:
            key = name.split(b"\0")[0].decode("ascii").upper()
            if key in changed:
                member = pack(changed[key]) if key.endswith(".MES") else changed[key]
            else:
                member = self.raw[off:off + size]
            if len(member) > 0xFFFF:
                raise SystemExit("%s: %d bytes as stored, an archive's member may take 65535" % (key, len(member)))
            dirs += name + struct.pack("<IH", at + len(body), len(member))
            body += member
        dirs += bytes(20 * (SLOTS - len(entries)))
        enc = bytearray(_enc(dirs))
        # (the empty slots stay zeros, as the engine's own are)
        enc[20 * len(entries):] = bytes(20 * (SLOTS - len(entries)))
        return self.raw[:HEAD] + bytes(enc) + bytes(body)
