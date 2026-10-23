"""Himeya Soft's HMY engine on Tokuma Shoten's MAKO-DOS (Bacta): the floppies' file system, the scripts,
and English (the engine draws ASCII half-width itself).

The floppies (`D88`): 2HD, 1024-byte sectors, 9 a track.  MAKO-DOS (`Mako`): the boot sector loads the
kernel (sectors 2-4), which serves int 44h; its directory (`DIR`, track 0 from sector 5, "MAKO-DOS HD
format" first) holds a count (the word at 1Eh) and 16-byte entries from 20h: a name (8) and an extension
(3), a byte, the size (3 bytes, then one).  There are no places: the files are packed one after another,
byte for byte, in the directory's order from track 1 (the kernel adds up the sizes before a file's entry).
A file is looked up on the first drive, then on the second.

AUTOEXEC.COM loads HMY.BIN, the engine, and runs A-01.COM.  A script (*.COM) runs from its first byte at
the 8080-like address 100h of its segment (3000h or 3C00h in turn, 48 KB room each: `ROOM`), op by op
(`OPS`; HMY.BIN's table at 150h, ops 00h-1Ch):
  00 next code...               machine code run with a far call (A-01.COM's screen effect)
  01                            return to AUTOEXEC.COM
  02/03 next n var(2) items(10) a menu of up to 5 choices, the texts at the items' addresses (0: none)
  04 a                          goto
  05 var(2) a...                switch on a variable (its table up to the code after it)
  06                            wait for a key
  07 var(2) v / 08 var(2) v a   set; if the variable is not v, goto a
  09 next text                  a message, Shift-JIS up to 0, in the window (3 lines of 68 cells)
  0A next name / 16 next seg(2) name   load a picture / a file to a segment
  15 name                       run another script
  the others take 0-4 bytes of arguments (`FIXED`)
`Script` walks every op it can reach (and the code past an unconditional jump, when it reads as ops)
and finds every address field and every text; `rebuild` writes a script again with texts of any length
and every address mapped to its new place.  A script with machine code in it (op 00) keeps its layout:
a longer message becomes a goto to its English after the script's end (`tramp`).

Text (MAKOBIOS.BIN's int 40h, AH=20h): Shift-JIS, and bytes below 80h (its half-width path writes to no
plane: `patch_bios` draws them two to a character); 01 waits for a key and clears the window, 02 a new
line; the routine breaks a line at the window's width and goes on down the screen past the window's
lines (the English gets an 01 after each 3 lines).
"""
import re
import struct

ORG = 0x100
ROOM = 0xBF00               # a script's room: 3000h:0100h up to 3C00h (and 3C00h:0100h up to 4800h)
DIR = (0, 5)                # the directory's track and sector
DATA_TRACK = 1
HEAD = b"MAKO-DOS HD format"
FIXED = {0x01: 1, 0x04: 3, 0x06: 1, 0x07: 4, 0x08: 6, 0x0B: 5, 0x0C: 1, 0x0D: 1, 0x0E: 1, 0x0F: 1, 0x10: 1,
         0x11: 1, 0x12: 2, 0x13: 3, 0x14: 3, 0x17: 3, 0x18: 1, 0x19: 1, 0x1A: 3, 0x1B: 3, 0x1C: 3}
NEXT = (0x00, 0x02, 0x03, 0x09, 0x0A, 0x16)
ITEMS = 5
MSG_WIDTH, MSG_LINES = 68, 3
ITEM_WIDTH = 12

DISPATCH = re.compile(rb"\x8a\x1c\x32\xff\xd1\xe3\x2e\x8b\x9f(..)\xff\xe3", re.S)
MSG_WINDOW = re.compile(rb"\xbd(..)\xb9(..)\xba(..)\xb8\x02\x23", re.S)
ITEM_WINDOW = re.compile(rb"\xbd(..)\xb9(..)\xba\x01\x00\xb8\x00\x23", re.S)


class D88:
    """A D88 image's sectors, by track (cylinder * 2 + head) and sector, read and written in place."""

    def __init__(self, data):
        self.raw = bytearray(data)
        self.at, self.size = {}, None
        for t in range(164):
            off = struct.unpack_from("<I", self.raw, 0x20 + 4 * t)[0]
            if not off or off >= len(self.raw):
                continue
            p = off
            ns = struct.unpack_from("<H", self.raw, p + 4)[0]
            for _ in range(ns):
                c, h, r = self.raw[p], self.raw[p + 1], self.raw[p + 2]
                size = struct.unpack_from("<H", self.raw, p + 14)[0]
                self.at[(c * 2 + h, r)] = p + 16
                self.size = self.size or size
                p += 16 + size
        self.spt = max(r for _t, r in self.at)
        self.tracks = max(t for t, _r in self.at) + 1

    def offset(self, pos):
        """(track, sector, place in it) of a byte place counted from track 0, sector 1."""
        n, k = divmod(pos, self.size)
        return n // self.spt, n % self.spt + 1, k

    def capacity(self):
        return self.tracks * self.spt * self.size

    def read(self, pos, n):
        out = bytearray()
        while n > 0:
            t, r, k = self.offset(pos)
            o = self.at[(t, r)]
            take = min(n, self.size - k)
            out += self.raw[o + k:o + k + take]
            pos, n = pos + take, n - take
        return bytes(out)

    def write(self, pos, data):
        i = 0
        while i < len(data):
            t, r, k = self.offset(pos + i)
            o = self.at[(t, r)]
            take = min(len(data) - i, self.size - k)
            self.raw[o + k:o + k + take] = data[i:i + take]
            i += take


class Mako:
    """A MAKO-DOS floppy: [(name, bytes)] in the directory's order."""

    def __init__(self, d88):
        self.d = d88
        self.dir_at = (DIR[0] * d88.spt + DIR[1] - 1) * d88.size
        head = d88.read(self.dir_at, 0x20)
        if not head.startswith(HEAD):
            raise ValueError("not a MAKO-DOS floppy")
        n = struct.unpack_from("<H", head, 0x1E)[0]
        ents = d88.read(self.dir_at + 0x20, 16 * n)
        self.entries, at = [], DATA_TRACK * d88.spt * d88.size
        self.data_at = at
        for k in range(n):
            e = ents[16 * k:16 * k + 16]
            size = e[12] | e[13] << 8 | e[14] << 16
            name = e[:8].decode("latin-1").rstrip() + "." + e[8:11].decode("latin-1").rstrip()
            self.entries.append([name.rstrip("."), e, d88.read(at, size)])
            at += size
        self.end = at

    def names(self):
        return [n for n, _e, _d in self.entries]

    def read(self, name):
        for n, _e, d in self.entries:
            if n == name:
                return d
        raise KeyError(name)

    def write_all(self, files):
        """The files again ({name: bytes} for the changed ones), packed in the directory's order."""
        at = self.data_at
        out = []
        for n, e, d in self.entries:
            d = files.get(n, d)
            e = bytearray(e)
            e[12:15] = len(d).to_bytes(3, "little")
            out.append((n, bytes(e), d))
            at += len(d)
        if at > self.d.capacity():
            raise ValueError("the files take %d bytes, the floppy holds %d" % (at, self.d.capacity()))
        at = self.data_at
        for n, e, d in out:
            self.d.write(at, d)
            at += len(d)
        self.d.write(self.dir_at + 0x20, b"".join(e for _n, e, _d in out))
        self.entries = [[n, e, d] for n, e, d in out]
        self.end = at


def engine(hmy):
    """HMY.BIN's ops (the table's length) and its windows: {"ops", "msg": (width, lines), "item": width}."""
    m = DISPATCH.search(hmy)
    if not m:
        raise ValueError("HMY.BIN: the op dispatch is not found")
    table = struct.unpack("<H", m.group(1))[0] - ORG
    first = struct.unpack_from("<H", hmy, table)[0] - ORG
    ops = (first - table) // 2
    if ops != 0x1D:
        raise ValueError("HMY.BIN: %d ops, not the 29 this driver reads" % ops)
    w = MSG_WINDOW.search(hmy)
    i = ITEM_WINDOW.search(hmy)
    if not w or not i:
        raise ValueError("HMY.BIN: the windows are not found")
    return {"ops": ops, "msg": (struct.unpack("<H", w.group(2))[0], struct.unpack("<H", w.group(3))[0]),
            "item": struct.unpack("<H", i.group(2))[0]}


class ScriptError(ValueError):
    pass


class Script:
    """A script's ops ({place: (op, length)}), its address fields ([place]), its texts ([(kind, start, end)]:
    kind "msg" or "item", end the 0's place)."""

    def __init__(self, d):
        self.d = bytes(d)
        self.ops, self.addrs, self.texts = {}, set(), {}
        self.code = False
        self._walk([0])
        # the ops past an unconditional jump (unreachable or reached in ways the walk does not see)
        while True:
            cov = self.covered()
            k, more = 0, None
            while k < len(self.d):
                if not cov[k] and self.d[k] and (self.d[k] in FIXED or self.d[k] in NEXT[1:] or self.d[k] in (5, 0x15)):
                    if self._parses(k):
                        more = k
                        break
                k += 1
            if more is None:
                break
            self._walk([more])

    def w(self, k):
        return struct.unpack_from("<H", self.d, k)[0]

    def _target(self, k):
        if k + 2 > len(self.d):
            return None
        a = self.w(k) - ORG
        return a if 0 <= a < len(self.d) else None

    def _parses(self, k):
        save = (dict(self.ops), set(self.addrs), dict(self.texts))
        try:
            self._walk([k], probe=True)
            ok = True
        except (ScriptError, ValueError, struct.error):
            ok = False
        self.ops, self.addrs, self.texts = save
        return ok

    def _walk(self, todo, probe=False):
        d = self.d
        labels = set()
        n0 = len(self.ops)
        while todo:
            k = todo.pop()
            while 0 <= k < len(d) and k not in self.ops:
                op = d[k]
                if op in FIXED:
                    n = FIXED[op]
                    if k + n > len(d):
                        raise ScriptError("op %02x at %x runs past the end" % (op, k))
                    self.ops[k] = (op, n)
                    if op == 0x04:
                        self.addrs.add(k + 1)
                        a = self._target(k + 1)
                        if a is not None:
                            labels.add(a)
                            todo.append(a)
                        break
                    if op == 0x08:
                        self.addrs.add(k + 4)
                        a = self._target(k + 4)
                        if a is not None:
                            labels.add(a)
                            todo.append(a)
                    if op == 0x01:
                        break
                    k += n
                    continue
                if op in NEXT:
                    a = self._target(k + 1)
                    if a is None or a <= k + 2:
                        if probe:
                            raise ScriptError("op %02x at %x: no place to go on" % (op, k))
                        break       # (a jump into a 0 of the padding: never taken)
                    if op == 0x00:
                        self.code = True
                    self.ops[k] = (op, a - k)
                    self.addrs.add(k + 1)
                    labels.add(a)
                    if op == 0x09:
                        e = d.index(b"\0", k + 3)
                        if e >= a:
                            raise ScriptError("the message at %x runs past its op" % k)
                        self.texts[k + 3] = ("msg", k + 3, e)
                    if op in (0x02, 0x03):
                        for j in range(ITEMS):
                            p = self._target(k + 6 + 2 * j)
                            if self.w(k + 6 + 2 * j) and p is not None:
                                self.addrs.add(k + 6 + 2 * j)
                                self.texts.setdefault(p, ("item", p, d.index(b"\0", p)))
                    k = a
                    continue
                if op == 0x15:
                    e = d.index(b"\0", k + 1)
                    self.ops[k] = (op, e + 1 - k)
                    break
                if op == 0x05:
                    j, lim, tab = k + 3, len(d), []
                    while j + 2 <= lim and j not in labels and j not in self.ops:
                        a = self._target(j)
                        if a is None:
                            break
                        tab.append(j)
                        if a > k:
                            lim = min(lim, a)
                        j += 2
                    if not tab:
                        raise ScriptError("an empty switch at %x" % k)
                    self.ops[k] = (op, j - k)
                    for t in tab:
                        self.addrs.add(t)
                        labels.add(self._target(t))
                        todo.append(self._target(t))
                    break
                raise ScriptError("op %02x at %x" % (op, k))
        return len(self.ops) - n0

    def covered(self):
        cov = bytearray(len(self.d))
        for k, (_op, n) in self.ops.items():
            cov[k:k + n] = b"\1" * n
        for _kind, s, e in self.texts.values():
            cov[s:e + 1] = b"\1" * (e + 1 - s)
        return cov

    def messages(self):
        return sorted(v for v in self.texts.values() if v[0] == "msg")

    def items(self):
        return sorted(v for v in self.texts.values() if v[0] == "item")


def rebuild(sc, new):
    """The script with new texts ({start: bytes without the 0}), every address field moved."""
    if sc.code:
        return tramp(sc, new)
    d = sc.d
    spans = sorted((s, e) for s, (_k, s2, e) in sc.texts.items() for s in [s2] if s in new)
    out, at, starts = bytearray(), 0, []
    for s, e in spans:
        out += d[at:s]
        starts.append((s, e, len(out)))
        out += new[s] + b"\0"
        at = e + 1
    out += d[at:]

    def move(o):
        delta = 0
        for s, e, ns in starts:
            if o < s:
                break
            if o <= e:
                return ns + min(o - s, len(new[s]))
            delta = ns + len(new[s]) + 1 - (e + 1)
        return o + delta

    for a in sorted(sc.addrs):
        v = struct.unpack_from("<H", d, a)[0] - ORG
        struct.pack_into("<H", out, move(a), (move(v) + ORG) & 0xFFFF)
    if len(out) > ROOM:
        raise ScriptError("%d bytes, the room is %d" % (len(out), ROOM))
    return bytes(out)


def tramp(sc, new):
    """The script, its layout kept: a text that fits is written in place, a longer message's op becomes a
    goto to a message op after the end (going on where the original went), a longer item's address its
    English after the end."""
    out = bytearray(sc.d)
    item_at = {}
    for k, (op, _n) in sc.ops.items():
        if op in (0x02, 0x03):
            for j in range(ITEMS):
                if sc.w(k + 6 + 2 * j):
                    item_at.setdefault(sc.w(k + 6 + 2 * j) - ORG, []).append(k + 6 + 2 * j)
    for s, (kind, _s, e) in sorted(sc.texts.items()):
        if s not in new:
            continue
        b = new[s]
        if len(b) <= e - s:
            out[s:s + len(b) + 1] = b + b"\0"
            continue
        here = len(out)
        if kind == "msg":
            k = s - 3
            nxt = sc.w(k + 1)
            out += bytes([0x09]) + struct.pack("<H", nxt) + b + b"\0"
            out[k:k + 3] = b"\x04" + struct.pack("<H", here + ORG)
        else:
            out += b + b"\0"
            for a in item_at.get(s, ()):
                struct.pack_into("<H", out, a, here + ORG)
    if len(out) > ROOM:
        raise ScriptError("%d bytes, the room is %d" % (len(out), ROOM))
    return bytes(out)


# ---- text ----------------------------------------------------------------------------------------------------

def _cells(ch):
    return 2 if len(ch.encode("cp932", "replace")) == 2 else 1


def show(b, width=MSG_WIDTH):
    """A text as the window shows it: its lines (the routine's own breaks at the width), the full-width
    spaces that only pad a line out dropped."""
    t = bytes(b).decode("cp932", "replace")
    lines, cur, col = [], "", 0
    for ch in t:
        cur += ch
        col += _cells(ch)
        if col >= width:
            lines.append(cur)
            cur, col = "", 0
    if cur:
        lines.append(cur)
    return "\n".join(ln.rstrip("　") for ln in lines).rstrip("\n")


SPEAKER = re.compile(r"^(【[^】]{1,8}】)")


def layout(text, width, first=0, rows=MSG_LINES):
    """English lines (ASCII) for the window: broken between words at width cells (the first line after
    `first` cells); 02 between lines, but not after a line the routine breaks itself (a full one: an odd
    one's last letter takes a whole character); 01 (a key, the window cleared) after each `rows` lines,
    the routine going on down the screen by itself."""
    from .aypio import ascii_text
    from .text import wrap
    t = ascii_text(text)
    lines = wrap(t, width, width=len, first=width - first if first else None)
    out = b""
    for k, ln in enumerate(lines):
        b = ln.encode("ascii")
        out += b
        if k == len(lines) - 1:
            break
        cells = len(b) + (first if k == 0 else 0)
        if cells % 2:
            out += b" "             # (the pair's other half: the next line's letters start a pair)
            cells += 1
        if (k + 1) % rows == 0:
            out += b"\x01"
        elif cells < width:
            out += b"\x02"
    return out


# ---- the patch: ASCII two letters a character ----------------------------------------------------------------

ANK = re.compile(rb"\x8b\x04\x3c\x81\x72\x06\x3c\x9f\x77\x02\xeb.\x3c\xe0\x72\x06\x3c\xfc\x77\x02\xeb."
                 rb"(\xb4\x29\x3c\xa0)", re.S)
FULL = re.compile(rb"\x60\x57\x80\xec\x20\x8b\xd8\xb0\x0b\xe6\x68.{8}\xbb\x00\x20\x8c\xcf\x8e\xc7\xbf(..)\xbe\x10\x00",
                  re.S)
FULL_TAIL = re.compile(rb"\xb0\x0a\xe6\x68\x5a\x1e\x8c\xc8\x8e\xd8\xb0\x01\xb9\x00\xa8")
BOLD = re.compile(rb"\x2e\x80\x3e(..)\x00\x74", re.S)
# 01's wait: call (no key) ; call (a key) ; jmp (clear and go on) -- then popa / pop es / ret
PAGE_WAIT = re.compile(rb"\x75.(\xe8..\xe8..)\xeb.\x61\x07\xc3", re.S)

PAIR = """
pair:
    mov ax, word ptr [si]
    mov bx, ax
    mov cx, 2
    cmp bh, 0x20
    jb p_one
    cmp bh, 0x80
    jb p_go
p_one:
    mov bh, 0x20
    mov cx, 1
p_go:
    push cx
    CALLN draw2
    pop cx
    add si, cx
    .byte 0xc3
draw2:
    pusha
    push di
    mov al, 0x0b
    out 0x68, al
    mov di, {buf:#x}
    mov dl, bl
    CALLN rows
    mov di, {buf:#x} + 1
    mov dl, bh
    CALLN rows
    JMPN {tail:#x}
rows:
    mov al, dl
    out 0xa1, al
    mov al, 0x09
    out 0xa3, al
    mov ah, 0x20
    mov cx, 16
r_loop:
    mov al, ah
    out 0xa5, al
    in al, 0xa9
    cmp byte ptr cs:[{bold:#x}], 0
    je r_put
    push bx
    push cx
    mov bl, al
    shl bl, 1
    or al, bl
    mov cx, 6
r_bold:
    mov bh, bl
    and bh, 7
    cmp bh, 5
    jne r_keep
    and al, 0xfd
r_keep:
    shr bl, 1
    ror al, 1
    loop r_bold
    ror al, 2
    pop cx
    pop bx
r_put:
    mov byte ptr cs:[di], al
    add di, 2
    inc ah
    loop r_loop
    .byte 0xc3
"""


def patch_bios(bios):
    """MAKOBIOS.BIN with its one-byte characters drawn two to a 16-dot character (its own half-width
    path writes to no plane): the pair's glyphs read from the font's ANK row into the full-width
    routine's buffer, then its own coloured copy to the planes; the helper after the file's end (the
    memory up to MLF.BIN's segment is free)."""
    from .cocktail import _asm
    a, f, t = ANK.search(bios), FULL.search(bios), FULL_TAIL.search(bios)
    if not (a and f and t):
        raise ValueError("MAKOBIOS.BIN: the text routine is not laid out as expected")
    bolds = {struct.unpack("<H", m.group(1))[0] for m in BOLD.finditer(bios, f.start(), t.start())}
    if len(bolds) != 1:
        raise ValueError("MAKOBIOS.BIN: the bold flag is not found")
    org = len(bios) + (-len(bios) % 16)
    code, addr = _asm(PAIR.format(buf=struct.unpack("<H", f.group(1))[0], tail=t.start(), bold=bolds.pop()),
                      org, ["pair"])
    out = bytearray(bios) + b"\0" * (org - len(bios)) + code
    at = a.start(1)
    out[at:at + 4] = b"\xe9" + struct.pack("<H", (addr["pair"] - (at + 3)) & 0xFFFF) + b"\x90"
    # 01 waits for the key's release, then a key: the script's key wait after the message (a key, then
    # its release) took the same key; the game's own texts have no 01, the English's waits: a key, then
    # its release
    p = PAGE_WAIT.search(bios, a.end() - 0x200 if a.end() > 0x200 else 0, a.start())
    if not p:
        raise ValueError("MAKOBIOS.BIN: the page's wait is not found")
    c = p.start(1)
    no_key = c + 3 + struct.unpack_from("<h", bios, c + 1)[0]
    key = c + 6 + struct.unpack_from("<h", bios, c + 4)[0]
    out[c:c + 6] = (b"\xe8" + struct.pack("<H", (key - (c + 3)) & 0xFFFF)
                    + b"\xe8" + struct.pack("<H", (no_key - (c + 6)) & 0xFFFF))
    return bytes(out)
