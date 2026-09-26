"""N88-DISK BASIC(86) file system on 2HD D88 images (Abunai Tengu Densetsu).

Layout (26 sectors of 256 bytes per track side): the directory is on
cylinder 35 head 0, sectors 1-12 (16-byte entries: name 6 + ext 3, attribute,
first cluster); the FAT is in sector 24 (copies in 25 and 26).  A cluster is
one track side (cluster n = cylinder n // 2, head n % 2).  A FAT entry holds
the next cluster, C0+k for a last cluster that uses k sectors, FE for
reserved and FF for free.  Files have no byte length: they are whole sectors.

The D88 container is kept as it is (track order, sector headers, gaps), so
saving rewrites only sector data.
"""
import struct

SPT, SSIZE = 26, 256
DIR_CYL = 35
FAT_SECTORS = (24, 25, 26)


class N88Disk:
    def __init__(self, path):
        self.raw = bytearray(open(path, "rb").read())
        self.sectors = {}                     # (cyl, head, sector) -> offset of data in raw
        for t in range(164):
            off = struct.unpack_from("<I", self.raw, 0x20 + 4 * t)[0]
            if not off:
                continue
            p, n = off, None
            while True:
                c, h, r, _nn, ns = struct.unpack_from("<BBBBH", self.raw, p)
                size = struct.unpack_from("<H", self.raw, p + 14)[0]
                self.sectors[(c, h, r)] = p + 16
                p += 16 + size
                n = ns
                if sum(1 for k in self.sectors if k[0] == c and k[1] == h) >= n:
                    break

    def extend(self, tracks=164):
        """Add formatted track sides up to `tracks` (the D88 track table's
        size: cylinders 77-81 on a 2HD disk).  Their FAT entries are already
        FF (free), and N88-BASIC reads a file by following its cluster numbers,
        so files written there load like any other.  Returns the number of
        track sides added."""
        added = 0
        for t in range(tracks):
            if struct.unpack_from("<I", self.raw, 0x20 + 4 * t)[0]:
                continue
            c, h = t // 2, t % 2
            struct.pack_into("<I", self.raw, 0x20 + 4 * t, len(self.raw))
            for r in range(1, SPT + 1):
                head = struct.pack("<BBBBHBBB5sH", c, h, r, 1, SPT, 0, 0, 0, b"\0" * 5, SSIZE)
                self.sectors[(c, h, r)] = len(self.raw) + 16
                self.raw += head + b"\xe5" * SSIZE
            added += 1
        struct.pack_into("<I", self.raw, 0x1C, len(self.raw))
        return added

    def tracks(self):
        return {(c, h) for c, h, _r in self.sectors}

    # ---- sectors -----------------------------------------------------------
    def sector(self, c, h, r):
        o = self.sectors[(c, h, r)]
        return bytes(self.raw[o:o + SSIZE])

    def put_sector(self, c, h, r, data):
        o = self.sectors[(c, h, r)]
        self.raw[o:o + SSIZE] = data.ljust(SSIZE, b"\0")[:SSIZE]

    # ---- FAT / directory -----------------------------------------------------
    def fat(self):
        return bytearray(self.sector(DIR_CYL, 0, FAT_SECTORS[0]))

    def put_fat(self, fat):
        for r in FAT_SECTORS:
            self.put_sector(DIR_CYL, 0, r, bytes(fat))

    def entries(self):
        out = []
        for r in range(1, 13):
            sec = self.sector(DIR_CYL, 0, r)
            for i in range(0, SSIZE, 16):
                e = sec[i:i + 16]
                if e[0] in (0, 0xFF):
                    continue
                name = e[0:6].decode("cp932", "replace").rstrip()
                ext = e[6:9].decode("cp932", "replace").rstrip()
                out.append({"name": name + ("." + ext if ext else ""), "attr": e[9], "cluster": e[10],
                            "slot": (r, i)})
        return out

    def find(self, name):
        for e in self.entries():
            if e["name"].upper() == name.upper():
                return e
        raise FileNotFoundError(name)

    def _chain(self, first):
        fat, c, out = self.fat(), first, []
        while True:
            nxt = fat[c]
            if nxt >= 0xC0:
                out.append((c, nxt - 0xC0))
                return out
            out.append((c, SPT))
            c = nxt

    # ---- files -----------------------------------------------------------------
    def read(self, name):
        data = bytearray()
        for c, n in self._chain(self.find(name)["cluster"]):
            for r in range(1, n + 1):
                data += self.sector(c // 2, c % 2, r)
        return bytes(data)

    def write(self, name, data):
        """Replace a file's contents, reusing its clusters and taking free
        ones as needed (IOError when the disk is full)."""
        e = self.find(name)
        old = [c for c, _n in self._chain(e["cluster"])]
        nsec = max(1, (len(data) + SSIZE - 1) // SSIZE)
        need = (nsec + SPT - 1) // SPT
        fat = self.fat()
        for c in old:
            fat[c] = 0xFF
        have = self.tracks()
        free = [c for c in range(min(len(fat), 0xC0)) if fat[c] == 0xFF and (c // 2, c % 2) in have]
        # keep the file's own clusters first, in order, then any free ones
        pool = old + [c for c in free if c not in old]
        if len(pool) < need and self.extend():
            self.extended = True
            have = self.tracks()
            pool += [c for c in range(min(len(fat), 0xC0)) if fat[c] == 0xFF and (c // 2, c % 2) in have
                     and c not in pool]
        if len(pool) < need:
            raise IOError("disk full: %s needs %d clusters, %d available" % (name, need, len(pool)))
        chain = pool[:need]
        for i, c in enumerate(chain):
            last = i == need - 1
            fat[c] = (0xC0 + (nsec - SPT * (need - 1))) if last else chain[i + 1]
            for r in range(1, SPT + 1):
                k = i * SPT + r - 1
                if k < nsec:
                    self.put_sector(c // 2, c % 2, r, data[k * SSIZE:(k + 1) * SSIZE])
        self.put_fat(fat)
        r, i = e["slot"]
        sec = bytearray(self.sector(DIR_CYL, 0, r))
        sec[i + 10] = chain[0]
        self.put_sector(DIR_CYL, 0, r, bytes(sec))

    def create(self, name, data, attr=0x00):
        """Add a file (6+3 name) in a free directory slot."""
        stem, _, ext = name.upper().partition(".")
        if not (1 <= len(stem) <= 6 and len(ext) <= 3):
            raise ValueError("not a 6.3 N88 name: %s" % name)
        for r in range(1, 13):
            sec = bytearray(self.sector(DIR_CYL, 0, r))
            for i in range(0, SSIZE, 16):
                if sec[i] in (0x00, 0xFF):
                    fat = self.fat()
                    have = self.tracks()
                    free = [c for c in range(min(len(fat), 0xC0)) if fat[c] == 0xFF and (c // 2, c % 2) in have]
                    if not free and self.extend():
                        self.extended = True
                        have = self.tracks()
                        free = [c for c in range(min(len(fat), 0xC0)) if fat[c] == 0xFF and (c // 2, c % 2) in have]
                    if not free:
                        raise IOError("disk full: no cluster for %s" % name)
                    c = free[0]
                    fat[c] = 0xC1
                    self.put_fat(fat)
                    ent = stem.encode("cp932").ljust(6) + ext.encode("cp932").ljust(3) + bytes([attr, c])
                    sec[i:i + 16] = ent.ljust(16, b"\xff")
                    self.put_sector(DIR_CYL, 0, r, bytes(sec))
                    self.write(name, data)
                    return
        raise IOError("directory full")

    def save(self, path):
        open(path, "wb").write(bytes(self.raw))


class N88Image:
    """A game's N88 disks as one image-like object: volumes[0] reads and writes
    files by name on whichever disk holds them; save() writes the first disk
    to the given path and the others next to it as "<stem> - <name>"."""

    def __init__(self, paths):
        import os
        self.paths = paths
        self.disks = [N88Disk(p) for p in paths]
        self.volumes = [N88Volume(self.disks)]
        self._os = os

    def save(self, dst):
        os = self._os
        stem, _ext = os.path.splitext(dst)
        self.disks[0].save(dst)
        for p, d in zip(self.paths[1:], self.disks[1:]):
            extra = "%s - %s" % (stem, os.path.basename(p))
            d.save(extra)
            print("patched %s" % extra)


class N88Volume:
    """Files spread over several N88 disks, read and written by name (the
    subset of FatVolume that Sys2Game uses)."""

    def __init__(self, disks):
        self.disks = disks                    # list of N88Disk

    def _disk(self, path):
        name = path.replace("\\", "/").split("/")[-1]
        for d in self.disks:
            try:
                d.find(name)
                return d, name
            except FileNotFoundError:
                pass
        raise FileNotFoundError(path)

    def read(self, path):
        d, name = self._disk(path)
        return d.read(name)

    def write(self, path, data):
        d, name = self._disk(path)
        d.write(name, data)

    def find(self, path):
        d, name = self._disk(path)
        return d.find(name)

    def create(self, path, data):
        """New file on the first disk; N88 names are 6+3, so a longer stem is
        cut (MTL_NOTE.TXT -> MTL_NO.TXT)."""
        name = path.replace("\\", "/").split("/")[-1]
        stem, _, ext = name.partition(".")
        self.disks[0].create(stem[:6] + ("." + ext[:3] if ext else ""), data)
