"""Birdy Soft's ADOS disks (Cal, Cal II: "ADOS ver1.5", "ver1.6" in the boot sector): files by number.

A 2HD image of 1024-byte sectors (77 cylinders, 2 heads, 8 sectors: 1232 sectors).  The directory is
sectors 14-15 (byte 3800h): 256 entries of 8 bytes, entry n at 3800h + 8n; entry 0 and 1 hold the
disk's label ("[A] CAL.....") and four more bytes.  An entry: the size (a word and a third byte), the
first sector (a word), the sector count (a byte), two zero bytes; "::" and zeros mark a free entry.
A file's sectors are contiguous; the kernel loads whole sectors.  (The FAT at sector 1 marks every
cluster bad, keeping MS-DOS off the disk; ADOS does not use it.)
"""
import struct

SECTOR = 1024
DIR = 0x3800
ENTRIES = 256
RESERVED = 16                     # sectors 0-15: boot, FAT, directory
FREE = b"::" + bytes(6)


class AdosDisk:
    def __init__(self, path):
        self.path = path
        self.raw = bytearray(open(path, "rb").read())
        if b"ADOS" not in bytes(self.raw[:16]):
            raise ValueError("%s: not an ADOS disk" % path)
        self.sectors = len(self.raw) // SECTOR

    def label(self):
        return bytes(self.raw[DIR:DIR + 12]).decode("ascii", "replace")

    def entry(self, n):
        """(size, first sector, count) of file n, or None."""
        if n < 2:
            return None
        e = bytes(self.raw[DIR + 8 * n:DIR + 8 * n + 8])
        if e[:2] == b"::" or not any(e):
            return None
        return struct.unpack_from("<H", e, 0)[0] | e[2] << 16, struct.unpack_from("<H", e, 3)[0], e[5]

    def files(self):
        return [n for n in range(ENTRIES) if self.entry(n)]

    def read(self, n):
        size, start, _count = self.entry(n)
        return bytes(self.raw[start * SECTOR:start * SECTOR + size])

    def _used(self, skip=None):
        used = set(range(RESERVED))
        for n in self.files():
            if n != skip:
                _s, start, count = self.entry(n)
                used |= set(range(start, start + count))
        return used

    def free(self):
        return self.sectors - len(self._used())

    def write(self, n, data):
        """File n's contents: in its own sectors when they hold it, else in the first free run long
        enough (IOError when there is none)."""
        need = max(1, -(-len(data) // SECTOR))
        old = self.entry(n)
        if old and old[2] >= need:
            start = old[1]
        else:
            used = self._used(skip=n)
            start, run = None, 0
            for s in range(RESERVED, self.sectors):
                run = 0 if s in used else run + 1
                if run == need:
                    start = s - need + 1
                    break
            if start is None:
                raise IOError("%s: no %d free sectors in a row for file %d (%d free in all)" % (
                    self.path, need, n, self.sectors - len(used)))
            if old:
                self.raw[old[1] * SECTOR:(old[1] + old[2]) * SECTOR] = bytes(old[2] * SECTOR)
        self.raw[start * SECTOR:(start + need) * SECTOR] = data + bytes(need * SECTOR - len(data))
        e = struct.pack("<HBHB", len(data) & 0xFFFF, len(data) >> 16, start, need) + b"\0\0"
        self.raw[DIR + 8 * n:DIR + 8 * n + 8] = e

    def save(self, path):
        open(path, "wb").write(bytes(self.raw))
