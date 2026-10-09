"""Elf's AI5 data archive (Doukyuusei 2's ELFSYS.DAT and SPECIAL.DAT).

The engine reads the first 3590h bytes as its header:

* 00-FF: a permutation of the bytes 00-FF, the hash table;
* 100h: a word n, the number of files;
* 102h: n words, each file's name hash (see name_hash);
* then n entries of six bytes: the file's offset (three bytes), a flags
  byte (bit 0: compressed) and its size (a word: the stored, so the
  compressed, size).

A file is found by its name's hash alone: the archive holds no names.
A compressed file is LZSS: a flags byte, then for each of its bits (low
first) a literal byte (0) or a reference (1): a word whose low 12 bits are
the distance back and whose high 4 bits are the length less 3, the length
in the next byte when they are all set.
"""
import struct

HEADER = 0x35A0


def name_hash(table, name):
    dl = dh = 0
    for c in name.lower().encode("ascii"):
        dl ^= c
        dh ^= c | 0x80
        dl = table[dl]
        dh = table[dh]
    return dh << 8 | dl


class Archive:
    def __init__(self, data):
        self.data = bytes(data)
        self.table = self.data[:256]
        n = struct.unpack_from("<H", self.data, 0x100)[0]
        self.hashes = list(struct.unpack_from("<%dH" % n, self.data, 0x102))
        base = 0x102 + 2 * n
        self.entries = []
        for k in range(n):
            e = self.data[base + 6 * k:base + 6 * k + 6]
            self.entries.append((e[0] | e[1] << 8 | e[2] << 16, e[3], e[4] | e[5] << 8))
        self.base = base

    def index(self, name):
        h = name_hash(self.table, name)
        return self.hashes.index(h) if h in self.hashes else None

    def raw(self, k):
        off, _fl, size = self.entries[k]
        return self.data[off:off + size]

    def read_index(self, k):
        off, fl, size = self.entries[k]
        data = self.data[off:off + size]
        return lzss(data) if fl & 1 else data

    def read(self, name):
        k = self.index(name)
        if k is None:
            raise FileNotFoundError(name)
        return self.read_index(k)

    def rebuilt(self, files):
        """The archive with the files in files ({name: bytes}) replaced, each
        compressed; the files are laid out again in their order, the
        entries pointing at them (the header keeps its place and size)."""
        new = {}
        for name, data in files.items():
            k = self.index(name)
            if k is None:
                raise FileNotFoundError(name)
            packed = compress(data)
            if lzss(packed) != data:
                raise SystemExit("%s: the compressed file does not unpack to itself" % name)
            if len(packed) > 0xFFFF:
                raise SystemExit("%s: %d bytes compressed, an archive file holds 65535" % (name, len(packed)))
            new[k] = packed
        out = bytearray(self.data[:self.entries and min(o for o, _f, _s in self.entries)])
        for k in sorted(range(len(self.entries)), key=lambda k: self.entries[k][0]):
            off, fl, size = self.entries[k]
            data = new.get(k, self.data[off:off + size])
            fl = 0xC1 if k in new else fl
            pos = len(out)
            if pos + len(data) > 0xFFFFFF:
                raise SystemExit("the archive would outgrow its 16 MB of offsets")
            out += data
            struct.pack_into("<HB", out, self.base + 6 * k, pos & 0xFFFF, pos >> 16)
            out[self.base + 6 * k + 3] = fl
            struct.pack_into("<H", out, self.base + 6 * k + 4, len(data))
        return bytes(out)


def compress(data):
    """LZSS as lzss() reads it (greedy, the nearest longest match in the
    4095 bytes before)."""
    out = bytearray()
    heads = {}
    i, n = 0, len(data)
    while i < n:
        flag_at = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if i >= n:
                break
            best_len, best_dist = 0, 0
            if i + 3 <= n:
                for j in reversed(heads.get(data[i:i + 3], ())[-48:]):
                    dist = i - j
                    if dist > 0xFFF:
                        break
                    m = 3
                    limit = min(255, n - i)
                    while m < limit and data[j + m] == data[i + m]:
                        m += 1
                    if m > best_len:
                        best_len, best_dist = m, dist
                        if m == limit:
                            break
            if best_len >= 3:
                flags |= 1 << bit
                if best_len <= 17:
                    w = (best_len - 3) << 12 | best_dist
                    out += bytes([w & 0xFF, w >> 8])
                else:
                    w = 0xF000 | best_dist
                    out += bytes([w & 0xFF, w >> 8, best_len])
                step = best_len
            else:
                out.append(data[i])
                step = 1
            for p in range(i, min(i + step, n - 2)):
                heads.setdefault(data[p:p + 3], []).append(p)
            i += step
        out[flag_at] = flags
    return bytes(out)


def lzss(src):
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        flags = src[i]
        i += 1
        for _ in range(8):
            if i >= n:
                break
            if not flags & 1:
                out.append(src[i])
                i += 1
            else:
                if i + 1 >= n:
                    # (the stored size ends inside a reference: the engine stops there too)
                    return bytes(out)
                w = src[i] | src[i + 1] << 8
                i += 2
                if w & 0xF000 == 0xF000:
                    length = src[i]
                    i += 1
                else:
                    length = (w >> 12) + 3
                dist = w & 0xFFF
                for _ in range(length):
                    out.append(out[-dist])
            flags >>= 1
    return bytes(out)
