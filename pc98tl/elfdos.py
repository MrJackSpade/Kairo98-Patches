"""Elf's ELFDOS floppies (Dragon Knight III and the other AI5 games on
floppy): the boot disk's boot sector is marked "ELFDOS FORMAT" and loads
JELFDOS.SYS; every disk of a set has the same file system instead of FAT
(the data disks have no boot sector: their files start at byte 0).

The directory is the whole of track 80 (cylinder 40, head 0: 2HD, 8
sectors of 1024 bytes a track, so bytes A0000h-A1FFFh) and runs to the
first entry starting with 00.  An entry is 24 bytes: the name (13 bytes,
NUL padded), the start (one byte: the track; a word: the offset in it) and
the size (a dword, twice).  Files lie one after another; a file that runs
into the directory's track goes on after it.
"""
import struct

TRACK = 0x2000
DIR = 80 * TRACK


def _entry(raw, k):
    e = raw[DIR + 24 * k:DIR + 24 * k + 24]
    name = e[:13].split(bytes(1))[0]
    start = e[13] * TRACK + struct.unpack_from("<H", e, 14)[0]
    size, again = struct.unpack_from("<II", e, 16)
    return name, start, size, again


def is_elfdos(raw):
    """A boot disk says so in its boot sector; a data disk (no boot
    sector) is known by its directory: names, starts and sizes that fit
    the disk."""
    if raw[3:17] == b" ELFDOS FORMAT":
        return True
    if len(raw) < DIR + TRACK or not raw[DIR]:
        return False
    k = 0
    while raw[DIR + 24 * k] and k < TRACK // 24:
        name, start, size, again = _entry(raw, k)
        if not name or any(c < 0x20 for c in name) or size != again or start + size > len(raw):
            return False
        k += 1
    return True


def entries(raw):
    """{name: (start, size)} in directory order."""
    out = {}
    k = 0
    while raw[DIR + 24 * k]:
        name, start, size, _again = _entry(raw, k)
        out[name.decode("cp932")] = (start, size)
        k += 1
    return out


def read(raw, start, size):
    out = bytearray()
    p = start
    while len(out) < size:
        if DIR <= p < DIR + TRACK:
            p = DIR + TRACK
        n = size - len(out) if p >= DIR else min(size - len(out), DIR - p)
        out += raw[p:p + n]
        p += n
    return bytes(out)


def files(path):
    """[(name, bytes)] of an ELFDOS floppy image (a plain sector dump)."""
    raw = open(path, "rb").read()
    return [(n, read(raw, s, z)) for n, (s, z) in entries(raw).items()]
