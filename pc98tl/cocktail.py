"""Cocktail Soft's PC-98 versions of its PC-8801 games (Can Can Bunny): one self-booting 2HD floppy,
its program, its scripts, and English drawn half-width.

The disk: 1024-byte sectors, 8 a track, 154 tracks (a track's index is cylinder * 2 + head).  The boot
sector loads the program (`Disk.program`: the track and sector of `mov dx`, the size the dword at 40h)
to 0060:0000.  The program's first bytes call a stub at its end (`Program`): the stub decodes the bytes
before it (a word the seed, a word the count, after a short jump: each byte XORed with the high byte of
a running product, ax = ax * 37ABh + 31A1h) and puts back the program's first 3 bytes (kept after the
count), so the image on the disk holds everything encoded but the stub and what follows it.

The program is the PC-8801 game's Z80 code ported to x86 by machine, the 8080 world kept: each part runs
with a 64 KB segment as its 8080 memory, its data at the 8080 addresses.  The main part's segment
(`Program.ds`, set at the entry) is loaded with the program (`Program.ds_image`); the opening and the
ending (one part, entered at 0B27:0010 and 0B27:0000) run with their own (`Program.module_ds`).  The game
reads the PC-8801 files (`FILES`, in the table of the program the track, the sector and the size of each)
into these segments: the pictures, and the five girls' talks (CHR1KJ.COM-CHR5KJ.COM, the main part's
8080 address 3B00h).  The PC-8801 files MAIN.COM, USER.COM, GAME.COM, PROLOG.COM and ENDING.COM are on the
disk too; their texts are copies of the program's.

Text of the main part (`box_records`): a record is a header of two bytes, then Shift-JIS, then 0.  The
header's low nibble is a slot (the positions at 8080 182h, a word each: 0-6 the command panel's rows,
7 and 8 the message box's two lines), the high nibble a mode: 0 show, 2 clear the box and show, 3 clear
and show and go on with the next record, 1 show and go on after scrolling the box a line, E show, then
the next record (mode D) puts the player's entry its slot names (the name, the age...: 16 bytes at
2300h) and shows its own text after it; F a command.  The box (two lines of 50 cells) scrolls 13 rows a
step by a routine of the part (8BB8h for the talks, 2A05h for the rest).  Three loops of the main part
draw the bytes (MAIN's at 2E1Ch, the talks' at 92B9h, a one-byte one at 35B1h): two bytes a character
through the routine at 3696h, which reads the character's glyph with int 18h; the one-byte loop draws
bytes below 80h from the font's half-width row (29h) itself and takes 0Dh as a new line.

Text of the opening and the ending (`module_records`): a record is a header of 8 bytes (column, row
(14 dots a row), colour, width, four more), then two bytes a character up to 00 00: 00 0Ah a new line,
00 01-07h a colour, 00 08h colour 0, 00 20h a space; the part breaks a line by itself at the width.
Its own copy of the glyph routine (0B27:1F22h) is fed by a loop (0B27:1A42h) that converts the
Shift-JIS to JIS itself.

The patch (`patch_program`): a character of two ASCII bytes is drawn as their two half-width glyphs side
by side (the routines' glyph read: the bytes' 8x16 glyphs, interleaved into the 16x16 buffer); the
English is kept in a store (`store`) on the free tracks at the disk's end, loaded at the start into memory
the game does not use (segment `HSEG`), with the helpers in it; a translated text's first bytes become a
mark (a byte 10h-1Fh, the high bits of the English's index, then its low byte), the rest stays: each loop's
reads go through a helper that, on a mark, reads the English from the store, then goes on after the
original text's end.  In the English, 0Ah (in the main part) breaks the box's line (to the second line,
or scrolls it); in the opening's, 00 0Ch waits and clears the record's lines (more than its rows).
"""
import re
import struct

from .kuro import _asm16

SECTOR = 0x400
TRACK = 8 * SECTOR
TRACKS = 154
LOAD_SEG = 0x60             # the program's place (the boot sector's far jump)
HSEG = 0x5200               # the store's segment: memory above the program's, the disk's bounce buffer
STORE_TRACK = 124           # the first free track (E5h) after the program's
STORE_CHUNK = 0x8000        # bytes a read of the store (4 tracks)
MARK = range(0x10, 0x20)
BOX_WIDTH = 50              # the message box's cells (the scroll's 32h bytes)
NAME_CELLS = 14             # an entry the player made (as the command panel shows its choices)
MENU_CELLS = 14             # the command panel's (columns 64-77, inside its frame)
SCREEN_ROWS = 14            # rows of 14 dots in the 200 lines
MODULE_COLUMNS = 40         # the opening's columns of a character (the part's own limit)

# the files (the program's table: the track, the sector, the size of each, in this order)
FILES = ("MUSDRV.COM", "CANBG1.DAT", "CANBG2.DAT", "CANBG3.DAT", "CANBG4.DAT", "CANBG5.DAT", "CANBG6.DAT",
         "CANBG7.DAT", "CANBG8.DAT", "NIGHT.DAT", "BUNEAR.DAT", "BUNFLY.DAT", "BUNHND.DAT", "TITLE.DAT",
         "CHR1OP.DAT", "CHR2OP.DAT", "CHR3OP.DAT", "CHR4OP.DAT", "CHR5OP.DAT", "BUNNY1.DAT", "BUNNY2.DAT",
         "FLAME.DAT", "MYROOM.DAT", "NOTE.DAT", "SLTCHR.DAT", "SLTMAC.DAT", "SLTLUK.DAT", "ITEM.DAT",
         "CHR1AC.DAT", "CHR112.ANM", "CHR1D1.DAT", "CHR1D2.DAT", "CHR134.ANM", "CHR1D3.DAT", "CHR1D4.DAT",
         "CHR125.ANM", "CHR1D5.DAT", "CHR1D6.DAT", "CHR6AC.DAT", "CHR612.ANM", "CHR6D1.DAT", "CHR6D2.DAT",
         "CHR6D3.DAT", "CHR123.PET", "CHR145.PET", "CHR223.PET", "CHR245.PET", "CHR323.PET", "CHR345.PET",
         "CHR423.PET", "CHR445.PET", "CHR523.PET", "CHR545.PET", "DOOR1.DAT", "DOOR2.DAT", "DOOR3.DAT",
         "DOOR4.DAT", "DOOR5.DAT", "PROLOG.COM", "MAIN.COM", "GAME.COM", "USER.COM", "LOGO.DAT",
         "ENDING.COM", "CHR1KJ.COM", "CHR2KJ.COM", "CHR3KJ.COM", "CHR4KJ.COM", "CHR5KJ.COM")
TALKS = ("CHR1KJ.COM", "CHR2KJ.COM", "CHR3KJ.COM", "CHR4KJ.COM", "CHR5KJ.COM")
TALK_BASE = 0x3B00          # the talks' 8080 address
COPIES = ("MAIN.COM", "USER.COM", "GAME.COM", "PROLOG.COM", "ENDING.COM")
SAVE = (0, 7)               # the saved games (track, sector): two of 256 bytes, read to 5B00h
ENTRIES = 7                 # a game's or USER.COM's (the defaults) entries: 16 bytes each, then FFh

BOOT_SIG = re.compile(rb"\xba(.)(.)\x2e\x8b\x0e(..)\x2e\x8b\x1e(..)", re.S)
ENTRY_SIG = re.compile(rb"\xb8(..)\x8e\xd8\x8e\xc0\xe8(..)", re.S)      # mov ax, DS; ds, es; call init
STUB_SIG = re.compile(rb"\xeb.(..)(..)(...)(?:.){0,3}?\xfa\x8c\xc8\x8e\xd0", re.S)
CRYPT_SIG = re.compile(rb"\xbb(..)\x8b\x0e..\x2b\xff\xf7\xe3\x05(..)\x30\x15", re.S)
FILE_TABLE_SIG = re.compile(rb"\x01\x02..\x05\x02..\x07\x02", re.S)     # MUSDRV.COM's, CANBG1.DAT's...
MODULE_SIG = re.compile(rb"\x9a\x10\x00(..)", re.S)                     # call far <module>:0010 (the opening)
MODULE_DS_SIG = re.compile(rb"\xb8(..)\x8e\xc0\x8e\xd8\x2e\xc6\x06", re.S)


class Disk:
    def __init__(self, raw):
        if len(raw) != TRACKS * TRACK:
            raise ValueError("not a 2HD floppy of 1024-byte sectors (%d bytes)" % len(raw))
        self.raw = bytearray(raw)

    @staticmethod
    def at(track, sector):
        return track * TRACK + (sector - 1) * SECTOR

    def program(self):
        m = BOOT_SIG.search(bytes(self.raw[:SECTOR]))
        if not m:
            raise ValueError("the boot sector's load is not found")
        track, sector = m.group(2)[0], m.group(1)[0]
        lo, hi = struct.unpack("<HH", m.group(3) + m.group(4))
        # (the sector runs from 1FC0h:0000 a copy of itself from the segment its first mov sets)
        c = re.match(rb"\xb8(..)\x8e\xd8", bytes(self.raw[:5]), re.S)
        if hi != lo + 2 or not c:
            raise ValueError("the boot sector's size is not laid out as expected")
        size = struct.unpack_from("<I", self.raw, lo + (struct.unpack("<H", c.group(1))[0] - 0x1FC0) * 16)[0]
        return self.at(track, sector), size


def crypt(data, seed, count, mul, add):
    ax = seed
    for i in range(count):
        p = ax * mul
        ax = (p + add) & 0xFFFF
        data[i] ^= (p >> 16) & 0xFF


class Program:
    """The program, decoded (`d`), with its parts' places."""

    def __init__(self, disk):
        self.disk = disk
        self.at, self.size = disk.program()
        raw = bytes(disk.raw[self.at:self.at + self.size])
        if raw[0] != 0xE8:
            raise ValueError("the program does not start with its stub's call")
        self.stub = 3 + struct.unpack_from("<H", raw, 1)[0]
        m = STUB_SIG.match(raw, self.stub)
        c = CRYPT_SIG.search(raw, self.stub)
        if not m or not c:
            raise ValueError("the program's decoding stub is not laid out as expected")
        self.seed, self.count = struct.unpack("<HH", m.group(1) + m.group(2))
        self.mul, self.add = struct.unpack("<HH", c.group(1) + c.group(2))
        self.head = raw[:3]
        d = bytearray(raw)
        crypt(d, self.seed, self.count, self.mul, self.add)
        d[0:3] = m.group(3)
        self.d = d
        e = ENTRY_SIG.search(bytes(d[:0x40]))
        if not e:
            raise ValueError("the program's entry is not laid out as expected")
        self.ds = struct.unpack("<H", e.group(1))[0]
        self.init_call = e.start() + 7
        self.ds_at = self.ds * 16 - LOAD_SEG * 16
        mo = MODULE_SIG.search(bytes(d[:0x80]))
        self.module = struct.unpack("<H", mo.group(1))[0]
        self.module_at = self.module * 16 - LOAD_SEG * 16
        md = MODULE_DS_SIG.match(bytes(d), self.module_at)
        if not md:
            raise ValueError("the opening's segment is not laid out as expected")
        self.module_ds = struct.unpack("<H", md.group(1))[0]
        self.module_ds_at = self.module_ds * 16 - LOAD_SEG * 16

    def encoded(self):
        out = bytearray(self.d)
        crypt(out, self.seed, self.count, self.mul, self.add)
        out[0:3] = self.head
        return out

    def ds_image(self):
        return self.d[self.ds_at:self.ds_at + 0x10000]

    def module_image(self):
        return self.d[self.module_ds_at:self.module_ds_at + 0x10000]

    def files(self):
        """{name: (disk offset, size)} from the program's table."""
        found = list(FILE_TABLE_SIG.finditer(bytes(self.d[:self.count])))
        if len(found) != 1:
            raise ValueError("the files' table is found %d times, not once" % len(found))
        at, out = found[0].start(), {}
        for k, name in enumerate(FILES):
            dx, n = struct.unpack_from("<HH", self.d, at + 4 * k)
            out[name] = (Disk.at(dx >> 8, dx & 0xFF), n)
        return out


# ---- text --------------------------------------------------------------------------------------------------

def _sjis(b, k):
    return k + 1 < len(b) and (0x81 <= b[k] <= 0x9F or 0xE0 <= b[k] <= 0xEF) and 0x40 <= b[k + 1] <= 0xFC


def _text_end(b, k):
    """The 0 after Shift-JIS from k, or -1."""
    s = k
    while _sjis(b, k):
        k += 2
    return k if k > s and k < len(b) and b[k] == 0 else -1


BOX_MODES = (0x0, 0x1, 0x2, 0x3, 0xD, 0xE, 0xF)


class Record:
    __slots__ = ("at", "mode", "slot", "text", "end")

    def __init__(self, at, mode, slot, text, end):
        self.at, self.mode, self.slot, self.text, self.end = at, mode, slot, text, end

    def __repr__(self):
        return "Record(%x, %x/%x)" % (self.at, self.mode, self.slot)


def _box_record(b, at):
    if at + 3 > len(b):
        return None
    mode, slot = b[at] >> 4, b[at] & 15
    if mode not in BOX_MODES or slot > 8:
        return None
    e = _text_end(b, at + 2)
    return Record(at, mode, slot, at + 2, e) if e > 0 else None


def box_records(b, base):
    """[Record] of a main-part image whose 8080 address is base: the records a word points at, the
    records after a 0 the program's code points at (with kana or kanji), and the records right after
    those (a chain, a list), less those inside another's text; and the plain texts (no header: mode
    None) a word points at after a 0 (the player's entries' choices)."""
    b = bytes(b)
    cand = set()
    for i in range(len(b) - 1):
        v = struct.unpack_from("<H", b, i)[0] - base
        if 0 <= v < len(b):
            cand.add(v)
    loose = {k for k in range(1, len(b) - 3) if b[k - 1] == 0 and b[k] >> 4 in BOX_MODES}
    found = {}
    for v in sorted(cand | loose):
        r = _box_record(b, v)
        if r is None or (v not in cand and not KANA.search(show(b[r.text:r.end]))):
            continue
        while r is not None and r.at not in found:
            found[r.at] = r
            r = _box_record(b, r.end + 1)
    # (a table: two words or more in a row, each at a text)
    plain = {}
    for i in range(len(b) - 1):
        v = struct.unpack_from("<H", b, i)[0] - base
        e = _text_end(b, v) if 0 <= v < len(b) else -1
        if e > 0 and JAPANESE.search(show(b[v:e])):
            plain[i] = (v, e)
    for i, (v, e) in plain.items():
        if (i + 2 in plain or i - 2 in plain) and v not in found:
            found[v] = Record(v, None, None, v, e)
    out, last = [], -1
    for at in sorted(found):
        r = found[at]
        if at <= last:
            continue
        t = show(b[r.text:r.end])
        if "�" in t or (not JAPANESE.search(t) and r.mode != 0xE):
            continue
        out.append(r)
        last = r.end
    return out


KANA = re.compile(r"[ぁ-ヶ一-鿿々]")
JAPANESE = re.compile(r"[ぁ-ヶ一-鿿々〇ー～☆、。・！？Ａ-Ｚａ-ｚ０-９]")


def show(b):
    """Shift-JIS bytes as text."""
    return bytes(b).decode("cp932", "replace")


class ModuleRecord:
    __slots__ = ("at", "x", "y", "colour", "width", "text", "end")

    def __init__(self, at, x, y, colour, width, text, end):
        self.at, self.x, self.y, self.colour, self.width, self.text, self.end = at, x, y, colour, width, text, end

    def limit(self):
        return min(self.x + self.width - 1, MODULE_COLUMNS - 1) + 1

    def cells(self):
        return 2 * (self.limit() - self.x)

    def rows(self):
        return SCREEN_ROWS - self.y


def module_records(b):
    """[ModuleRecord] of the opening's segment: two-byte units (Shift-JIS, or 00 and a control) up to
    00 00, two Japanese characters at least, after an 8-byte header."""
    b = bytes(b)
    out, k = [], 8
    while k < len(b) - 1:
        if not _sjis(b, k):
            k += 1
            continue
        s, n = k, 0
        while k < len(b) - 1 and (_sjis(b, k) or (b[k] == 0 and 0 < b[k + 1] < 0x21)):
            n += _sjis(b, k)
            k += 2
        if b[k:k + 2] == b"\0\0" and n >= 2:
            h = b[s - 8:s]
            if h[0] < MODULE_COLUMNS and h[1] < SCREEN_ROWS and h[3]:
                out.append(ModuleRecord(s - 8, h[0], h[1], h[2], h[3], s, k))
    return out


def module_show(b):
    """A module record's units as text: \\n a new line, {Cn} a colour, a space."""
    out, k = [], 0
    while k < len(b) - 1:
        if b[k] == 0:
            c = b[k + 1]
            out.append("\n" if c == 0x0A else " " if c == 0x20 else "{C%d}" % (0 if c == 8 else c))
        else:
            out.append(show(b[k:k + 2]))
        k += 2
    return "".join(out)


def units(records):
    """[[Record]]: what the box shows together.  A unit starts at a record of the box's first line (slot
    7) or the player's entry (mode E), or a panel's; the box's second line (slot 8) and an entry's text
    (mode D) join the unit before them when that one is the box's."""
    out = []
    for r in records:
        u = out[-1] if out else None
        joins = False
        if u and u[0].mode is not None and u[0].slot in (7, 8) and u[-1].end + 1 == r.at and r.mode is not None:
            last = u[-1]
            first_line = last.slot == 7 if last.mode != 0xD else len(u) > 1 and u[-2].slot == 7
            joins = ((last.mode in (1, 3) and r.mode not in (2, 3))         # the chain goes on
                     or (last.mode == 0xE and r.mode == 0xD)                 # the entry's text
                     or (first_line and r.slot == 8 and r.mode not in (2, 3)))    # the second line
        if joins:
            u.append(r)
        else:
            out.append([r])
    return out


# ---- English --------------------------------------------------------------------------------------------------

NAME_TOKEN = re.compile(r"\{N(\d)\}")
COLOUR_TOKEN = re.compile(r"\{C(\d)\}")


def ascii_line(text):
    from .aypio import ascii_text
    return ascii_text(text).replace("\n", " ")


def _wrap(items, width, first=0):
    """items: words (str), " " and "\n", and names ((k,)): [[item]] lines of at most width cells (a name
    NAME_CELLS), the first starting at column first."""
    def cells(x):
        return NAME_CELLS if isinstance(x, tuple) else len(x)
    lines, cur, col = [], [], first
    for x in items:
        if x == "\n":
            lines.append(cur)
            cur, col = [], 0
            continue
        if x == " ":
            if cur:
                cur.append(x)
                col += 1
            continue
        w = cells(x)
        if col + w > width and any(y != " " for y in cur):
            while cur and cur[-1] == " ":
                cur.pop()
            lines.append(cur)
            cur, col = [], 0
        while not isinstance(x, tuple) and len(x) > width:      # a word longer than a line
            cut = width - col
            cur.append(x[:cut])
            lines.append(cur)
            cur, col, x = [], 0, x[cut:]
        cur.append(x)
        col += cells(x)
    while cur and cur[-1] == " ":
        cur.pop()
    lines.append(cur)
    return lines


def _items(text):
    out = []
    for part in re.split(r"(\{N\d\}|\n| )", text):
        if not part:
            continue
        m = NAME_TOKEN.fullmatch(part)
        out.append((int(m.group(1)),) if m else part if part in ("\n", " ") else ascii_line(part))
    return out


def _even(b):
    return b + b" " if len(b) % 2 else b


def box_english(unit, text, ident, warn):
    """{record's place: English bytes} for a unit of the box (`units`): the lines (50 cells; a name the
    player made NAME_CELLS) one a record (an entry's record the text before its name, the entry's own
    record what follows it on that line), the last record the rest, its lines broken by 0Ah (the helper:
    the box's second line, or a scroll)."""
    lines = _wrap(_items(text.strip("\n")), BOX_WIDTH)
    stream = []                     # str pieces, "\n", and names
    for k, ln in enumerate(lines):
        if k:
            stream.append("\n")
        stream += ln
    out, pos = {}, 0
    for i, r in enumerate(unit):
        last = i == len(unit) - 1
        nxt = unit[i + 1] if not last else None
        if i and r.mode != 0xD and pos < len(stream) and stream[pos] == "\n":
            pos += 1                # (the record's slot is the next line)
        seg = []
        while pos < len(stream):
            x = stream[pos]
            if isinstance(x, tuple):
                if nxt is not None and nxt.mode == 0xD:
                    pos += 1        # (the program puts the entry)
                    break
                warn.append("%s: {N%d} where the program puts no entry" % (ident, x[0]))
                pos += 1
                continue
            if x == "\n" and not last and r.mode != 0xE:
                break
            seg.append(x)
            pos += 1
        if r.mode == 0xE and not (pos and isinstance(stream[pos - 1], tuple)):
            warn.append("%s: no {N%d}: the entry follows the text" % (ident, nxt.slot if nxt else 0))
        b = b""
        for x in seg:
            b = _even(b) + b"\n" if x == "\n" else b + x.encode("ascii")
        out[r.at] = _even(b)
    return out


def line_english(text, room, ident, warn):
    b = ascii_line(text).encode("ascii")
    if len(b) > room:
        warn.append("%s: %d letters, room for %d" % (ident, len(b), room))
    return _even(b)


def page_english(rec, text, centred, rows, ident, warn):
    """(English units, new header bytes x, y) of an opening's record: lines of the record's width (a line
    centred again if the Japanese was), rows a page (the Japanese's: the picture beside it may take the
    rest), 00 0Ch between pages."""
    items = []
    for part in re.split(r"(\{C\d\}|\n| )", text.strip("\n")):
        if part:
            m = COLOUR_TOKEN.fullmatch(part)
            items.append(m.group(0) if m else part if part in ("\n", " ") else ascii_line(part))
    width = rec.cells()
    x, y, rows = rec.x, rec.y, max(1, min(rows, rec.rows()))
    lines = _wrap(items_for_wrap(items), width)
    if centred:
        widest = max(_cells(ln) for ln in lines)
        x = max(0, (MODULE_COLUMNS - (widest + 1) // 2) // 2)
        width = 2 * (rec.limit() - x)
        lines = _wrap(items_for_wrap(items), width)
    pages = [lines[k:k + rows] for k in range(0, len(lines), rows)]
    if len(pages) > 1:
        warn.append("%s: %d lines, %d a page: shown in %d pages" % (ident, len(lines), rows, len(pages)))
    out = b""
    for n, page in enumerate(pages):
        if n:
            out += b"\0\x0c"
        for k, ln in enumerate(page):
            if k:
                out += b"\0\x0a"
            b = b""
            for t in ln:
                m = COLOUR_TOKEN.fullmatch(t) if isinstance(t, str) else None
                if m:
                    c = int(m.group(1))
                    b = _even(b) + bytes([0, c or 8])
                else:
                    b += t.encode("ascii")
            out += _even(b)
    return out + b"\0\0", x, y


def items_for_wrap(items):
    # colours take no cells: kept as words of no width
    return [_Colour(x) if COLOUR_TOKEN.fullmatch(x) else x for x in items]


class _Colour(str):
    def __len__(self):
        return 0


def _cells(ln):
    return sum(NAME_CELLS if isinstance(t, tuple) else len(t) for t in ln)


# ---- the patch ------------------------------------------------------------------------------------------------

def _asm(src, org, want=()):
    """keystone, with CALLN/JMPN <label or 0x-address> (near, 3 bytes) and FAR <seg>:<off> (a far call)."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    lines, fix = [], []
    for line in src.split("\n"):
        t = line.strip()
        if t.startswith(("CALLN ", "JMPN ")):
            tag = "__fix%d" % len(fix)
            fix.append((tag, 0xE8 if t.startswith("CALLN") else 0xE9, t.split()[1]))
            lines += [tag + ":", "nop", "nop", "nop"]
        elif t.startswith("FAR "):
            seg, off = t.split()[1].split(":")
            lines += [".byte 0x9a", ".word %s" % off, ".word %s" % seg]
        else:
            lines.append(line)
    names = list(dict.fromkeys(list(want) + [f[0] for f in fix] + [f[2] for f in fix if not f[2].startswith("0x")]))
    full = bytes(Ks(KS_ARCH_X86, KS_MODE_16).asm("\n".join(lines) + "\n" + "\n".join(".word %s" % n for n in names),
                                                org)[0])
    code = bytearray(full[:len(full) - 2 * len(names)])
    addr = {n: int.from_bytes(full[len(code) + 2 * i:len(code) + 2 * i + 2], "little") for i, n in enumerate(names)}
    for tag, op, target in fix:
        t = int(target, 16) if target.startswith("0x") else addr[target]
        at = addr[tag] - org
        code[at:at + 3] = bytes([op]) + ((t - (addr[tag] + 3)) & 0xFFFF).to_bytes(2, "little")
    for ins in Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(code), org):
        if ins.bytes[0] == 0x66:
            raise ValueError("a 32-bit prefix in a helper at %x" % ins.address)
    return bytes(code), addr


FIRST = re.compile(rb"\x87\xcb\x8a\x07\x87\xcb\x41\x89\x0e\x3c\x00\x0a\xc0\x75\x01\xc3\x3c\x0d\x75")
SECOND = re.compile(rb"\x8a\xf0(\x87\xcb\x8a\x07\x87\xcb\x41)\x8a\xd0\x51\xe8(..)", re.S)
ONE_FIRST = re.compile(rb"\x87\xd9\x8a\x07\x87\xd9\x41\x0a\xc0\x74")
ONE_SECOND = re.compile(rb"\x8a\xf0(\x87\xcb\x8a\x07\x87\xcb\x41)\x8a\xd0\xe8")
POS_READ = re.compile(rb"\x8b\x1e(..)\x81\xeb\x00\xc0\xe8", re.S)          # mov bx, [pos]; sub bx, C000h; call
POS_TABLE = re.compile(rb"\xb9(..)\x03\xd9\x8a\x17", re.S)                  # mov cx, table; add bx, cx; mov dl, [bx]
SCROLL = re.compile(rb"\x32\xc0\xa2(..)\xbb\x32\x00\x89\x1e..\x32\xc0\xb0\x90\xbb\x88\xf4", re.S)
SYNC = re.compile(rb"\x50\x53\x51\x52\x55\x57\x56\x1e\x06\xe8..\x07\x1f\x5e\x5f\x5d\x5a\x59\x5b\x58", re.S)
SCROLL_PARAM = re.compile(rb"\xa0(..)\x8a\xe8", re.S)
GLYPH = re.compile(rb"\x53\xe8(..)\x52\x53\x8c\xdb\xb9(..)\xb4\x14\xfa\xcd\x18(\x2e\xc7\x06....)", re.S)
READ = re.compile(rb"\x55\x50\x53\x51\x2e\xa2..\x8b\xe9\xe3", re.S)
M_FETCH = re.compile(rb"\x2e\x8b\x1e..(\x8a\x37\x43\x8a\x07\x8a\xd0\x43)\x87\x06\x00\x00\x8a\xc6\x3c\xa0", re.S)
M_CONV_END = re.compile(rb"\x8a\xd0\x87\x06\x00\x00\x2e\x89")
M_GLYPH = re.compile(rb"\x53\x52\x53\x8c\xdb\xb9(..)\xb4\x14\xcd\x18(\x2e\xc7\x06....)", re.S)
M_LIMIT = re.compile(rb"\x2e\x3a\x06(..)", re.S)                            # cmp al, cs:[limit] (the column's)
STUB_SP = re.compile(rb"\x8e\xd0\xbc(..)", re.S)

DATA = 0x40                 # the helpers' variables and the glyph buffer, before their code
FRAMES = 170                # a page of the opening shown (about 3 s), or a key


def _one(rx, d, what, start=0, end=None):
    found = list(rx.finditer(d, start, len(d) if end is None else end))
    if len(found) != 1:
        raise ValueError("%s: its signature is found %d times, not once" % (what, len(found)))
    return found[0]


def _w(b):
    return struct.unpack("<H", b)[0]


def _sites(prog):
    """The places the patch changes, found by their bytes."""
    d = bytes(prog.d[:prog.count])
    s, loops = {}, {}
    for m in FIRST.finditer(d):
        sec = SECOND.search(d, m.end(), m.end() + 0x60)
        if not sec:
            raise ValueError("a text loop's second read is not found")
        draw = sec.end() + _w(sec.group(2))
        pos = POS_READ.search(d, draw, draw + 0x20)
        if not pos:
            raise ValueError("a text loop's position is not found")
        loops[_w(pos.group(1))] = (m.start(), sec.start(1))
    if len(loops) != 2:
        raise ValueError("the text loops are found %d times, not twice" % len(loops))
    (s["main_pos"], s["main"]), (s["kj_pos"], s["kj"]) = sorted(loops.items())
    tables = [(m.start(), _w(m.group(1))) for m in POS_TABLE.finditer(d)]
    for name in ("main", "kj"):
        near = s[name][0]
        s[name + "_tab"] = max(t for t in tables if t[0] < near)[1]
        best = None
        for m in SCROLL.finditer(d):
            entry = m.start() - 21 if m.start() >= 21 and SYNC.match(d, m.start() - 21) else m.start()
            if best is None or abs(entry - near) < abs(best[0] - near):
                best = (entry, m)
        entry, m = best
        ps = [_w(x.group(1)) for x in SCROLL_PARAM.finditer(d, m.end(), m.end() + 0x40)][:2]
        if len(ps) != 2:
            raise ValueError("the %s scroll's counts are not found" % name)
        s[name + "_scroll"], s[name + "_flag"], s[name + "_p"] = entry, _w(m.group(1)), ps
    one = _one(ONE_FIRST, d, "the one-byte loop")
    s["one"] = (one.start(), _one(ONE_SECOND, d, "the one-byte loop's second read", one.end(),
                                  one.end() + 0x80).start(1))
    g = _one(GLYPH, d, "the glyph routine")
    s["glyph"] = (g.start(), g.end(), g.start() + 4 + _w(g.group(1)), _w(g.group(2)), g.group(3))
    reads = []
    for m in READ.finditer(d):              # (the read's and the write's: the read's sector call reads)
        c = re.compile(rb"\x2b\xeb\xe8(..)", re.S).search(d, m.end(), m.end() + 0x60)
        t = c.end() + _w(c.group(1)) if c else -1
        if c and b"\xb4\x56\xcd\x1b" in d[t:t + 0x40]:
            reads.append(m.start())
    if len(reads) != 1:
        raise ValueError("the disk read is found %d times, not once" % len(reads))
    s["read"] = reads[0]
    s["init"] = prog.init_call
    s["init_target"] = prog.init_call + 3 + _w(bytes(prog.d[prog.init_call + 1:prog.init_call + 3]))
    # the free place after the decoding stub (its stack below it)
    sp = _w(STUB_SP.search(bytes(prog.d), prog.stub).group(1))
    fill, end = prog.d[sp], sp
    while prog.d[end] == fill:
        end += 1
    s["pad"] = (sp + 0x10, end)
    # the opening's part
    md = bytes(prog.d)
    lo, hi = prog.module_at, prog.module_at + 0x10000
    f = _one(M_FETCH, md, "the opening's text read", lo, hi)
    conv = f.end() - 4
    ce = _one(M_CONV_END, md, "the opening's conversion's end", conv, conv + 0x40)
    mg = _one(M_GLYPH, md, "the opening's glyph routine", lo, hi)
    s["m_fetch"] = f.start(1) - lo
    s["m_conv"] = (conv - lo, ce.start() + 6 - lo)
    s["m_glyph"] = (mg.start() - lo, mg.end() - lo, _w(mg.group(1)), mg.group(2))
    s["m_limit"] = _w(_one(M_LIMIT, md, "the opening's column limit", lo, hi).group(1))
    return s


NEWLINE = """
nl_{v}:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov ax, word ptr [{pos:#x}]
    cmp ax, word ptr [{line2:#x}]
    jb nl_{v}_two
    mov al, byte ptr [{flag:#x}]
    push ax
    mov byte ptr [{p1:#x}], 0x0d
    mov byte ptr [{p2:#x}], 0x1b
    FAR {seg:#x}:{th:#x}
    pop ax
    mov byte ptr [{flag:#x}], al
nl_{v}_two:
    mov ax, word ptr [{line2:#x}]
    mov word ptr [{pos:#x}], ax
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    .byte 0xc3
"""

HELPERS = """
f1_main:
    mov byte ptr cs:[1], 0
    CALLN first
    .byte 0xcb
f1_kj:
    mov byte ptr cs:[1], 1
    CALLN first
    .byte 0xcb
f1_one:
    mov byte ptr cs:[1], 2
    CALLN first
    .byte 0xcb
f2:
    CALLN second
    .byte 0xcb
eread:
    push si
    push es
    les si, dword ptr cs:[2]
    mov al, byte ptr es:[si]
    inc si
    mov word ptr cs:[2], si
    pop es
    pop si
    .byte 0xc3
estart:
    push bx
    push dx
    push si
    mov si, ax
    shl si, 1
    shl si, 1
    add si, word ptr cs:[0x0c]
    mov ax, word ptr cs:[si]
    mov dx, word ptr cs:[si + 2]
    mov bx, ax
    and bx, 15
    mov word ptr cs:[2], bx
    shr dx, 1
    rcr ax, 1
    shr dx, 1
    rcr ax, 1
    shr dx, 1
    rcr ax, 1
    shr dx, 1
    rcr ax, 1
    add ax, {hseg:#x}
    mov word ptr cs:[4], ax
    mov byte ptr cs:[0], 1
    pop si
    pop dx
    pop bx
    .byte 0xc3
first:
    cmp byte ptr cs:[0], 0
    jne fi_eng
    push bx
    mov bx, cx
    mov al, byte ptr [bx]
    cmp al, {mark0:#x}
    jb fi_plain
    cmp al, {mark1:#x}
    jae fi_plain
    mov ah, al
    sub ah, {mark0:#x}
    mov al, byte ptr [bx + 1]
    add bx, 2
fi_scan:
    cmp byte ptr [bx], 0
    je fi_found
    inc bx
    jmp fi_scan
fi_found:
    inc bx
    mov word ptr cs:[6], bx
    pop bx
    CALLN estart
    jmp fi_eng
fi_plain:
    pop bx
    inc cx
    .byte 0xc3
fi_eng:
    CALLN eread
    or al, al
    jne fi_nz
    mov byte ptr cs:[0], 0
    mov cx, word ptr cs:[6]
    .byte 0xc3
fi_nz:
    cmp al, 0x0a
    jne fi_ret
    cmp byte ptr cs:[1], 1
    je fi_k
    ja fi_one
    CALLN nl_m
    jmp fi_eng
fi_k:
    CALLN nl_k
    jmp fi_eng
fi_one:
    mov al, 0x0d
fi_ret:
    .byte 0xc3
second:
    cmp byte ptr cs:[0], 0
    jne se_eng
    push bx
    mov bx, cx
    mov al, byte ptr [bx]
    pop bx
    inc cx
    .byte 0xc3
se_eng:
    CALLN eread
    .byte 0xc3
{newlines}
m_fetch:
    cmp byte ptr cs:[0], 0
    jne mf_eng
    mov dh, byte ptr [bx]
    cmp dh, {mark0:#x}
    jb mf_plain
    cmp dh, {mark1:#x}
    jae mf_plain
    mov ah, dh
    sub ah, {mark0:#x}
    mov al, byte ptr [bx + 1]
    push bx
    add bx, 2
mf_scan:
    cmp word ptr [bx], 0
    je mf_found
    add bx, 2
    jmp mf_scan
mf_found:
    add bx, 2
    mov word ptr cs:[6], bx
    pop bx
    CALLN estart
    mov ax, word ptr [0x40]
    mov word ptr cs:[8], ax
    mov al, byte ptr [0x3e]
    mov byte ptr cs:[0x0a], al
    jmp mf_eng
mf_plain:
    inc bx
    mov al, byte ptr [bx]
    mov dl, al
    inc bx
    .byte 0xcb
mf_eng:
    CALLN eread
    mov dh, al
    CALLN eread
    mov dl, al
    or dh, dh
    jne mf_ret
    or dl, dl
    jne mf_ctl
    mov byte ptr cs:[0], 0
    mov bx, word ptr cs:[6]
    .byte 0xcb
mf_ctl:
    cmp dl, 0x0c
    jne mf_ret
    CALLN m_page
    jmp mf_eng
mf_ret:
    mov al, dl
    .byte 0xcb
m_conv:
    mov al, dl
    or dh, dh
    je mc_ret
    cmp dh, 0x80
    jae mc_sj
    or dh, 0x80
    mov al, 0x41
mc_ret:
    .byte 0xcb
mc_sj:
    push ax
    mov al, dh
    cmp al, 0xa0
    jae mc_e0
    sub al, 0x81
    add al, al
    add al, 0x21
    jmp mc_lo
mc_e0:
    sub al, 0xe0
    add al, al
    add al, 0x5f
mc_lo:
    mov dh, al
    mov al, dl
    cmp al, 0x9f
    jb mc_80
    sub al, 0x7e
    inc dh
    jmp mc_dl
mc_80:
    cmp al, 0x80
    jb mc_1f
    sub al, 0x20
    jmp mc_dl
mc_1f:
    sub al, 0x1f
mc_dl:
    mov dl, al
    pop ax
    .byte 0xcb
m_page:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
mp_flush:
    mov ah, 1
    int 0x18
    or bh, bh
    je mp_wait
    mov ah, 0
    int 0x18
    jmp mp_flush
mp_wait:
    mov cx, {frames}
mp_v1:
    in al, 0x60
    test al, 0x20
    jne mp_v1
mp_v2:
    in al, 0x60
    test al, 0x20
    je mp_v2
    push cx
    mov ah, 1
    int 0x18
    pop cx
    or bh, bh
    jne mp_key
    loop mp_v1
    jmp mp_clear
mp_key:
    mov ah, 0
    int 0x18
mp_clear:
    mov ax, word ptr [0x42]
    sub ax, word ptr cs:[8]
    mov bl, 80
    div bl
    xor ah, ah
    add ax, 14
    mov dx, ax
    mov ax, {module:#x}
    mov es, ax
    mov al, byte ptr es:[{limit:#x}]
    sub al, byte ptr [0x3f]
    xor ah, ah
    shl ax, 1
    mov bp, ax
    mov si, word ptr cs:[8]
    sub si, 0xc000
    mov bx, 0xa800
    CALLN mp_plane
    mov bx, 0xb000
    CALLN mp_plane
    mov bx, 0xb800
    CALLN mp_plane
    mov bx, 0xe000
    CALLN mp_plane
    mov ax, word ptr cs:[8]
    mov word ptr [0x40], ax
    mov word ptr [0x42], ax
    mov al, byte ptr cs:[0x0a]
    mov byte ptr [0x3e], al
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    .byte 0xc3
mp_plane:
    mov es, bx
    mov di, si
    push dx
mp_row:
    mov cx, bp
    xor al, al
    push di
    rep stosb
    pop di
    add di, 80
    dec dx
    jne mp_row
    pop dx
    .byte 0xc3
glyphf:
    CALLN glyph
    .byte 0xcb
glyph:
    cmp dh, 0x80
    jae g_ank
    push bx
    mov bx, ds
    mov ah, 0x14
    pushf
    cli
    int 0x18
    popf
    pop bx
    .byte 0xc3
g_ank:
    push si
    push di
    push es
    push ds
    pop es
    mov di, cx
    add di, 2
    mov al, dh
    and al, 0x7f
    CALLN g_one
    mov di, cx
    add di, 3
    mov al, dl
    CALLN g_one
    pop es
    pop di
    pop si
    .byte 0xc3
g_one:
    push bx
    push cx
    push dx
    push ds
    mov dh, 0x80
    mov dl, al
    mov bx, cs
    mov cx, {buf:#x}
    mov ah, 0x14
    int 0x18
    pop ds
    pop dx
    pop cx
    pop bx
    mov si, {buf:#x} + 2
    push cx
    mov cx, 16
g_row:
    mov al, byte ptr cs:[si]
    mov byte ptr es:[di], al
    inc si
    add di, 2
    loop g_row
    pop cx
    .byte 0xc3
"""

STUBS = """
init:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push ds
    push es
    mov bx, {chunks}
    mov ax, {hseg:#x}
    mov dh, {track}
i_next:
    push bx
    push ax
    push dx
    mov es, ax
    xor di, di
    mov dl, 1
    mov cx, {chunk:#x}
    mov al, 0
    CALLN {read:#x}
    pop dx
    pop ax
    pop bx
    add ax, {paras:#x}
    add dh, {tracks}
    dec bx
    jne i_next
    pop es
    pop ds
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    JMPN {target:#x}
th_main:
    CALLN {sm:#x}
    .byte 0xcb
th_kj:
    CALLN {sk:#x}
    .byte 0xcb
conv:
    cmp dh, 0x80
    jae c_sj
    or dh, 0x80
    .byte 0xc3
c_sj:
    JMPN {conv:#x}
"""
GLYPH_BUF = 0x10            # (in the helpers' segment: the ANK glyph read, 2 + 16 bytes)


def _far(off):
    return b"\x9a" + struct.pack("<HH", off, HSEG)


def patch_program(prog, store):
    """Hook the program (prog.d) for English; store: [English bytes] by index.  Returns the store's
    image (the helpers, the index table, the English), to be written at STORE_TRACK."""
    s = _sites(prog)
    if len(store) > len(MARK) * 256:
        raise ValueError("%d English texts; the marks hold %d" % (len(store), len(MARK) * 256))
    pad, pad_end = s["pad"]
    stub_args = dict(hseg=HSEG, track=STORE_TRACK, chunk=STORE_CHUNK, read=s["read"], paras=STORE_CHUNK // 16,
                     tracks=STORE_CHUNK // TRACK, target=s["init_target"], sm=s["main_scroll"],
                     sk=s["kj_scroll"], conv=s["glyph"][2])
    _probe, st = _asm(STUBS.format(chunks=1, **stub_args), pad, ["init", "th_main", "th_kj", "conv"])
    nl = "".join(NEWLINE.format(v=v, pos=s[n + "_pos"], line2=s[n + "_tab"] + 16, flag=s[n + "_flag"],
                                p1=s[n + "_p"][0], p2=s[n + "_p"][1], seg=LOAD_SEG, th=st["th_" + n])
                 for v, n in (("m", "main"), ("k", "kj")))
    src = HELPERS.format(hseg=HSEG, newlines=nl, frames=FRAMES, module=prog.module, limit=s["m_limit"],
                         mark0=MARK[0], mark1=MARK[-1] + 1, buf=GLYPH_BUF)
    code, h = _asm(src, DATA, ["f1_main", "f1_kj", "f1_one", "f2", "m_fetch", "m_conv", "glyphf"])
    table_at = DATA + len(code)
    table_at += -table_at % 4
    body = bytearray(table_at + 4 * len(store))
    body[DATA:DATA + len(code)] = code
    struct.pack_into("<H", body, 0x0C, table_at)
    for k, eng in enumerate(store):
        struct.pack_into("<I", body, table_at + 4 * k, len(body))
        body += eng + b"\0"
        body += b"\0" * (-len(body) % 16)
    room = (TRACKS - STORE_TRACK) * TRACK
    if len(body) > room:
        raise ValueError("the English store is %d bytes; the free tracks hold %d" % (len(body), room))
    stub, st = _asm(STUBS.format(chunks=-(-len(body) // STORE_CHUNK), **stub_args), pad,
                    ["init", "th_main", "th_kj", "conv"])
    if pad + len(stub) > pad_end:
        raise ValueError("the program's free place holds %d bytes, the stubs take %d" % (pad_end - pad, len(stub)))
    d = prog.d
    d[pad:pad + len(stub)] = stub
    at = s["init"]
    d[at:at + 3] = b"\xe8" + struct.pack("<H", (st["init"] - (at + 3)) & 0xFFFF)
    for (a, b), f1 in ((s["main"], "f1_main"), (s["kj"], "f1_kj"), (s["one"], "f1_one")):
        d[a:a + 7] = _far(h[f1]) + b"\x90\x90"
        d[b:b + 7] = _far(h["f2"]) + b"\x90\x90"
    g0, g1, _conv, buf, tail = s["glyph"]
    new = b"\x53\xe8" + struct.pack("<H", (st["conv"] - (g0 + 4)) & 0xFFFF) + b"\x52\x53\xb9" + struct.pack("<H", buf)
    d[g0:g1] = (new + _far(h["glyphf"]) + tail).ljust(g1 - g0, b"\x90")
    base = prog.module_at
    a = base + s["m_fetch"]
    d[a:a + 8] = _far(h["m_fetch"]) + b"\x90\x90\x90"
    c0, c1 = s["m_conv"]
    d[base + c0:base + c0 + 8] = _far(h["m_conv"]) + b"\xe9" + struct.pack("<H", (c1 - (c0 + 8)) & 0xFFFF)
    m0, m1, mbuf, mtail = s["m_glyph"]
    new = b"\x53\x52\x53\xb9" + struct.pack("<H", mbuf) + _far(h["glyphf"]) + mtail
    d[base + m0:base + m1] = new.ljust(m1 - m0, b"\x90")
    return bytes(body)


def mark(index):
    return bytes([MARK[0] + (index >> 8), index & 0xFF])
