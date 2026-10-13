"""FourNine's N.A.V.A.L system (Waku Waku Mahjong Panic!: NAVAL.EXE, the scenario player DIANA.EXE,
the mahjong programs SONNET.EXE and TYPHON.EXE): the DSD scripts and the programs' text drawer.

DSD scripts (SNR/*.DSD, BEGIN.DSD, ONGSET.DSD): stored as they are or packed ("eLZ0", the size as a
dword, then pc98tl/sys98.py's LZSS stream).  DIANA reads a script (at most 4268h bytes) to its data
segment's 56h; an offset in a script is from its start (the program adds 56h).

The code is a run of operations, each a word (the operation, below 70h: DIANA's table at DS:5F2C)
and its operands (`LENGTHS`).  Some take a list ended by FFF0h (18h, 24h, 25h); 13h is a switch (a
variable, then a table of offsets as long as the variable's range: it ends where the code it jumps
to, or other code, begins).  Jumps: 0Ah (goto), 0Dh-12h (on the last compare), 59h, 5Bh, 40h, 41h (after
a mouse choice), 54h (call; 55h returns); 1Fh goes to another script, 5Ch calls one (5Dh returns
to the caller's script, read again), 00h and 01h end.  53h stops, the
script going on 5 bytes on (after an 00h) when the game comes back to it (not with FFh).

Text: 15h draws a string (operands: the window, a byte; the string's offset, a word); 47h draws the
one a variable points to (a script's table: written in place).  A string is Shift-JIS and control
codes, ended by 00h: 01h waits for a key and clears the window, 02h waits, 03h marks the place,
0Dh a new line, 04h and 07h the player's names, 05h (a word) a variable's text; 06h, 08h-0Ch,
0Eh-1Ch take a byte; 1Dh, 1Eh (the colours) and 1Fh (the style) take a byte; 20h is a half-width
space; other bytes 21h-7Fh are skipped.  Shift-JIS 8540h-869Fh draw half-width.  The window
(03h: its place, its width in characters, its height in lines) does not break lines.

The drawer is the same routine in DIANA, SONNET and TYPHON.  `hook` rewrites its control-code
branch so that 21h-7Eh draw as half-width letters (NEC 85xxh), one byte a cell.
"""
import struct

from . import sys98

BASE = 0x56
ROOM = 0x4268

LENGTHS = {
    0x00: 2, 0x01: 4, 0x02: 10, 0x03: 12, 0x04: 3, 0x05: 3, 0x06: 2, 0x07: 4, 0x08: 4, 0x09: 3,
    0x0a: 4, 0x0b: 6, 0x0c: 6, 0x0d: 4, 0x0e: 4, 0x0f: 4, 0x10: 4, 0x11: 4, 0x12: 4, 0x14: 10,
    0x15: 5, 0x16: 5, 0x17: 6, 0x19: 6, 0x1a: 4, 0x1b: 2, 0x1c: 2, 0x1d: 4, 0x1e: 4, 0x1f: 4,
    0x20: 2, 0x21: 4, 0x22: 4, 0x23: 3, 0x26: 3, 0x27: 6, 0x28: 6, 0x29: 6, 0x2a: 6, 0x2b: 6,
    0x2c: 6, 0x2d: 6, 0x2e: 3, 0x2f: 4, 0x30: 8, 0x31: 5, 0x32: 5, 0x33: 4, 0x34: 4, 0x35: 9,
    0x36: 6, 0x37: 8, 0x38: 8, 0x39: 13, 0x3a: 18, 0x3b: 13, 0x3c: 18, 0x3d: 8, 0x3e: 4, 0x3f: 6,
    0x40: 10, 0x41: 13, 0x42: 3, 0x43: 6, 0x44: 6, 0x45: 3, 0x46: 5, 0x47: 5, 0x48: 2, 0x49: 2,
    0x4a: 5, 0x4b: 5, 0x4c: 6, 0x4e: 2, 0x4f: 3, 0x50: 4, 0x51: 6, 0x52: 6, 0x53: 3, 0x54: 4,
    0x55: 2, 0x56: 2, 0x57: 4, 0x58: 4, 0x59: 6, 0x5a: 4, 0x5b: 6, 0x5c: 4, 0x5d: 2, 0x5e: 11,
    0x5f: 4, 0x60: 8, 0x61: 4, 0x62: 6, 0x68: 6, 0x69: 4, 0x6a: 10, 0x6b: 10, 0x6d: 3, 0x6e: 18,
    0x6f: 18}
JUMP = {0x0a: 2, 0x0d: 2, 0x0e: 2, 0x0f: 2, 0x10: 2, 0x11: 2, 0x12: 2, 0x54: 2, 0x59: 4, 0x5b: 4, 0x40: 8,
        0x41: 8}
END = {0x00, 0x01, 0x0a, 0x13, 0x1f, 0x40, 0x41, 0x55, 0x5d}
GOTO, JMP, DRAW = 0x1f, 0x0a, 0x15
ONE = {0x01, 0x02, 0x03, 0x04, 0x07, 0x0d}
FILE_OPERANDS = {0x02: 8, 0x1a: 2, 0x1f: 2, 0x4a: 3, 0x4b: 3, 0x5c: 2, 0x60: 6, 0x61: 2, 0x69: 2}


class Version:
    """A release of DIANA: its scripts' place in its data segment, their room, its operations."""

    def __init__(self, base, room, lengths=None, jump=None, end=None, files=None, overlay=None,
                 overlay_room=0, scrambled=False):
        self.base, self.room = base, room
        self.lengths = {**LENGTHS, **(lengths or {})}
        self.jump = {**JUMP, **(jump or {})}
        self.end = END | set(end or ())
        self.files = {**FILE_OPERANDS, **(files or {})}
        self.overlay, self.overlay_room, self.scrambled = overlay, overlay_room, scrambled


# Waku Waku Mahjong Panic!; and 2 (its DIANA: the scripts at 4Ah, 4650h bytes; 4Dh reads a further
# file (M2_SUB.DSD) to 4650h, the code calling into it; 63h is 03h with variables, 64h 41h with a
# variable, 65h reads a word from a script's table; every file scrambled, `unscramble`).
V1 = Version(0x56, 0x4268)
V2 = Version(0x4A, 0x4650, lengths={0x4d: 4, 0x63: 12, 0x64: 13, 0x65: 8}, jump={0x64: 8},
             end={0x64}, files={0x4d: 2}, overlay=0x4650, overlay_room=0x3E80, scrambled=True)


def unscramble(b):
    """A file as DIANA 2 reads it: a byte at an even place one less, at an odd one one more."""
    return bytes((c - 1) & 0xFF if i % 2 == 0 else (c + 1) & 0xFF for i, c in enumerate(b))


def scramble(b):
    return bytes((c + 1) & 0xFF if i % 2 == 0 else (c - 1) & 0xFF for i, c in enumerate(b))


def W(d, a):
    return struct.unpack_from("<H", d, a)[0]


def archive(d):
    """[(name, offset, size)] of a later release's 0Dnn.DAT (Waku Waku Mahjong Panic! 2): the
    directory at the end (its size, with that word, the file's last word), its words XOR 9999h: a 16-byte head
    ("D_Lib"), then 16-byte entries (the name, ended by 00h, and the offset as a dword), ended by
    one named "[[".  DIANA opens a file by its name first, and looks in the archives only when
    that fails."""
    n = W(d, len(d) - 2)
    dr = bytearray(d[len(d) - n:])
    for i in range(0, len(dr) - 1, 2):
        dr[i] ^= 0x99
        dr[i + 1] ^= 0x99
    ents = []
    for i in range(16, len(dr), 16):
        name = bytes(dr[i:i + 12]).split(b"\0")[0]
        at = struct.unpack_from("<I", dr, i + 12)[0]
        ents.append((name.decode("ascii"), at))
        if name == b"[[":
            break
    ends = [at for _nm, at in ents[1:-1]] + [len(d) - n]
    return [(nm, at, end - at) for (nm, at), end in zip(ents[:-1], ends)]


def write_archive(d, members):
    """d (an archive) with its members as members gives them [(name, bytes)]: the data in that
    order, the directory's head as it was but for the count (stored as it is, at 11), "[[End]]" after the
    entries with the data's end (its low word; the high word the directory's size, so that the
    file's last word is it after the XOR)."""
    n = 16 + 16 * (len(members) + 1)
    head = bytearray(d[len(d) - W(d, len(d) - 2):][:16])
    for i in range(16):
        head[i] ^= 0x99
    struct.pack_into("<H", head, 11, len(members) ^ 0x9999)     # (the count as it is stored)
    data, dr = bytearray(), bytearray(head)
    for name, b in members:
        dr += (name.encode("ascii") + b"\0").ljust(12, b" ") + struct.pack("<I", len(data))
        data += b
    dr += b"[[End]]".ljust(12, b" ") + struct.pack("<HH", len(data) & 0xFFFF, n ^ 0x9999)
    return bytes(data) + bytes(c ^ 0x99 for c in dr)


def load(raw):
    """A script as the program reads it."""
    return sys98.unpack(raw, 8)[0] if raw[:4] == b"eLZ0" else raw


def _walk(d, barrier, v, starts):
    ops, inside, todo, bad = {}, set(), list(starts), []
    while todo:
        pc = todo.pop()
        while pc not in ops:
            if pc + 2 > len(d) or pc in inside:
                bad.append(pc)
                break
            op = W(d, pc)
            tg = []
            if op in (0x18, 0x24, 0x25):
                n = 4
                while W(d, pc + n) != 0xFFF0:
                    n += 2
                n += 2
            elif op == 0x13:
                n, low = 4, 1 << 20
                while pc + n < low and pc + n not in barrier and pc + n + 2 <= len(d):
                    w = W(d, pc + n)
                    if w + 2 > len(d) or w in inside or pc <= w < pc + n + 2:
                        break
                    if W(d, w) not in v.lengths and W(d, w) not in (0x13, 0x18, 0x24, 0x25):
                        break                       # (not code: the table has ended)
                    tg.append(w)
                    if w > pc:
                        low = min(low, w)
                    n += 2
            elif op in v.lengths:
                n = v.lengths[op]
            else:
                bad.append(pc)
                break
            if op in v.jump:
                tg.append(W(d, pc + v.jump[op]))
            if op == 0x53 and d[pc + 2] != 0xFF:
                tg.append(pc + 5)                   # (where the script goes on, after an 00h)
            if v.overlay and starts == (0,):
                tg = [t for t in tg if t < v.overlay]       # (a call into the further file)
            ops[pc] = (op, n, tg)
            inside.update(range(pc + 1, pc + n))
            todo.extend(tg)
            if op in v.end:
                break
            pc += n
    return ops, bad


def parse(d, v=V1, starts=(0,)):
    """{offset: (operation, length, [targets])} of the code reached from the start (or from starts:
    a further file's code, d then that file after `v.overlay` bytes).  A switch's table is cut where
    code found on a later pass begins."""
    barrier = frozenset()
    while True:
        ops, bad = _walk(d, barrier, v, tuple(starts))
        nb = frozenset(ops) | frozenset(bad)
        if nb == barrier:
            if bad:
                raise ValueError("no operation at %s" % ", ".join("%04x" % b for b in sorted(set(bad))))
            return ops
        barrier = nb


def reach(ops, starts, stop=(), v=V1):
    """The operations run from starts, not going on past the offsets in stop."""
    seen, todo = set(), list(starts)
    while todo:
        pc = todo.pop()
        while pc in ops and pc not in seen:
            seen.add(pc)
            if pc in stop and pc not in starts:
                seen.discard(pc)
                break
            op, n, tg = ops[pc]
            todo.extend(tg)
            if op in v.end:
                break
            pc += n
    return seen


def units(d, a):
    """(offset, bytes) of the string at a: a character or a control code."""
    i = a
    while i < len(d) and d[i]:
        c = d[i]
        n = 2 if c >= 0x80 else 1 if (c in ONE or c >= 0x20) else 3 if c == 0x05 else 2
        yield i, d[i:i + n]
        i += n


def end(d, a):
    """The offset after the string at a's 00h."""
    e = a
    for i, u in units(d, a):
        e = i + len(u)
    return e + 1


def draws(d, ops):
    """{string offset: [the 15h operations drawing it]}"""
    out = {}
    for pc, (op, n, tg) in ops.items():
        if op == DRAW:
            out.setdefault(W(d, pc + 3), []).append(pc)
    return out


def file_operands(d, ops, v=V1):
    """The offsets the operations naming a file (or other data) point to: a file's name is read
    from the byte after (that byte, below 21h, the disk's number), often a string's 00h."""
    return {W(d, pc + v.files[op]) for pc, (op, n, t) in ops.items() if op in v.files}


def windows(d, ops):
    """{window: (width in cells, height in lines)} as the 03h operations set them (the last
    in the script)."""
    out = {}
    for pc in sorted(ops):
        if ops[pc][0] == 0x03:
            out[d[pc + 2] & 7] = (2 * d[pc + 7], d[pc + 8])
    return out


# ---- the drawer ----

SIG = bytes.fromhex("80fa2075014780fa2072014e")     # cmp dl,20h / jne / inc di / cmp dl,20h / jb / dec si


def hook(image):
    """The drawer's control-code branch rewritten: 1Dh-1Fh as before, 20h a space, 21h-7Eh a half-width
    letter (85h, the letter + 1Fh, past 7Eh one more: NEC's half-width row) drawn by the
    character path.  (image, the branch's offset)"""
    s = image.find(SIG)
    if s < 0 or image.find(SIG, s + 1) >= 0:
        raise ValueError("the drawer's control branch is not found once")
    a0 = s - 0x21                           # cmp dl,1Dh
    if image[a0:a0 + 3] != b"\x80\xfa\x1d" or image[a0 - 0x5b:a0 - 0x57] != b"\x80\xfa\x80\x72":
        raise ValueError("the drawer is not the one expected")
    regs = [W(image, a0 + 10), W(image, a0 + 0x15 + 10), W(image, a0 + 0x0c + 7)]
    if regs != [regs[0], regs[0] + 1, regs[0] + 2]:
        raise ValueError("the drawer's colour bytes are not together")
    loop, char = a0 - 0x16, a0 - 0x56       # add si,2 / call (the character path)
    out = bytearray()

    def at():
        return a0 + len(out)

    def short(op, target):
        out.extend([op, (target - (at() + 2)) & 0xFF])
    out += b"\x80\xfa\x20"                  # cmp dl,20h
    out += b"\x73\x00"                      # jae letter
    j_letter = len(out) - 1
    out += b"\x80\xea\x1d"                  # sub dl,1Dh
    out += b"\x72\x00"                      # jb done (11h-1Ch: nothing)
    j_done = len(out) - 1
    out += b"\x32\xff\x8a\xda"              # xor bh,bh / mov bl,dl
    out += b"\x88\xb7" + struct.pack("<H", regs[0])     # mov [bx+colours],dh
    out[j_done] = len(out) - (j_done + 1)
    short(0xEB, loop)                       # done: jmp add si,2
    out[j_letter] = len(out) - (j_letter + 1)
    out += b"\x74\x00"                      # je space
    j_space = len(out) - 1
    out += b"\x4e"                          # dec si (a byte)
    out += b"\x80\xc2\x1f\x80\xfa\x7f\x80\xda\xff"     # add dl,1Fh / cmp dl,7Fh / sbb dl,-1
    out += b"\x8a\xf2\xb2\x85"              # mov dh,dl / mov dl,85h
    out += b"\xe9" + struct.pack("<h", char - (at() + 3))
    out[j_space] = len(out) - (j_space + 1)
    out += b"\x47\x4e"                      # space: inc di / dec si
    short(0xEB, loop)
    room = 0x2f
    if len(out) > room:
        raise ValueError("the drawer's branch does not fit")
    img = bytearray(image)
    img[a0:a0 + room] = bytes(out) + b"\x90" * (room - len(out))
    return bytes(img), a0


def encode(text):
    """English as the hooked drawer takes it: ASCII a byte (a space 20h), else Shift-JIS."""
    out = bytearray()
    for ch in text:
        if " " <= ch <= "~":
            out.append(ord(ch))
        else:
            try:
                out += ch.encode("cp932")
            except UnicodeEncodeError:
                out.append(ord("?"))
    return bytes(out)
