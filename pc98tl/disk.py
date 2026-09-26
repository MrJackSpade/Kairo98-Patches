"""PC-98 disk images (HDI / HDM / raw FDD) with a read/write FAT12/16 filesystem.

Supports:
  * .hdi  Anex86 hard disk image (32-byte header, header_size usually 4096)
  * .hdm / .fdi-less raw 2HD floppy (1024-byte sectors, FAT12 at offset 0)

The FAT layer can list, read, replace (grow or shrink) and add files, so a
patcher can write translated data straight back into a copy of the image.
"""
import struct


class FatVolume:
    def __init__(self, buf, base):
        self.buf = buf            # bytearray of the whole image
        self.base = base          # byte offset of the FAT boot sector
        b = bytes(buf[base:base + 64])
        (self.bps, self.spc, self.reserved, self.nfats, self.root_entries,
         total16, self.media, self.fat_sectors, _spt, _heads, _hidden,
         total32) = struct.unpack_from("<HBHBHHBHHHII", b, 11)
        self.total_sectors = total16 or total32
        self.cluster_size = self.bps * self.spc
        self.fat_off = base + self.reserved * self.bps
        self.root_off = self.fat_off + self.nfats * self.fat_sectors * self.bps
        root_bytes = self.root_entries * 32
        self.data_off = self.root_off + ((root_bytes + self.bps - 1) // self.bps) * self.bps
        data_sectors = self.total_sectors - (self.data_off - base) // self.bps
        self.nclusters = data_sectors // self.spc
        self.fat12 = self.nclusters < 4085
        self.eoc = 0xFF8 if self.fat12 else 0xFFF8

    # ---- FAT table -------------------------------------------------------
    def _get(self, n, fat_index=0):
        off = self.fat_off + fat_index * self.fat_sectors * self.bps
        if self.fat12:
            v = struct.unpack_from("<H", self.buf, off + n + n // 2)[0]
            return (v >> 4) if n & 1 else (v & 0xFFF)
        return struct.unpack_from("<H", self.buf, off + n * 2)[0]

    def _set(self, n, val):
        for fi in range(self.nfats):
            off = self.fat_off + fi * self.fat_sectors * self.bps
            if self.fat12:
                p = off + n + n // 2
                v = struct.unpack_from("<H", self.buf, p)[0]
                v = (v & 0x000F) | (val << 4) if n & 1 else (v & 0xF000) | (val & 0xFFF)
                struct.pack_into("<H", self.buf, p, v)
            else:
                struct.pack_into("<H", self.buf, off + n * 2, val)

    def chain(self, c):
        out = []
        while 2 <= c < self.eoc and len(out) <= self.nclusters:
            out.append(c)
            c = self._get(c)
        return out

    def _coff(self, c):
        return self.data_off + (c - 2) * self.cluster_size

    def _free_clusters(self, n):
        got = []
        for c in range(2, self.nclusters + 2):
            if self._get(c) == 0:
                got.append(c)
                if len(got) == n:
                    return got
        raise IOError("disk full: need %d clusters" % n)

    # ---- directories -----------------------------------------------------
    def _dir_slots(self, cluster):
        """Yield (byte_offset, 32-byte entry) for a directory (0 = root)."""
        if cluster == 0:
            for i in range(self.root_entries):
                off = self.root_off + i * 32
                yield off, bytes(self.buf[off:off + 32])
        else:
            for c in self.chain(cluster):
                base = self._coff(c)
                for i in range(self.cluster_size // 32):
                    off = base + i * 32
                    yield off, bytes(self.buf[off:off + 32])

    def listdir(self, cluster=0):
        out = []
        for off, e in self._dir_slots(cluster):
            if e[0] == 0:
                break
            if e[0] == 0xE5 or e[11] == 0x0F or e[11] & 0x08:
                continue
            name = e[0:8].decode("cp932", "replace").rstrip()
            ext = e[8:11].decode("cp932", "replace").rstrip()
            if name in (".", ".."):
                continue
            full = name + ("." + ext if ext else "")
            clus, size = struct.unpack_from("<H", e, 26)[0], struct.unpack_from("<I", e, 28)[0]
            out.append({"name": full, "attr": e[11], "cluster": clus, "size": size,
                        "is_dir": bool(e[11] & 0x10), "entry_off": off})
        return out

    def walk(self, cluster=0, prefix=""):
        for ent in self.listdir(cluster):
            path = prefix + ent["name"]
            if ent["is_dir"]:
                yield path + "/", ent
                yield from self.walk(ent["cluster"], path + "/")
            else:
                yield path, ent

    def find(self, path):
        cluster, ent = 0, None
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        for i, part in enumerate(parts):
            ent = next((e for e in self.listdir(cluster) if e["name"].upper() == part.upper()), None)
            if ent is None:
                raise FileNotFoundError(path)
            cluster = ent["cluster"]
        return ent

    # ---- file data -------------------------------------------------------
    def read(self, path):
        ent = self.find(path)
        data = bytearray()
        for c in self.chain(ent["cluster"]):
            o = self._coff(c)
            data += self.buf[o:o + self.cluster_size]
        return bytes(data[:ent["size"]])

    def create(self, path, data):
        """Create (or overwrite) a file with an 8.3 name in an existing directory."""
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        try:
            self.find(path)
            return self.write(path, data)
        except FileNotFoundError:
            pass
        name, _, ext = parts[-1].upper().partition(".")
        if not (1 <= len(name) <= 8 and len(ext) <= 3):
            raise ValueError("not an 8.3 name: %s" % parts[-1])
        cluster = self.find("/".join(parts[:-1]))["cluster"] if len(parts) > 1 else 0
        slot = next((off for off, e in self._dir_slots(cluster) if e[0] in (0, 0xE5)), None)
        if slot is None:
            raise IOError("directory full")
        entry = bytearray(32)
        entry[0:11] = name.encode("cp932").ljust(8) + ext.encode("cp932").ljust(3)
        entry[11] = 0x20  # archive
        self.buf[slot:slot + 32] = entry
        self.write(path, data)

    def mkdir(self, path):
        """Create a directory (8.3 name) in an existing directory."""
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        parent = self.find("/".join(parts[:-1]))["cluster"] if len(parts) > 1 else 0
        self.create(path, b"")
        ent = self.find(path)
        c = self._free_clusters(1)[0]
        self._set(c, 0xFFF if self.fat12 else 0xFFFF)
        o = self._coff(c)
        self.buf[o:o + self.cluster_size] = bytes(self.cluster_size)
        for i, (name, clus) in enumerate(((b".", c), (b"..", parent))):
            d = bytearray(32)
            d[0:11] = name.ljust(11)
            d[11] = 0x10
            struct.pack_into("<H", d, 26, clus)
            self.buf[o + 32 * i:o + 32 * i + 32] = d
        e = ent["entry_off"]
        self.buf[e + 11] = 0x10
        struct.pack_into("<H", self.buf, e + 26, c)
        struct.pack_into("<I", self.buf, e + 28, 0)

    def delete(self, path):
        """Delete a file, or a directory with everything in it."""
        ent = self.find(path)
        if ent["is_dir"]:
            for sub in self.listdir(ent["cluster"]):
                self.delete(path.rstrip("/") + "/" + sub["name"])
        for c in (self.chain(ent["cluster"]) if ent["cluster"] else []):
            self._set(c, 0)
        self.buf[ent["entry_off"]] = 0xE5

    def write(self, path, data):
        """Replace an existing file's contents, growing/shrinking its chain."""
        ent = self.find(path)
        old = self.chain(ent["cluster"]) if ent["cluster"] else []
        need = (len(data) + self.cluster_size - 1) // self.cluster_size
        if need <= len(old):
            keep, extra = old[:need], old[need:]
            for c in extra:
                self._set(c, 0)
        else:
            keep = old + self._free_clusters(need - len(old))
        for i, c in enumerate(keep):
            self._set(c, keep[i + 1] if i + 1 < len(keep) else 0xFFF if self.fat12 else 0xFFFF)
            chunk = data[i * self.cluster_size:(i + 1) * self.cluster_size]
            o = self._coff(c)
            self.buf[o:o + self.cluster_size] = chunk.ljust(self.cluster_size, b"\0")
        e = ent["entry_off"]
        struct.pack_into("<H", self.buf, e + 26, keep[0] if keep else 0)
        struct.pack_into("<I", self.buf, e + 28, len(data))


class DiskImage:
    """Whole image; `.volumes` holds each FAT partition found."""

    def __init__(self, path_or_bytes):
        if isinstance(path_or_bytes, (bytes, bytearray)):
            raw = bytearray(path_or_bytes)
            self.path = None
        else:
            self.path = path_or_bytes
            raw = bytearray(open(path_or_bytes, "rb").read())
        self.volumes = []
        if self._looks_d88(raw):
            raw = self._d88_to_raw(raw)  # read-only view: sectors in C/H/R order
        self.raw = raw
        if self._looks_hdi(raw):
            self.kind = "hdi"
            (_r, _t, hsize, _dsize, ssize, spt, heads, _cyl) = struct.unpack_from("<8I", raw, 0)
            self.header_size = hsize
            for part_start in self._pc98_partitions(raw, hsize, ssize, spt, heads):
                self.volumes.append(FatVolume(raw, part_start))
        else:
            self.kind = "fdd"
            self.header_size = 0
            if self._is_bpb(raw, 0):
                self.volumes.append(FatVolume(raw, 0))
        if not self.volumes:  # fallback: scan for a boot sector
            for off in range(0, min(len(raw), 8 << 20), 256):
                if self._is_bpb(raw, off):
                    self.volumes.append(FatVolume(raw, off))
                    break

    @staticmethod
    def _looks_d88(raw):
        if len(raw) < 0x2B0:
            return False
        size = struct.unpack_from("<I", raw, 0x1C)[0]
        first = struct.unpack_from("<I", raw, 0x20)[0]
        return size == len(raw) and first in (0x2A0, 0x2B0) or (first == 0x2B0 and size <= len(raw))

    @staticmethod
    def _d88_to_raw(raw):
        """Flatten a D88 image to raw sectors (tracks in order, sectors by R)."""
        out = bytearray()
        for t in range(164):
            off = struct.unpack_from("<I", raw, 0x20 + t * 4)[0]
            if not off or off >= len(raw):
                continue
            secs = []
            nsec = struct.unpack_from("<H", raw, off + 4)[0] or 1
            p = off
            for _ in range(nsec):
                if p + 16 > len(raw):
                    break
                r = raw[p + 2]
                size = struct.unpack_from("<H", raw, p + 0x0E)[0]
                secs.append((r, bytes(raw[p + 16:p + 16 + size])))
                p += 16 + size
            for _, data in sorted(secs):
                out += data
        return out

    @staticmethod
    def _looks_hdi(raw):
        if len(raw) < 32:
            return False
        _r, _t, hsize, dsize, ssize, spt, heads, cyl = struct.unpack_from("<8I", raw, 0)
        return hsize in (512, 1024, 2048, 4096) and ssize in (256, 512, 1024) and \
            heads and spt and hsize + dsize <= len(raw) + ssize

    @staticmethod
    def _is_bpb(raw, off):
        b = raw[off:off + 32]
        if len(b) < 32 or b[0] not in (0xEB, 0xE9):
            return False
        bps = struct.unpack_from("<H", b, 11)[0]
        return bps in (256, 512, 1024, 2048) and b[13] in (1, 2, 4, 8, 16, 32, 64) and b[16] in (1, 2)

    @staticmethod
    def _pc98_partitions(raw, hsize, ssize, spt, heads):
        pt = hsize + ssize  # partition table lives in sector 1
        starts = []
        for i in range(16):
            e = raw[pt + i * 32: pt + (i + 1) * 32]
            if len(e) < 32 or e[0] == 0 and e[1] == 0:
                continue
            s, h, c = e[8], e[9], struct.unpack_from("<H", e, 10)[0]
            off = hsize + ((c * heads + h) * spt + s) * ssize
            if DiskImage._is_bpb(raw, off):
                starts.append(off)
        return starts

    def save(self, path):
        open(path, "wb").write(self.raw)
