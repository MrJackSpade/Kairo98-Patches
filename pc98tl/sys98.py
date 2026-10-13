"""four nine's System-98 (SYS98.EXE: Mugen Yasoukyoku, Gaogao! 3rd): the archives and the scripts.

Archives: DISK_?.CAT lists the members of DISK_?.LIB.  A catalog is "Cat1" and a word, the count,
then count entries of 22 bytes compressed (or "Cat0" and the entries as they are): the name (12
bytes, NUL-padded), a word (1: the member is compressed), the member's size in the archive and its
offset after the archive's 6-byte header ("Lib0" and a word).  A compressed member (and a
compressed catalog, from its offset 2) is a dword, the size unpacked, and the LZSS stream
(`unpack`: SYS98.EXE's own routine).

SYS98.EXE is packed with LZEXE 0.91 (its signature removed); `pc98tl/sys98.py`'s notes on the
program are read off the unpacked image.
"""
import bisect
import re
import struct

from .adl import _asm16

LIB_HEAD = 6


def unpack(src, i=0):
    """The LZSS stream at src[i:] (after its size dword): a flag byte, LSB first, a set bit a
    literal; else a word: 0 the end, else the window's position (word >> 4) and the length (low
    four bits + 3); the 4 KB window (zeros) is written from 1.  (data, the end's offset)"""
    win = bytearray(0x1000)
    r = 1
    out = bytearray()
    while True:
        flags = src[i]
        i += 1
        for k in range(8):
            if flags >> k & 1:
                c = src[i]
                i += 1
                out.append(c)
                win[r] = c
                r = (r + 1) & 0xFFF
            else:
                w = src[i] | src[i + 1] << 8
                i += 2
                if w == 0:
                    return bytes(out), i
                pos, n = w >> 4, (w & 0xF) + 3
                for _ in range(n):
                    c = win[pos]
                    pos = (pos + 1) & 0xFFF
                    out.append(c)
                    win[r] = c
                    r = (r + 1) & 0xFFF


def pack(data):
    """data as an LZSS stream `unpack` reads, with its size dword: the longest earlier match (3 to 18
    bytes, within the window's last 4095) else a literal; the word 0 (the end) never a match."""
    out = bytearray(struct.pack("<I", len(data)))
    chains = {}
    i, n = 0, len(data)
    items = []

    def add(p):
        if p + 3 <= n:
            chains.setdefault(data[p:p + 3], []).append(p)
    while i < n:
        best, at = 0, 0
        for j in reversed(chains.get(data[i:i + 3], [])[-48:]):
            if i - j > 4095:
                break
            k = 0
            while k < 18 and i + k < n and data[j + k] == data[i + k]:
                k += 1
            if k > best:
                best, at = k, j
                if k == 18:
                    break
        if best >= 3:
            w = (((1 + at) & 0xFFF) << 4) | (best - 3)
            if w == 0:
                best = 0
        if best >= 3:
            items.append(struct.pack("<H", w))
            for p in range(i, i + best):
                add(p)
            i += best
        else:
            items.append(data[i:i + 1])
            add(i)
            i += 1
    items.append(b"\0\0")
    for k in range(0, len(items), 8):
        group = items[k:k + 8]
        flags = sum(1 << b for b, it in enumerate(group) if len(it) == 1)
        out.append(flags)
        for it in group:
            out += it
    return bytes(out)


SCRIPT_BASE = 0x100     # a script's code starts here (the bytes before it are zeros)
SCRIPT_ROOM = 0x4000    # the program reads this much of a script

# op: (length in bytes with the op's word, {offset in the op: what the word there points at}).
# "code": a jump's (or a call's, or a handler's: ops 40h, 41h) target; "text": a message; "file": a
# file's name; "string": a string op 59h copies to a variable; "data": data in the script (a glyph, a
# table).  None as the length: the op's own rule (op 13h, a switch).
OPS = {
    0x00: (2, {}), 0x02: (14, {10: "file"}), 0x03: (14, {}), 0x04: (4, {}), 0x05: (4, {}), 0x06: (2, {}),
    0x07: (6, {}), 0x08: (6, {}), 0x09: (4, {}), 0x0A: (4, {2: "code"}), 0x0B: (6, {}), 0x0C: (6, {}),
    0x0D: (4, {2: "code"}), 0x0E: (4, {2: "code"}), 0x0F: (4, {2: "code"}), 0x10: (4, {2: "code"}),
    0x11: (4, {2: "code"}), 0x12: (4, {2: "code"}), 0x13: (None, {}), 0x14: (10, {}),
    0x15: (6, {4: "text"}), 0x16: (8, {6: "text"}), 0x18: (6, {}), 0x19: (6, {}), 0x1A: (4, {2: "file"}),
    0x1B: (2, {}), 0x1C: (2, {}), 0x1D: (4, {}), 0x1E: (4, {}), 0x1F: (4, {2: "file"}), 0x20: (2, {}),
    0x21: (4, {}), 0x22: (4, {}), 0x24: (6, {}), 0x25: (6, {}), 0x26: (12, {}), 0x27: (6, {}),
    0x28: (6, {}), 0x29: (6, {4: "file"}), 0x2A: (6, {4: "file"}), 0x2D: (6, {}), 0x2E: (6, {}),
    0x2F: (18, {}), 0x32: (6, {}), 0x33: (4, {}), 0x34: (4, {}), 0x35: (14, {}), 0x36: (2, {}),
    0x38: (6, {}), 0x39: (6, {}), 0x3A: (18, {}), 0x3B: (18, {}), 0x3C: (12, {}), 0x3D: (6, {}),
    0x3E: (6, {}), 0x3F: (6, {}), 0x40: (10, {6: "data", 8: "code"}), 0x41: (10, {8: "code"}), 0x42: (4, {}), 0x43: (6, {}),
    0x4A: (6, {4: "file"}), 0x4B: (6, {4: "file"}), 0x4C: (2, {}), 0x4D: (4, {}), 0x4E: (4, {}),
    0x4F: (4, {}), 0x50: (4, {}), 0x51: (6, {}), 0x52: (6, {}), 0x53: (6, {}), 0x54: (4, {2: "code"}),
    0x55: (2, {}), 0x56: (6, {}), 0x57: (8, {}), 0x58: (8, {}), 0x59: (6, {4: "string"}), 0x5A: (4, {}),
    0x5B: (6, {}), 0x5E: (12, {}), 0x5F: (4, {}), 0x60: (8, {6: "file"}), 0x62: (6, {}), 0x63: (18, {}),
    0x64: (18, {}), 0x68: (6, {}), 0x69: (8, {}), 0x6A: (10, {}), 0x6B: (10, {}), 0x6E: (6, {}),
    0x72: (4, {}), 0x73: (4, {}), 0x74: (6, {4: "code"}), 0x75: (6, {4: "data"}), 0x76: (18, {}),
    0x77: (18, {}), 0x78: (6, {}), 0x79: (4, {2: "data"}), 0x7A: (4, {}), 0x7B: (6, {4: "code"}),
    0x7F: (4, {}), 0x80: (6, {4: "file"}), 0x81: (6, {4: "file"}), 0x82: (2, {}), 0x83: (4, {}),
    0x8D: (2, {}), 0x8F: (6, {4: "file"}), 0x90: (2, {}), 0x91: (6, {}), 0x92: (2, {}), 0x93: (4, {}),
    0x94: (2, {}), 0x95: (18, {}), 0x96: (6, {}), 0x97: (2, {}),
}


# SYS98FM.EXE (Gaogao! 3rd): the same ops but 2Eh, and these (lengths and pointers read off its handlers)
OPS_FM = {k: v for k, v in OPS.items() if k != 0x2E}
OPS_FM.update({
    0x37: (4, {2: "file"}), 0x61: (4, {2: "file"}), 0x67: (10, {}), 0x84: (2, {}), 0x85: (2, {}),
    0x86: (4, {2: "data"}), 0x87: (22, {}), 0x88: (8, {}), 0x89: (4, {2: "data"}), 0x8A: (10, {}),
    0x8B: (8, {}), 0x8C: (2, {}), 0x8E: (2, {}), 0x29: (8, {}), 0x2A: (8, {}),
})


def decode(member):
    """A script as the program runs it: its bytes from 100h on XORed with 1 (op 1Fh's loader)."""
    d = bytearray(member)
    for i in range(SCRIPT_BASE, len(d)):
        d[i] ^= 1
    return bytes(d)


encode = decode


# ops after which the next bytes are not run (a goto, a switch, a return, the end, another script)
STOPS = {0x00, 0x0A, 0x13, 0x55, 0x1F, 0x7F}


def _probe(word, i, org, end, table):
    """Whether the code at i runs on (op after op) to an op that stops without an unknown op."""
    for _k in range(4096):
        if not org + SCRIPT_BASE <= i <= end - 2 or word(i) not in table:
            return False
        op = word(i)
        n = table[op][0]
        if n is None or op in STOPS:
            return True
        i += n
    return True


def walk(d, org=0, entries=(), ops_table=None, barriers=()):
    """(ops {addr: (op, end)}, refs [(addr of the word, kind, target)]): the script's code, from 100h
    and every place a jump goes (the scripts keep their messages and data between the code too).
    Addresses are org + the offset in the file: a script is loaded at 0, the shared routines' script
    (op 8Fh's, buffer 1) at 4000h; a jump to the other one's addresses is not followed ("extern"; a
    pointer of another kind there "extern_" and its kind);
    entries: more places its code starts (the shared routines', from the scripts' "extern" jumps)."""
    ops, refs = {}, []
    work = [org + SCRIPT_BASE] + list(entries)
    end = org + len(d)

    def word(a):
        return struct.unpack_from("<H", d, a - org)[0]
    while work:
        i = work.pop()
        while i not in ops:
            if not org + SCRIPT_BASE <= i <= end - 2:
                raise ValueError("code at %x outside the script" % i)
            op = word(i)
            table = ops_table or OPS
            if op not in table:
                raise ValueError("op %02x at %x not known" % (op, i))
            n, fields = table[op]
            if n is None:
                # op 13h: the variable, then the table of targets: as many as run up to the lowest
                # place one of them goes (the code after the table); 0 a case with none
                j, low = i + 4, end
                while j < low and j not in barriers:    # (barriers: texts a table cannot run into)
                    t = word(j)
                    if t == 0:
                        j += 2
                        continue
                    if not org + SCRIPT_BASE <= t < end:
                        break
                    if ops_table is not None and not _probe(word, t, org, end, table):
                        if j > i + 4:       # (past the first: the table has ended)
                            break
                        j += 2              # (SYS98FM: the first case never taken, pointing at data)
                        continue
                    refs.append((j, "code", t))
                    work.append(t)
                    low = min(low, t)
                    j += 2
                n = j - i
            for at, kind in fields.items():
                t = word(i + at)
                if not org <= t < end:
                    kind = "extern" if kind == "code" else "extern_" + kind
                refs.append((i + at, kind, t))
                if kind == "code":
                    work.append(t)
            ops[i] = (op, i + n)
            if op in STOPS:
                break
            i += n
    return ops, refs


# a text's control bytes (the renderer's table at 2D90h): their operand bytes; 00h ends the text, 01h
# waits for a key and clears the window, 02h waits for a key, 0Dh starts a new line, 09h moves on 8 dots;
# 03h the colour, 04h a name (one of the 80-byte strings op 59h sets), 05h a number (a variable), 0Eh
# nothing; 0Fh an escape: a byte, 00h and one more byte, else none
CONTROL = {0x01: 0, 0x02: 0, 0x03: 1, 0x04: 1, 0x05: 2, 0x06: 1, 0x07: 1, 0x08: 1, 0x09: 0, 0x0A: 1,
           0x0B: 1, 0x0C: 1, 0x0D: 0, 0x0E: 1}


CONTROL_FM = {**CONTROL, 0x07: 0, 0x0A: 0}     # SYS98FM.EXE's: 07h and 0Ah take no byte


def atoms(d, i, control=None):
    """[(kind, bytes)] of the text at i up to its 00h (not included): "c" a control, "n" a new line
    (0Dh), "p" a new page (01h), "k" a key wait (02h), "t" a character (Shift-JIS, two bytes), "a" a
    byte the program draws half-width (an ASCII byte or a half-width kana)."""
    out = []
    while True:
        b = d[i]
        if b == 0:
            return out
        if b == 0x0F:
            n = 3 if d[i + 1] == 0 else 2
            out.append(("c", d[i:i + n]))
            i += n
        elif b < 0x0F:
            n = 1 + (control or CONTROL)[b]
            out.append(({0x0D: "n", 0x01: "p", 0x02: "k"}.get(b, "c"), d[i:i + n]))
            i += n
        elif 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
            out.append(("t", d[i:i + 2]))
            i += 2
        else:
            out.append(("a", d[i:i + 1]))
            i += 1


def text_end(d, i, control=None):
    """The offset after a text's 00h."""
    return i + sum(len(r) for _k, r in atoms(d, i, control)) + 1


def rebuild(d, org, refs, new, keep_layout=False, room=SCRIPT_ROOM, control=None):
    """The script with new texts: new {address of a text or a string: its bytes, without the 00h}.
    The old ones are cut out and what follows them moves up (every pointer in the script moved with
    it), the new ones go after the end; keep_layout (the shared routines' script, which the others call
    by address): nothing moves, the new texts go after the end.  OverflowError past room."""
    cuts = []
    if not keep_layout:
        for t in sorted(new):
            s, e = t - org, text_end(d, t - org, control)
            if cuts and s <= cuts[-1][1]:
                cuts[-1][1] = max(cuts[-1][1], e)
            else:
                cuts.append([s, e])
    starts = [s for s, _e in cuts]
    before = [0]
    for s, e in cuts:
        before.append(before[-1] + e - s)

    def moved(p):
        k = bisect.bisect_right(starts, p) - 1
        if k >= 0 and p < cuts[k][1]:
            raise ValueError("a pointer to %x, inside a text cut out" % (p + org))
        return p - before[k + 1]
    out = bytearray()
    p = 0
    for s, e in cuts:
        out += d[p:s]
        p = e
    out += d[p:]
    at = {}
    for t in sorted(new):
        at[t] = len(out)
        out += new[t] + b"\0"
    if len(out) > room:
        raise OverflowError(len(out))
    for a, kind, t in refs:
        w = moved(a - org)
        if kind.startswith("extern"):
            continue
        v = org + (at[t] if t in at else moved(t - org))
        struct.pack_into("<H", out, w, v)
    if len(out) > room:
        raise OverflowError(len(out))
    return bytes(out)


# the glyph fetch (SYS98.EXE 105Eh): push cx, dx, di, di / xor ax, ax / lodsb / cmp al, 80h / jb blank /
# cmp al, A0h / jb two-byte / cmp al, E0h / jb blank / mov ah, al / mov al, 0Bh / out 68h, al / lodsb
GLYPH_SIG = re.compile(rb"\x51\x52\x57\x57\x33\xc0\xac\x3c\x80\x72(.)\x3c\xa0\x72.\x3c\xe0\x72.\x8a\xe0"
                       rb"\xb0\x0b\xe6\x68\xac", re.S)
# the kanji ROM's read with ax the JIS code: push ax / out A1h, al / mov al, ah / sub al, 20h / out A3h, al
CG_READ_SIG = re.compile(rb"\x50\xe6\xa1\x8a\xc4\x2c\x20\xe6\xa3")
# the ops' dispatch: cmp ax, the last op / jbe +2 / xor ax, ax / add ax, ax / add ax, table / mov bx, ax /
# jmp cs:[bx]
DISPATCH_SIG = re.compile(rb"\x3d(..)\x76\x02\x33\xc0\x03\xc0\x05(..)\x8b\xd8\x2e\xff\x27", re.S)
# the ends: op 01h (an unknown op: its message, exit 1), op 00h (exit 0), op 7Fh (exit with a variable):
# each restores the screen (a call), prints a string (int DCh) and exits
EXIT_SIG = re.compile(rb"\xe8(..)\x68(..)\x1f\xba(..)\xb4\x01\xb1\x10\xcd\xdc\xb8\x01\x4c\xcd\x21"
                      rb"\xe8(..)\x68(..)\x1f\xba(..)\xb4\x01\xb1\x10\xcd\xdc\xb8\x00\x4c\xcd\x21"
                      rb"\xe8(..)\x50\xe8(..)\x68(..)\x1f\xba(..)\xb4\x01\xb1\x10\xcd\xdc\x58\xb4\x4c\xcd\x21",
                      re.S)


def patch_program(image, relocs):
    """(image, relocs): SYS98.EXE's image (unpacked, lzexe.unpack) and its relocations, drawing ASCII
    half-width: a byte 21h-7Fh, which the
    program draws as a blank, is fetched from the kanji ROM's half-width row (JIS 29xxh), whose
    characters the program already moves on by one cell.  The hook's code goes where the three ends'
    code was: they share one tail now (each still prints its string and exits with its code)."""
    img = bytearray(image)
    w = lambda a: struct.unpack_from("<H", img, a)[0]       # noqa: E731
    mg, mc, md, me = (list(s.finditer(img)) for s in (GLYPH_SIG, CG_READ_SIG, DISPATCH_SIG, EXIT_SIG))
    if len(mg) != 1 or len(md) != 1 or len(me) != 1 or not mc:
        raise SystemExit("SYS98.EXE: the patch sites found %d, %d, %d, %d times" % (
            len(mg), len(mc), len(md), len(me)))
    site = mg[0].start() + 7
    blank = (site + 4 + struct.unpack("<b", mg[0].group(1))[0]) & 0xFFFF
    back = site + 4
    cg = [m.start() for m in mc if m.start() > site][0]
    last, table = struct.unpack("<HH", md[0].group(1) + md[0].group(2))
    e = me[0]
    a01 = e.start()
    a00 = a01 + 21
    a7f = a00 + 21
    end = e.end()
    if w(table) != a00 or w(table + 2) != a01 or w(table + 2 * 0x7F) != a7f:
        raise SystemExit("SYS98.EXE: the ends are not ops 00h, 01h and 7Fh")
    rel = lambda at, g: (at + 3 + struct.unpack("<h", e.group(g))[0]) & 0xFFFF   # noqa: E731
    restore, getvar = rel(a01, 1), rel(a7f, 7)
    seg, msg01, msg00 = w(a01 + 4), w(a01 + 8), w(a00 + 8)
    if rel(a00, 4) != restore or w(a00 + 4) != seg or w(a7f + 12) != msg00:
        raise SystemExit("SYS98.EXE: the ends differ")
    src = """
e01:
    .byte 0x6a, 0x01
    mov dx, {msg01}
    jmp common
e7f:
    CALLN {getvar}
    push ax
    jmp t
e00:
    .byte 0x6a, 0x00
t:
    mov dx, {msg00}
common:
    push dx
    CALLN {restore}
    pop dx
segw:
    .byte 0x68, {seg_lo}, {seg_hi}
    pop ds
    mov ah, 1
    mov cl, 0x10
    int 0xdc
    pop ax
    mov ah, 0x4c
    int 0x21
hook:
    cmp al, 0x80
    jae two
    cmp al, 0x20
    jbe none
    mov cl, al
    mov ax, 0x290b
    out 0x68, al
    mov al, cl
    JMPN {cg}
none:
    JMPN {blank}
two:
    JMPN {back}
""".format(msg01=hex(msg01), msg00=hex(msg00), getvar=hex(getvar), restore=hex(restore), seg=hex(seg),
           cg=hex(cg), blank=hex(blank), back=hex(back), seg_lo=hex(seg & 0xFF), seg_hi=hex(seg >> 8))
    code, labs = _asm16(src, a01, ["e01", "e00", "e7f", "hook", "segw"])
    if a01 + len(code) > end or labs["e01"] != a01:
        raise SystemExit("SYS98.EXE: the hook does not fit (%d bytes, %d)" % (len(code), end - a01))
    img[a01:a01 + len(code)] = code
    img[a01 + len(code):end] = b"\x90" * (end - a01 - len(code))
    for k in range(last + 1):
        v = w(table + 2 * k)
        if v == a00:
            struct.pack_into("<H", img, table + 2 * k, labs["e00"])
        elif v == a7f:
            struct.pack_into("<H", img, table + 2 * k, labs["e7f"])
    # the program's other jumps and calls to the ends (its code: up to the ends' segment's data)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    md16 = Cs(CS_ARCH_X86, CS_MODE_16)
    md16.skipdata = True
    moved = {a00: labs["e00"], a7f: labs["e7f"]}
    for ins in md16.disasm(bytes(image[:seg * 16]), 0):
        if ins.mnemonic in ("jmp", "call") and ins.size == 3 and ins.bytes[0] in (0xE8, 0xE9) \
                and not a01 <= ins.address < end:
            t = (ins.address + 3 + struct.unpack_from("<h", image, ins.address + 1)[0]) & 0xFFFF
            if t in moved:
                struct.pack_into("<H", img, ins.address + 1, (moved[t] - (ins.address + 3)) & 0xFFFF)
    img[site:site + 4] = b"\xe9" + struct.pack("<H", (labs["hook"] - (site + 3)) & 0xFFFF) + b"\x90"
    # the ends' segment words were relocated; the new code has one (the push of the segment)
    relocs = [r for r in relocs if not a01 <= r < end] + [labs["segw"] + 1]
    return bytes(img), sorted(relocs)


def mz_unpack(exe):
    """unpack()'s result (pc98tl/lzexe.py) for a program not packed: its image, relocations, entry,
    stack and memory."""
    h = struct.unpack_from("<13H", exe, 0)
    hdr = h[4] * 16
    size = h[2] * 512 - ((512 - h[1]) if h[1] else 0) - hdr
    relocs = [struct.unpack_from("<H", exe, h[12] + 4 * k + 2)[0] * 16 +
              struct.unpack_from("<H", exe, h[12] + 4 * k)[0] for k in range(h[3])]
    return {"image": exe[hdr:hdr + size], "relocs": relocs, "ip": h[10], "cs": h[11], "sp": h[8],
            "ss": h[7], "memory": size + h[5] * 16, "most": size + h[6] * 16}


# SYS98FM.EXE (Gaogao! 3rd): the ops' dispatch: cmp ax, 100h / jb +2 / xor ax, ax / add ax, ax /
# add ax, table / mov bx, ax / jmp cs:[bx]; the ends print through DOS (int 21h, ah 9)
DISPATCH_FM_SIG = re.compile(rb"\x3d\x00\x01\x72\x02\x33\xc0\x03\xc0\x05(..)\x8b\xd8\x2e\xff\x27", re.S)
EXIT_FM_SIG = re.compile(rb"\xe8(..)\x68(..)\x1f\xba(..)\xb4\x09\xcd\x21\xb8\x01\x4c\xcd\x21"
                         rb"\xe8(..)\x68(..)\x1f\xba(..)\xb4\x09\xcd\x21\xb8\x00\x4c\xcd\x21"
                         rb"\xe8(..)\x50\xe8(..)\x68(..)\x1f\xba(..)\xb4\x09\xcd\x21\x58\xb4\x4c\xcd\x21",
                         re.S)


def patch_program_fm(image, relocs):
    """patch_program for SYS98FM.EXE (not packed; its ends print through DOS): (image, relocs)."""
    img = bytearray(image)
    w = lambda a: struct.unpack_from("<H", img, a)[0]       # noqa: E731
    mg, mc, md, me = (list(s.finditer(img)) for s in (GLYPH_SIG, CG_READ_SIG, DISPATCH_FM_SIG, EXIT_FM_SIG))
    if len(mg) != 1 or len(md) != 1 or len(me) != 1 or not mc:
        raise SystemExit("SYS98FM.EXE: the patch sites found %d, %d, %d, %d times" % (
            len(mg), len(mc), len(md), len(me)))
    site = mg[0].start() + 7
    blank = (site + 4 + struct.unpack("<b", mg[0].group(1))[0]) & 0xFFFF
    back = site + 4
    cg = [m.start() for m in mc if m.start() > site][0]
    table = struct.unpack("<H", md[0].group(1))[0]
    e = me[0]
    a01 = e.start()
    a00 = a01 + 19
    a7f = a00 + 19
    end = e.end()
    if w(table) != a00 or w(table + 2) != a01 or w(table + 2 * 0x7F) != a7f:
        raise SystemExit("SYS98FM.EXE: the ends are not ops 00h, 01h and 7Fh")
    rel = lambda at, g: (at + 3 + struct.unpack("<h", e.group(g))[0]) & 0xFFFF   # noqa: E731
    restore, getvar = rel(a01, 1), rel(a7f, 7)
    seg, msg01, msg00 = w(a01 + 4), w(a01 + 7), w(a00 + 7)
    if rel(a00, 4) != restore or w(a00 + 4) != seg or w(a7f + 11) != msg00:
        raise SystemExit("SYS98FM.EXE: the ends differ")
    src = """
e01:
    .byte 0x6a, 0x01
    .byte 0x68, {m01_lo}, {m01_hi}
    jmp common
e7f:
    CALLN {getvar}
    push ax
    jmp t
e00:
    .byte 0x6a, 0x00
t:
    .byte 0x68, {m00_lo}, {m00_hi}
common:
    CALLN {restore}
    pop dx
segw:
    .byte 0x68, {seg_lo}, {seg_hi}
    pop ds
    mov ah, 9
    int 0x21
    pop ax
    mov ah, 0x4c
    int 0x21
hook:
    cmp al, 0x80
    jae two
    cmp al, 0x20
    jbe none
    mov cl, al
    mov ax, 0x290b
    out 0x68, al
    mov al, cl
    JMPN {cg}
none:
    JMPN {blank}
two:
    JMPN {back}
""".format(getvar=hex(getvar), restore=hex(restore), cg=hex(cg), blank=hex(blank), back=hex(back),
           seg_lo=hex(seg & 0xFF), seg_hi=hex(seg >> 8), m01_lo=hex(msg01 & 0xFF), m01_hi=hex(msg01 >> 8),
           m00_lo=hex(msg00 & 0xFF), m00_hi=hex(msg00 >> 8))
    code, labs = _asm16(src, a01, ["e01", "e00", "e7f", "hook", "segw"])
    if a01 + len(code) > end or labs["e01"] != a01:
        raise SystemExit("SYS98FM.EXE: the hook does not fit (%d bytes, %d)" % (len(code), end - a01))
    img[a01:a01 + len(code)] = code
    img[a01 + len(code):end] = b"\x90" * (end - a01 - len(code))
    for k in range(0x100):
        v = w(table + 2 * k)
        if v == a00:
            struct.pack_into("<H", img, table + 2 * k, labs["e00"])
        elif v == a7f:
            struct.pack_into("<H", img, table + 2 * k, labs["e7f"])
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    md16 = Cs(CS_ARCH_X86, CS_MODE_16)
    md16.skipdata = True
    moved = {a00: labs["e00"], a7f: labs["e7f"]}
    for ins in md16.disasm(bytes(image[:seg * 16]), 0):
        if ins.mnemonic in ("jmp", "call") and ins.size == 3 and ins.bytes[0] in (0xE8, 0xE9) \
                and not a01 <= ins.address < end:
            t = (ins.address + 3 + struct.unpack_from("<h", image, ins.address + 1)[0]) & 0xFFFF
            if t in moved:
                struct.pack_into("<H", img, ins.address + 1, (moved[t] - (ins.address + 3)) & 0xFFFF)
    img[site:site + 4] = b"\xe9" + struct.pack("<H", (labs["hook"] - (site + 3)) & 0xFFFF) + b"\x90"
    relocs = [r for r in relocs if not a01 <= r < end] + [labs["segw"] + 1]
    return bytes(img), sorted(relocs)


class Catalog:
    """A catalog and its archive: entries [name, compressed, size, offset]."""

    def __init__(self, cat, lib):
        self.raw_cat, self.lib = cat, lib
        tag, n = cat[:4], struct.unpack_from("<H", cat, 4)[0]
        if tag == b"Cat1":
            body, _end = unpack(cat, 6)
        elif tag == b"Cat0":
            body = cat[6:6 + 22 * n]
        else:
            raise ValueError("not a catalog")
        self.tag = tag
        self.entries = []
        for k in range(n):
            e = body[22 * k:22 * (k + 1)]
            name = e[:12].split(b"\0")[0].decode("ascii").strip()
            flag, size, off = struct.unpack_from("<HII", e, 12)
            self.entries.append([name, flag, size, off, e[:12]])

    def names(self):
        return [e[0] for e in self.entries]

    def read(self, name):
        for nm, flag, size, off, _r in self.entries:
            if nm == name:
                at = LIB_HEAD + off
                if flag == 1:
                    return unpack(self.lib, at + 4)[0]
                return self.lib[at:at + size]
        raise KeyError(name)
