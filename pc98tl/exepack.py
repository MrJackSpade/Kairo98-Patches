"""Microsoft EXEPACK: unpack a packed MZ executable into a plain one.

A packed EXE's entry point is the unpacker, whose segment starts with a
header (real IP, real CS, unused word, unpacker size, real SP, real SS,
unpacked length in paragraphs, [skip length,] "RB").  The packed image is
everything before that segment; it is decoded backwards from its end
(trailing FF padding skipped) by commands: B0 = fill (count, byte),
B2 = copy (count bytes); bit 0 set marks the last command.  The relocations
follow the "Packed file is corrupt" message: for each of the 16 segment
bases 0000, 1000, ... F000 a count and that many offsets.
"""
import struct

SIGNATURE = b"RB"
ERROR_MSG = b"Packed file is corrupt"


def is_packed(exe):
    hdr = struct.unpack_from("<14H", exe, 0)
    at = hdr[4] * 16 + hdr[11] * 16
    return exe[at + 14:at + 16] == SIGNATURE or exe[at + 16:at + 18] == SIGNATURE


def unpack(exe):
    hdr = struct.unpack_from("<14H", exe, 0)
    base = hdr[4] * 16
    img = exe[base:]
    block = hdr[11] * 16
    if img[block + 14:block + 16] == SIGNATURE:
        ip, cs, _, size, sp, ss, dest_len = struct.unpack_from("<7H", img, block)
    elif img[block + 16:block + 18] == SIGNATURE:
        ip, cs, _, size, sp, ss, dest_len, _skip = struct.unpack_from("<8H", img, block)
    else:
        raise ValueError("not an EXEPACK file")
    packed = img[:block]
    out = bytearray(max(dest_len * 16, len(packed)))
    out[:len(packed)] = packed
    src = len(packed) - 1
    while src >= 0 and packed[src] == 0xFF:
        src -= 1
    dst = len(out) - 1
    while True:
        cmd = out[src]
        count = (out[src - 1] << 8) | out[src - 2]
        src -= 3
        op = cmd & 0xFE
        if op == 0xB0:
            val = out[src]
            src -= 1
            for _ in range(count):
                out[dst] = val
                dst -= 1
        elif op == 0xB2:
            for _ in range(count):
                out[dst] = out[src]
                dst -= 1
                src -= 1
        else:
            raise ValueError("EXEPACK: bad command %02x" % cmd)
        if cmd & 1:
            break
    image = bytes(out[:dest_len * 16])
    # relocations
    at = img.find(ERROR_MSG, block)
    if at < 0:
        raise ValueError("EXEPACK: relocation table not found")
    p = at + len(ERROR_MSG)
    relocs = []
    for seg in range(16):
        n = struct.unpack_from("<H", img, p)[0]
        p += 2
        for _ in range(n):
            relocs.append((struct.unpack_from("<H", img, p)[0], seg * 0x1000))
            p += 2
    # build a plain MZ file
    hdr_paras = (28 + 4 * len(relocs) + 15) // 16
    total = hdr_paras * 16 + len(image)
    # the same total memory as the packed program asked for
    load = (hdr[2] * 512 - (512 - hdr[1] if hdr[1] else 0)) - base
    need = load + hdr[5] * 16
    minalloc = max(0, (need - len(image) + 15) // 16)
    head = struct.pack("<14H", 0x5A4D, total % 512, (total + 511) // 512, len(relocs), hdr_paras,
                       minalloc, hdr[6], ss, sp, 0, ip, cs, 28, 0)
    head += b"".join(struct.pack("<HH", o, s) for o, s in relocs)
    head = head.ljust(hdr_paras * 16, b"\0")
    return head + image
