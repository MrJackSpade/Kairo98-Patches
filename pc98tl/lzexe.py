"""LZEXE 0.91 programs (the "LZ91" mark may be missing): unpacked to their image and relocations,
and written back as a plain MZ program.

An LZEXE program's entry (CS:IP 0 in its own header) is the unpacker: the header at its CS:0
(the real IP, CS, SP, SS, the packed image's paragraphs, the paragraphs it grows by, the unpacker's
length), then the unpacker, then the relocations.  The packed image starts at the load module's
start: 16-bit flag words (LSB first), a set bit a literal byte; else a short copy (two more flag bits
the count less 2, a byte the distance from FF00h) or a long one (a word: the distance in its low 13
bits, ORed with E000h, and the count less 2 in its top three, or 0 and a byte: 0 the end, 1 a
segment step, else the count less 1).  The unpacker reloads the flag word as soon as it has used
its 16 bits.  Relocations: bytes, each nonzero one moving the place on by that much and fixing
the word there; 0 and a word: 0 a step of FFF0h bytes, 1 the end, else a move by it and a fix.
"""
import struct

RELOC_AT = 0x158    # the relocations' place after the unpacker's CS:0 (LZEXE 0.91)


def _unpack(img):
    out = bytearray()
    i = 2
    bits = struct.unpack_from("<H", img, 0)[0]
    n = 16

    def bit():
        nonlocal bits, n, i
        b = bits & 1
        bits >>= 1
        n -= 1
        if n == 0:
            bits = struct.unpack_from("<H", img, i)[0]
            i += 2
            n = 16
        return b
    while True:
        if bit():
            out.append(img[i])
            i += 1
            continue
        if bit():
            ax = struct.unpack_from("<H", img, i)[0]
            i += 2
            off = ((ax & 0xFF) | (((ax >> 8) >> 3 | 0xE0) << 8)) - 0x10000
            count = (ax >> 8) & 7
            if count == 0:
                c = img[i]
                i += 1
                if c == 0:
                    return bytes(out)
                if c == 1:
                    continue
                count = c + 1
            else:
                count += 2
        else:
            count = ((bit() << 1) | bit()) + 2
            off = img[i] - 0x100
            i += 1
        for _ in range(count):
            out.append(out[off])


def unpack(exe):
    """{image, relocs [linear offsets in the image], ip, cs, sp, ss, memory (the bytes the program
    needs from its image's start)} of an LZEXE 0.91 program."""
    h = struct.unpack_from("<13H", exe, 0)
    if exe[:2] != b"MZ":
        raise ValueError("not an MZ program")
    hdr = h[4] * 16
    size = h[2] * 512 - ((512 - h[1]) if h[1] else 0) - hdr
    img = exe[hdr:hdr + size]
    cs0 = h[11] * 16
    ip, cs, sp, ss = struct.unpack_from("<4H", img, cs0)
    if img[cs0 + 0x0E:cs0 + 0x14] != bytes.fromhex("060e1f8b0e0c"):
        raise ValueError("not an LZEXE 0.91 unpacker")
    image = _unpack(img)
    relocs = []
    j = cs0 + RELOC_AT
    seg = pos = 0
    while True:
        b = img[j]
        j += 1
        if b:
            pos += b
        else:
            w = struct.unpack_from("<H", img, j)[0]
            j += 2
            if w == 0:
                seg += 0xFFF
                continue
            if w == 1:
                break
            pos += w
        relocs.append(seg * 16 + pos)
    return {"image": image, "relocs": relocs, "ip": ip, "cs": cs, "sp": sp, "ss": ss,
            "memory": size + h[5] * 16, "most": size + h[6] * 16}


def build(p, image=None, keep_most=False):
    """A plain MZ program from unpack()'s result (its image replaced by image); keep_most: asking
    for no more memory than the packed program did (else for all there is)."""
    image = p["image"] if image is None else image
    relocs = p["relocs"]
    hdr_len = (0x1C + 4 * len(relocs) + 15) // 16 * 16
    total = hdr_len + len(image)
    pages, last = (total + 511) // 512, total % 512
    minalloc = max(0, (p["memory"] - len(image) + 15) // 16)
    most = max(minalloc, min(0xFFFF, (p["most"] - len(image) + 15) // 16)) if keep_most else 0xFFFF
    head = struct.pack("<14H", 0x5A4D, last, pages, len(relocs), hdr_len // 16, minalloc, most,
                       p["ss"], p["sp"], 0, p["ip"], p["cs"], 0x1C, 0)
    out = bytearray(head[:0x1C])
    for r in relocs:
        out += struct.pack("<HH", r & 0xF, r >> 4)
    out += bytes(hdr_len - len(out))
    return bytes(out + image)


def fix(image, relocs, load_seg):
    """The image as loaded at load_seg (for comparing two loads)."""
    img = bytearray(image)
    for r in relocs:
        v = struct.unpack_from("<H", img, r)[0]
        struct.pack_into("<H", img, r, (v + load_seg) & 0xFFFF)
    return bytes(img)
