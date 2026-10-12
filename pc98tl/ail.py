"""Ail's ADV.EXE (Kyouhaku): the scenarios in SALL.SNL.

SALL.SNL: a word, the count, then a word per scenario, its size, and the scenarios one after another
(an empty one has size 0).  A scenario is a word, its mode (bit 0: compressed), and its bytes: LZSS
(`unpack`: ADV.EXE's own routine, Okumura's with the flag bits read the other way round: a clear bit
a literal, a set bit a reference, its position the first byte and the second's top four bits, its
length the low four bits plus 3; the 4 KB window starts as spaces and is written from FEEh).

A scenario: five words, the sizes of two tables, of the label table, of the code and of the text,
from 0Ah: the tables, the labels (offsets in the code), the code, the text.  The code is ops one
after another (`walk`): op 00h a command (a sub-op and its arguments), the others the variables, the
jumps (targets in the code, big-endian), a switch, the labels' calls and jumps, the ends.  An
argument is FFh and a byte, FEh and a big-endian word, or a variable (a byte up to 1Ah and a
big-endian word).  A sub-op's arguments are counted off the program's own routine (`Build`, the
table of sub-ops' routines read off ADV.EXE); the sub-ops that show a text have a big-endian word
after their arguments, the text's offset from the text's start.  A text is Shift-JIS up to a NUL,
padded to an even length; the code reads each text by its offset, so the text section can be laid
out anew with the code as it is.
"""
import re
import struct

# the main ops' lengths (ops 00h, 05h, 09h, 0Ah, 0Ch, 0Dh, 12h by their rule in `walk`)
MAIN = {0x01: 7, 0x02: 9, 0x03: 10, 0x04: 6, 0x06: 4, 0x07: 4, 0x08: 3, 0x0B: 1, 0x0E: 1, 0x0F: 1, 0x10: 1,
        0x11: 1, 0x13: 1, 0x14: 7}
# the sub-op dispatch: cmp ax, the last sub-op / ja / shl ax, 1 / xchg bx, ax / jmp cs:[bx + table]
DISPATCH = re.compile(rb"\x3d(..)\x77.\xd1\xe0\x93\x2e\xff\xa7(..)", re.S)
# the argument reader: a byte; FFh, FEh or a variable up to 1Ah
ARG_SIG = re.compile(rb"\x3c\xff\x75.", re.S)


def unpack(src, i, end):
    """ADV.EXE's LZSS (see the module's notes): the bytes src[i:end] unpacked."""
    win = bytearray(b" " * 4096)
    r = 0xFEE
    out = bytearray()
    flags = 0
    while i < end:
        flags >>= 1
        if not flags & 0x100:
            flags = src[i] | 0xFF00
            i += 1
            if i >= end:
                break
        if not flags & 1:
            c = src[i]
            i += 1
            out.append(c)
            win[r] = c
            r = (r + 1) & 0xFFF
        else:
            if i + 1 >= end:
                break
            lo, hi = src[i], src[i + 1]
            i += 2
            pos = lo | ((hi & 0xF0) << 4)
            for k in range((hi & 0xF) + 3):
                c = win[(pos + k) & 0xFFF]
                out.append(c)
                win[r] = c
                r = (r + 1) & 0xFFF
    return bytes(out)


def pack(data):
    """data as `unpack` reads it: the longest earlier match (3 to 18 bytes, within the window's last
    4095) else a literal."""
    chains = {}
    i, n = 0, len(data)
    items = []

    def add(p):
        if p + 3 <= n:
            chains.setdefault(data[p:p + 3], []).append(p)
    while i < n:
        best, at = 0, 0
        for j in reversed(chains.get(data[i:i + 3], [])[-48:]):
            if i - j > 4095 - 18:
                break
            k = 0
            while k < 18 and i + k < n and data[j + k] == data[i + k]:
                k += 1
            if k > best:
                best, at = k, j
                if k == 18:
                    break
        if best >= 3:
            pos = (0xFEE + at) & 0xFFF
            items.append(bytes([pos & 0xFF, ((pos >> 4) & 0xF0) | (best - 3)]))
            for p in range(i, i + best):
                add(p)
            i += best
        else:
            items.append(data[i:i + 1])
            add(i)
            i += 1
    out = bytearray()
    for k in range(0, len(items), 8):
        group = items[k:k + 8]
        out.append(sum(1 << b for b, it in enumerate(group) if len(it) == 2))
        for it in group:
            out += it
    return bytes(out)


def read_snl(raw):
    """[(mode, scenario bytes)]."""
    n = struct.unpack_from("<H", raw, 0)[0]
    sizes = struct.unpack_from("<%dH" % n, raw, 2)
    pos, out = 2 + 2 * n, []
    for size in sizes:
        blk = raw[pos:pos + size]
        pos += size
        if not blk:
            out.append((None, b""))
            continue
        mode = struct.unpack_from("<H", blk, 0)[0]
        out.append((mode, unpack(blk, 2, len(blk)) if mode & 1 else blk[2:]))
    return out


def write_snl(scenarios, raws):
    """SALL.SNL with the scenarios: raws {index: the original block} for the ones that stay."""
    blocks = []
    for k, (mode, d) in enumerate(scenarios):
        if k in raws:
            blocks.append(raws[k])
        elif mode is None:
            blocks.append(b"")
        else:
            blocks.append(struct.pack("<H", mode | 1) + pack(d))
    return struct.pack("<%dH" % (len(blocks) + 1), len(blocks), *[len(b) for b in blocks]) + b"".join(blocks)


def blocks(raw):
    n = struct.unpack_from("<H", raw, 0)[0]
    sizes = struct.unpack_from("<%dH" % n, raw, 2)
    pos, out = 2 + 2 * n, []
    for size in sizes:
        out.append(raw[pos:pos + size])
        pos += size
    return out


class Build:
    """ADV.EXE's sub-ops: {sub-op: (arguments, whether a text's offset follows)}, read off the program."""

    def __init__(self, image):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_16
        md = Cs(CS_ARCH_X86, CS_MODE_16)
        found = []
        for m in DISPATCH.finditer(image):
            last, t = struct.unpack("<HH", m.group(1) + m.group(2))
            tab = m.end() + (1 if image[m.end()] == 0x90 else 0)
            found.append((last, tab, tab - t))
        subs = [f for f in found if 0x2A <= f[0] <= 0x40]
        if len(subs) != 1:
            raise ValueError("ADV.EXE: the sub-ops' table found %d times" % len(subs))
        last, tab, base = subs[0]
        args = [m.start() for m in ARG_SIG.finditer(image)
                if b"\x80\x7e" in image[m.start() - 40:m.start() + 80]
                and b"\x1a" in image[m.start():m.start() + 120]]
        if len(args) != 1:
            raise ValueError("ADV.EXE: the arguments' reader found %d times" % len(args))
        argfn = image.rfind(b"\x55\x8b\xec", 0, args[0])
        self.sub = {}
        for k in range(last + 1):
            a = base + struct.unpack_from("<H", image, tab + 2 * k)[0]
            n, raw, seen = 0, 0, set()
            while a not in seen and len(seen) < 400:
                seen.add(a)
                i = next(md.disasm(image[a:a + 16], a), None)
                if i is None or i.mnemonic in ("ret", "retf"):
                    break
                if i.mnemonic == "call" and i.op_str == hex(argfn):
                    n += 1
                elif "es:[bx + si]" in i.op_str or "es:[bx + di]" in i.op_str:
                    raw += 1
                if i.mnemonic == "jmp" and i.op_str.startswith("0x"):
                    a = int(i.op_str, 16)
                    continue
                a = i.address + i.size
            if raw not in (0, 2):
                raise ValueError("ADV.EXE: sub-op %02x reads %d bytes of its own" % (k, raw))
            self.sub[k] = (n, raw == 2)


def _arg(d, i):
    b = d[i]
    if b == 0xFF:
        return i + 2
    if b == 0xFE or b <= 0x1A:
        return i + 3
    raise ValueError("an argument %02x at %x" % (b, i))


def layout(d):
    """(code start, text start, the five header words)."""
    h = struct.unpack_from("<5H", d, 0)
    code = 0xA + ((h[0] + h[1]) & ~1) + (h[2] & ~1)
    return code, code + h[3], h


def walk(d, build):
    """[(the place of a text's offset (big-endian), the offset)]: the code's ops one after another to
    the text's start (the code's last byte may be a pad, the text starting on an even offset)."""
    return [(p, off) for kind, p, off, _s, _a in events(d, build) if kind == "text"]


def events(d, build):
    """[(kind, place, offset, sub-op, its first argument's bytes)] in the code's order: "text" a
    sub-op with a text, "sub" one without (the ones that show what the texts were put in)."""
    code, text, _h = layout(d)
    out = []
    i = code

    def sub(i):
        s = d[i]
        n, tx = build.sub.get(s, (0, False))
        i += 1
        first = b""
        for k in range(n):
            j = _arg(d, i)
            if k == 0:
                first = d[i:j]
            i = j
        if tx:
            out.append(("text", i, struct.unpack_from(">H", d, i)[0], s, first))
            i += 2
        else:
            out.append(("sub", i, None, s, first))
        return i
    while i < text:
        if i == text - 1:
            break
        op = d[i]
        if op == 0x00:
            i = sub(i + 1)
        elif op == 0x05:
            i = sub(i + 4)
        elif op == 0x09:
            i += 7 + 3 * d[i + 6]
        elif op in (0x0A, 0x0C, 0x0D):
            i = _arg(d, i + 1)
        elif op == 0x12:
            i = _arg(d, i + 5)
        elif op in MAIN:
            i += MAIN[op]
        else:
            raise ValueError("op %02x at %x" % (op, i))
    if i not in (text, text - 1):
        raise ValueError("the code runs past its end (%x, %x)" % (i, text))
    return out


def text_at(d, off):
    code, text, _h = layout(d)
    p = text + off
    return d[p:d.index(0, p)]


def rebuild(d, refs, new):
    """The scenario with its text section laid out anew: new {offset: bytes (without the NUL)} for the
    texts that change; every text the code reads written once, NUL-ended and padded to an even
    length, the offsets moved."""
    code, text, h = layout(d)
    offs = sorted({off for _p, off in refs})
    sect, at = bytearray(), {}
    for off in offs:
        at[off] = len(sect)
        b = new.get(off, text_at(d, off))
        sect += b + b"\0"
        if len(sect) & 1:
            sect += b"\0"
    out = bytearray(d[:text]) + sect
    struct.pack_into("<H", out, 8, len(sect))
    for p, off in refs:
        struct.pack_into(">H", out, p, at[off])
    return bytes(out)
