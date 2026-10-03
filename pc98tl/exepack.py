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


def _commands(exe):
    """(prefix, commands, long header): the length of the image's start
    that the packed data holds as it is, then the commands for the rest,
    lowest output first: [(start, end, "fill" | "copy", byte or bytes)]."""
    hdr = struct.unpack_from("<14H", exe, 0)
    img = exe[hdr[4] * 16:]
    block = hdr[11] * 16
    long_hdr = img[block + 16:block + 18] == SIGNATURE
    dest_len = struct.unpack_from("<H", img, block + 12)[0]
    packed = img[:block]
    src = len(packed) - 1
    while src >= 0 and packed[src] == 0xFF:
        src -= 1
    dst = dest_len * 16
    cmds = []
    while True:
        cmd = packed[src]
        count = (packed[src - 1] << 8) | packed[src - 2]
        src -= 3
        if cmd & 0xFE == 0xB0:
            cmds.append((dst - count, dst, "fill", packed[src]))
            src -= 1
        else:
            cmds.append((dst - count, dst, "copy", bytes(packed[src - count + 1:src + 1])))
            src -= count
        dst -= count
        if cmd & 1:
            break
    # the image's start is the packed data's own start, left in place
    if src + 1 != dst:
        raise ValueError("EXEPACK: the packed data's start is not the image's")
    return dst, list(reversed(cmds)), long_hdr


def pack(orig, image):
    """`orig` (an EXEPACK-packed program) with its unpacked load image
    replaced by `image` (the same length): the original's commands are
    kept where the bytes are unchanged, and those covering changed bytes
    become copies (a fill split around them).  The unpacker, its
    relocation table and the memory the program asks for stay as they
    were.  The result is checked by unpacking it."""
    hdr = list(struct.unpack_from("<14H", orig, 0))
    base = hdr[4] * 16
    img = orig[base:]
    block = hdr[11] * 16
    prefix, cmds, _ = _commands(orig)
    out = []
    for start, end, kind, val in cmds:
        new = image[start:end]
        if kind == "fill" and new == bytes([val]) * (end - start) or kind == "copy" and new == val:
            out.append((start, end, kind, val))
            continue
        if kind == "copy":
            out.append((start, end, "copy", new))
            continue
        # a fill with changed bytes: fill / copy / fill
        changed = [i for i in range(end - start) if new[i] != val]
        a, b = changed[0], changed[-1] + 1
        if a:
            out.append((start, start + a, "fill", val))
        out.append((start + a, start + b, "copy", new[a:b]))
        if b < end - start:
            out.append((start + b, end, "fill", val))
    data = bytearray(image[:prefix])
    for n, (start, end, kind, val) in enumerate(out):
        count = end - start
        if count > 0xFFFF:
            raise ValueError("EXEPACK: a command over 64 KB")
        last = 1 if n == 0 else 0
        if kind == "fill":
            data += bytes([val, count & 0xFF, count >> 8, 0xB0 | last])
        else:
            data += val + bytes([count & 0xFF, count >> 8, 0xB2 | last])
    while len(data) % 16:
        data.append(0xFF)
    stub = img[block:]
    hdr[11] = len(data) // 16                       # the unpacker's segment
    load_old = hdr[2] * 512 - (512 - hdr[1] if hdr[1] else 0) - base
    load_new = len(data) + len(stub)
    hdr[5] = max(0, hdr[5] - (load_new - load_old + 15) // 16)    # the same total memory
    total = base + load_new
    hdr[1], hdr[2] = total % 512, (total + 511) // 512
    result = struct.pack("<14H", *hdr) + orig[28:base] + bytes(data) + stub
    check = unpack(result)
    if check[struct.unpack_from("<H", check, 8)[0] * 16:][:len(image)] != image:
        raise ValueError("EXEPACK: the repacked program does not unpack to the image")
    return result
