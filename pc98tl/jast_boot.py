"""JAST family-C games: self-booting 2HD floppies with no file system
(Tenshi-tachi no Gogo IV - Yuko, Tenshi-tachi no Gogo III Bangaihen,
Gomen ne Angel, Yoru no Tenshi-tachi): extract/patch driver.  The builds
differ in details found by signature: text in Shift-JIS or (the oldest)
JIS words (see Codec), a line mark or wrapping only, a put routine that
moves the column or leaves it to the caller.  The JIS build also draws a
few Japanese engine strings (its title's sound prompt), rewritten in place.

Disk layout.  The boot sector loads the engine (hand-written assembly) from
logical sector 8 onwards and jumps to it.  The engine keeps its own reload
code ("b8 08 00 bd <offset> b9 <count> ... int 3"), which gives the offset
the engine runs at in its segment.  Everything else is found through four
directory tables in the engine (graphics, animation, scenes, music), one
4-byte entry per file: disk number (1 = the boot disk), then 24 bits with
the logical sector (1 KB sectors, 8 per track side) in the low 12 and the
sector count in the high 12.  The menu words are one more file, loaded by a
fixed call (address, sector, count): a header of table offsets, two tables
of 16-byte words (verbs, nouns) and, where the header has a fourth offset,
a list of system messages (e.g. "no need for that").

Scenes.  A scene file is command tables, then the messages from offset
4C + (word at 4A).  The engine reads a message two bytes at a time: a zero
word ends it, a word up to 2000h (little-endian) is an animation control,
anything else is a Shift-JIS character.  "－", "＋" and "±" only switch the
text colour (name, highlight, normal) and aren't drawn; "↓" starts a new
line.  A message is found by counting, so messages may change length.  The
disk tool that built the floppies left old sector contents after a file's
end and cut some files at a sector boundary: the leftovers are not listed
(see scene_messages), and a scene's cut-off last message is kept as it is.

Patch.
* Scenes are rebuilt with the English messages and written to free sectors
  of their disk (sectors that no table refers to and that hold one filler
  byte throughout: the format's E5, or the dump's gap byte 4E); their table
  entries are updated.  A scene must fit the engine's scene buffer (offset
  0 of the engine segment up to the word file); the patcher refuses one
  that would not.
* The menu words are rewritten in place (7 cells shown).  A word file with
  a message table is rebuilt with the English messages and loaded just
  below the engine (its load call updated), which gives the scene buffer the
  room the file leaves.
* Engine: the message draw and the menu draw call one character routine
  with the Shift-JIS code; both calls go to a helper that draws a code whose
  first byte is below 80h as two ASCII letters in two half-width text cells
  (the engine's own half-width put) and passes everything else on.  The line
  scrolls in the message draw go through a pager: at every third new line of
  a message it waits for a key or a left click first, so nothing scrolls out
  of the three-line box unread.  The helpers sit in the unused (zero) tail of
  the music table, which stays zero in a running game.

game.json: {"title", "key", "image", "encoding": "jast_boot",
            "floppies": {"B": "<disk 2 image>"}, "box_lines" (3), "dipsw", "boot_steps"}
A string's ref is "scene<n>:<message number>", "word<table>:<entry>" or
"words:<message number>".
"""
import json
import os
import re
import struct

from .alice_sys2_tl import sha256

SECTOR = 1024

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""

# the engine's reload code (kept in the engine, ends in int 3): sector 8, the
# offset in the engine's own segment, sector count.  (The boot sector's copy
# may load through another segment:offset pair for the same place.)
LOAD = re.compile(rb"\xb8(..)\xbd(..)\xb9(..)\xe8\x0a\x00\x72\x07\x40\x81\xc5\x00\x04\xe2\xf4\xcc", re.S)
# a directory lookup: si = table + 4 * index ... ax = [si+1], cl = [si+3]
TABLE = re.compile(rb"\xbe(..)[^\xbe]{2,8}?\x32\xe4\xd1\xe0\xd1\xe0\x03\xf0.{0,10}?\x8b\x44\x01\x8a\x4c\x03", re.S)
# the scene load: bp = 0 ... then si = 4C + [4A]
SCENE = re.compile(rb"\xbe(..)\xa0..\x32\xe4\xd1\xe0\xd1\xe0\x03\xf0\xbd\x00\x00\x8b\x44\x01.{20,60}?"
                   rb"(?:\xbe(.)\x00\x03\x74\xfe|\xbe\x4a\x00\xb8(.)\x00\x03\x04)", re.S)
# the word file load: bp = address, bx = sector, cx = count, then the three table offsets
WORDS = re.compile(rb"\xbd(..)\xbb(..)\xb9(..)\x33\xc0\xe8..(?:\x72.|\x73\x02\xeb.)\xbe(..)\x8b\x04\x03\xc6\xa3",
                   re.S)
# the message draw: start position, then the character loop
MSG_START = re.compile(rb"(?:\xba..\x89\x16..|\xb8..\xa3..)\x33\xc9"
                       rb"(?:\xc6\x06..\x00\xad\x0b\xc0|\x8b\x14\x46\x46\x0b\xd2)", re.S)
# (some builds' put leaves the column alone and the caller adds 2)
MSG_PUT = re.compile(rb"\x51\x8a\x0e..\x92?\xe8(..)(\xfe\xc0\xfe\xc0)?", re.S)
# the wrap: scroll, cursor back to the line start, column count 0
WRAP = re.compile(rb"\xe8(..)(?:\x8b\x16|\xa1)..\x33\xc9", re.S)
NEWLINE = re.compile(rb"\x3d\xab\x81\x75\x0b\xe8(..)", re.S)
# the menu word draw: dx = [si] (swapped in Shift-JIS builds), attribute, put
MENU_PUT = re.compile(rb"\x8b\x14\x46\x46(?:\x86\xd6)?\x8a\x0e..\xe8(..)", re.S)
# the JIS build's string put: position in ax, [count][words] at bx, attribute
# in cl; it writes the words to the text layer itself
PUT_STRING = re.compile(rb"\x06\x50\x51\x52\x56\x57\xfc\x8a\xf1\x8a\xd0\xb0\xa0\xf6\xe4\x8b\xf8\x8a\xc2\x32\xe4"
                        rb"\xd1\xe0\x03\xf8\x8b\xf3\x8b\x0c\x46\x46\xb8\x00\xa0\x8e\xc0\x26\x88\xb5\x00\x20\xad", re.S)
# a JIS build's message draw compares with JIS "「" (cmp dx, 2156h)
JIS_TEXT = re.compile(rb"\x81\xfa\x56\x21")
# the half-width put: position in ax, character in dl, attribute in cl
PUT_HALF = re.compile(rb"\x1e\x50\x52\x57\xfc\x8a\xf0(?:\x32\xc0\xd1\xe8|\xb0\xa0\xf6\xe4)\x8b\xf8", re.S)

COLOURS = {b"\x81\x7b": "{C1}", b"\x81\x7c": "{C2}", b"\x81\x7d": "{C0}"}
NEWLINE_CHAR = b"\x81\xab"
LINE_COLS = 72      # 36 cells from column 4
WORD_CELLS = 7      # menu entries show 7 of their 8 cells


class Codec:
    """How a build stores message text.  Most store Shift-JIS words; the
    oldest (Yoru no Tenshi-tachi) stores JIS words, low byte first, and has
    no line mark.  English letters go in pairs, two to a word: in a
    Shift-JIS build as plain ASCII (the first byte below 80h marks them); in
    a JIS build, whose codes are all below 80h, the first letter carries
    bit 7."""

    def __init__(self, jis=False, newline=True):
        self.jis, self.newline = jis, newline
        self.colours = {b"\x5c\x21": "{C1}", b"\x5d\x21": "{C2}"} if jis else COLOURS

    def control(self, v):
        return v < 0x2000 if self.jis else v <= 0x2000

    def char_ok(self, w):
        if self.jis:
            return 0x21 <= w[0] <= 0x7E and 0x21 <= w[1] <= 0x7E
        return (0x81 <= w[0] <= 0x9F or 0xE0 <= w[0] <= 0xEF) and 0x40 <= w[1] <= 0xFC

    def to_text(self, w):
        if self.jis:
            return bytes([w[1] | 0x80, w[0] | 0x80]).decode("euc_jp", "replace")
        return w.decode("cp932", "replace")

    def from_char(self, c):
        """A full-width character as a word, or None."""
        try:
            if self.jis:
                e = c.encode("euc_jp")
                return bytes([e[1] & 0x7F, e[0] & 0x7F]) if len(e) == 2 and e[0] >= 0xA1 else None
            b = c.encode("cp932")
            return b if len(b) == 2 else None
        except UnicodeEncodeError:
            return None

    def ascii(self, text):
        """An even-length ASCII string as letter-pair words."""
        if not self.jis:
            return text.encode("ascii")
        return b"".join(bytes([ord(text[i]) | 0x80, ord(text[i + 1])]) for i in range(0, len(text), 2))


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _rel(img, at, base):
    """Target of the near call whose rel16 is at image offset `at`."""
    return (base + at + 2 + struct.unpack_from("<h", img, at)[0]) & 0xFFFF


class Game:
    def __init__(self, paths):
        self.paths = list(paths)
        self.disks = [bytearray(open(p, "rb").read()) for p in self.paths]
        boot = bytes(self.disks[0])
        # (a copy-protection loader in some boot sectors has the same shape, for one sector)
        hits = [m for m in LOAD.finditer(boot) if _u16(m.group(3), 0) >= 8]
        if not hits:
            raise ValueError("engine load code not found")
        m = hits[0]
        self.lba, self.base, self.count = (_u16(m.group(k), 0) for k in (1, 2, 3))
        self.img_off = self.lba * SECTOR
        self.img = boot[self.img_off:self.img_off + self.count * SECTOR]
        s = SCENE.search(self.img)
        if not s:
            raise ValueError("scene load not found")
        self.scene_table = _u16(s.group(1), 0)
        self.text_hdr = (s.group(2) or s.group(3))[0]
        self.tables = sorted({_u16(t.group(1), 0) for t in TABLE.finditer(self.img)})
        if self.scene_table not in self.tables:
            raise ValueError("directory tables not found")
        self.music_table = self.tables[-1]     # the last table (music)
        w = WORDS.search(self.img)
        if not w:
            raise ValueError("word file load not found")
        self.word_addr, self.word_lba, self.word_count = (_u16(w.group(k), 0) for k in (1, 2, 3))
        self.word_load = w
        # "↓" starts a new line in most builds; others only wrap at the edge
        self.newline = bool(NEWLINE.search(self.img))
        self.codec = Codec(bool(JIS_TEXT.search(self.img)), self.newline)
        self.scene_limit = min(self.word_addr, self.base)

    # ---- engine image ---------------------------------------------------------
    def _at(self, addr):
        return self.img_off + addr - self.base

    def poke(self, addr, data):
        o = self._at(addr)
        self.disks[0][o:o + len(data)] = data
        self.img = bytes(self.disks[0][self.img_off:self.img_off + self.count * SECTOR])

    def entries(self, table):
        """[(disk, lba, count)] for the table's 128 slots (disk 0 = unused)."""
        out = []
        for k in range(128):
            e = self.img[table - self.base + 4 * k:table - self.base + 4 * k + 4]
            v = int.from_bytes(e[1:4], "little")
            out.append((e[0], v & 0xFFF, v >> 12))
        return out

    def set_entry(self, table, k, disk, lba, count):
        if lba > 0xFFF or count > 0xFFF:
            raise ValueError("sector %d / count %d does not fit a table entry" % (lba, count))
        self.poke(table + 4 * k, bytes([disk]) + (lba | count << 12).to_bytes(3, "little"))

    def read(self, disk, lba, count):
        return bytes(self.disks[disk - 1][lba * SECTOR:(lba + count) * SECTOR])

    def engine_strings(self):
        """[(address of the count word, count)]: the Japanese strings the
        JIS build's string put draws (its title screen's sound prompt; the
        other screen strings are full-width English already).  A call
        loads bx with the string, or with a record (position word first)."""
        m = PUT_STRING.search(self.img) if self.codec.jis else None
        if not m:
            return []
        entry, out = self.base + m.start(), []
        for c in re.finditer(rb"\xbb(..)(\x8b\x07\x43\x43)?(?:\xb1.)?\xe8(..)", self.img, re.S):
            if _rel(self.img, c.start(3), self.base) != entry:
                continue
            a = _u16(c.group(1), 0) + (2 if c.group(2) else 0)
            n = _u16(self.img, a - self.base)
            text = self.img[a - self.base + 2:a - self.base + 2 + 2 * n]
            if any(text[i + 1] >= 0x24 and text[i + 1] != 0x23 for i in range(0, len(text), 2)) \
                    and (a, n) not in out:
                out.append((a, n))
        return out

    def scenes(self):
        return [(k, e) for k, e in enumerate(self.entries(self.scene_table)) if e[0]]

    # ---- words -------------------------------------------------------------------
    def word_tables(self):
        """(data, [the two word tables' (start, end)], the message table's
        (start, end) or None).  The header holds the table offsets; a
        four-entry header (8 bytes) also gives the end of the third table,
        a list of messages like a scene's; with three entries that table is
        not used (its space holds leftovers)."""
        data = self.read(1, self.word_lba, self.word_count)
        n = _u16(data, 0) // 2
        h = struct.unpack_from("<%dH" % n, data, 0)
        return data, [(h[0], h[1]), (h[1], h[2])], ((h[2], h[3]) if n >= 4 else None)

    def set_words(self, data):
        """Write a rebuilt word file.  One with a known end (four-entry
        header) is loaded just below the engine, so the scene buffer below
        it gets any room it leaves; its sectors move to free ones when it no
        longer fits its old place."""
        need = -(-len(data) // SECTOR)
        lba = self.word_lba
        if need > self.word_count:
            lba = _take_run(self.free_sectors(1), need)
            if lba is None:
                raise ValueError("no %d free sectors in a row for the word file" % need)
        img = self.disks[0]
        img[lba * SECTOR:(lba + need) * SECTOR] = data.ljust(need * SECTOR, b"\0")
        addr = self.base - need * SECTOR
        w = self.word_load
        for grp, val in ((1, addr), (2, lba), (3, need), (4, addr)):
            self.poke(self.base + w.start(grp), struct.pack("<H", val))
        self.word_addr, self.word_lba, self.word_count = addr, lba, need
        self.scene_limit = min(addr, self.base)

    # ---- free space ----------------------------------------------------------------
    def free_sectors(self, disk):
        used = set()
        for t in self.tables:
            for d, lba, cnt in self.entries(t):
                if d == disk:
                    used.update(range(lba, lba + cnt))
        if disk == 1:
            used.update(range(0, self.lba + self.count))
            used.update(range(self.word_lba, self.word_lba + self.word_count))
        img = self.disks[disk - 1]
        return [s for s in range(len(img) // SECTOR)
                if s not in used and len(set(img[s * SECTOR:(s + 1) * SECTOR])) == 1]


def messages(data, hdr, codec):
    """([(number, start, end)], text start): the messages that end inside
    the file (end = offset of the zero word), numbered by position, parsed
    until the first word that is neither text nor a control."""
    start = hdr + _u16(data, hdr - 2)
    out, i, n = [], start, 0
    while i + 2 <= len(data):
        s = i
        while i + 2 <= len(data):
            w = data[i:i + 2]
            if w == b"\0\0":
                break
            if not (codec.control(w[0] | w[1] << 8) or codec.char_ok(w)):
                return out, start
            i += 2
        if i + 2 > len(data):
            break
        if i > s:
            out.append((n, s, i))
        n += 1
        i += 2
    return out, start


OPENERS = "《「（『〈“‥・…＜【［{\n"


def scene_messages(game):
    """{scene: (data, [(number, start, end)])}.  The disk tool left old
    sector contents after each file's real end, and some of it parses as
    messages; the real end is the first piece (after the first) that starts
    mid-sentence, not with an opening bracket, a colour or a newline, and is
    the tail of another message.  It and everything after it are dropped."""
    raw = {}
    for k, (disk, lba, cnt) in game.scenes():
        data = game.read(disk, lba, cnt)
        raw[k] = (data, messages(data, game.text_hdr, game.codec)[0])
    texts = {decode(d[s:e], game.codec) for d, ms in raw.values() for _n, s, e in ms}
    out = {}
    for k, (data, ms) in raw.items():
        keep = []
        for i, (n, s, e) in enumerate(ms):
            t = decode(data[s:e], game.codec)
            if i and t[:1] not in OPENERS and any(o != t and o.endswith(t) for o in texts):
                break
            keep.append((n, s, e))
        out[k] = (data, keep)
    return out


def decode(piece, codec):
    """A message as shown: colours and controls as tokens, "↓" as a newline
    (in builds that have it)."""
    out = []
    for i in range(0, len(piece), 2):
        w = piece[i:i + 2]
        v = w[0] | w[1] << 8
        if codec.control(v):
            out.append("{A%d}" % v)
        elif w in codec.colours:
            out.append(codec.colours[w])
        elif w == NEWLINE_CHAR and codec.newline:
            out.append("\n")
        else:
            out.append(codec.to_text(w))
    return "".join(out)


def cells(jp):
    """Display width of a decoded message in 2-column cells."""
    return len(re.sub(r"\{[A-Z]\d+\}|\n", "", jp))


# ---- English -> engine words ------------------------------------------------------------
_SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
_TOKEN = re.compile(r"\{([A-Z])(\d+)\}")


def _items(text, codec):
    """[(kind, value, cols)]: 'a' ASCII char, 'w' a 2-byte word (Shift-JIS
    character, colour or control), 'n' newline."""
    out, i = [], 0
    rev = {v: k for k, v in codec.colours.items()}
    while i < len(text):
        m = _TOKEN.match(text, i)
        if m:
            tok = m.group(0)
            if tok in rev:
                out.append(("w", rev[tok], 0))
            elif m.group(1) == "A":
                out.append(("w", struct.pack("<H", int(m.group(2))), 0))
            else:
                raise ValueError("unknown token %s" % tok)
            i = m.end()
            continue
        c = _SUBST.get(text[i], text[i])
        i += 1
        if c == "\n":
            out.append(("n", None, 0))
        elif len(c) > 1:
            out.extend(("a", ch, 1) for ch in c)
        elif 0x20 <= ord(c) < 0x7F:
            out.append(("a", c, 1))
        else:
            b = codec.from_char(c)
            out.append(("w", b, 2) if b else ("a", "?", 1))
    return out


def _encode_line(items, codec):
    """One line's items -> bytes; each ASCII run padded to an even length."""
    out, run = bytearray(), []
    for kind, val, _c in items + [("end", None, 0)]:
        if kind == "a":
            run.append(val)
            continue
        if run:
            s = "".join(run)
            if len(s) % 2:
                s += " "
            out += codec.ascii(s)
            run = []
        if kind == "w":
            out += val
    return bytes(out)


def _width(items):
    """Columns a line takes once ASCII runs are padded."""
    cols, run = 0, 0
    for kind, _v, c in items:
        if kind == "a":
            run += 1
            continue
        cols += run + (run % 2) + c
        run = 0
    return cols + run + (run % 2)


def lay_out(text, codec, cols=LINE_COLS):
    """English -> message bytes (without the zero word): lines wrapped at
    word boundaries to `cols` columns and joined by "↓", or, in a build
    without it, padded with spaces to the edge where the engine wraps."""
    lines = []
    for para in text.split("\n"):
        items = _items(para, codec)
        line = []
        while items:
            # take items up to the width; break at the last space
            take = 0
            while take < len(items) and _width(line + items[:take + 1]) <= cols:
                take += 1
            if take == len(items):
                line += items
                items = []
                break
            cut = take
            while cut > 0 and not (items[cut][0] == "a" and items[cut][1] == " "):
                cut -= 1
            if cut == 0:
                cut = take or 1
                lines.append(line + items[:cut])
                items = items[cut:]
            else:
                lines.append(line + items[:cut])
                items = items[cut + 1:]
            line = []
        lines.append(line)
    if codec.newline:
        return NEWLINE_CHAR.join(_encode_line(ln, codec) for ln in lines)
    out = b""
    for k, ln in enumerate(lines):
        if k < len(lines) - 1:
            ln = ln + [("a", " ", 1)] * (cols - _width(ln))
        out += _encode_line(ln, codec)
    return out


def encode_word(text):
    s = "".join(_SUBST.get(c, c) for c in text)
    s = "".join(c if 0x20 <= ord(c) < 0x7F else "?" for c in s)
    return s.encode("ascii")


# ---- engine patch -------------------------------------------------------------------------
def patch_engine(game, box_lines=3):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm
    img, base = game.img, game.base
    ms = MSG_START.search(img)
    mp = MSG_PUT.search(img, ms.start() if ms else 0)
    wr = WRAP.search(img, ms.start() if ms else 0)
    mn = MENU_PUT.search(img)
    ph = PUT_HALF.search(img)
    if not (ms and mp and wr and mn and ph) or wr.start() > mp.start():
        raise ValueError("message/menu draw not found")
    put_at = mp.start(1)                        # rel16 of the put call
    put = _rel(img, put_at, base)
    advances = mp.group(2) is None              # the put moves the column itself
    menu_at = mn.start(1)
    if _rel(img, menu_at, base) != put:
        raise ValueError("menu draw uses another put routine")
    scroll = _rel(img, wr.start(1), base)
    # the scroll calls inside the message draw (the wrap and, where there is one, "↓")
    scrolls = [c.start(1) for c in re.finditer(rb"\xe8(..)", img[ms.start():mp.start()], re.S)]
    scrolls = [ms.start() + a for a in scrolls if _rel(img, ms.start() + a, base) == scroll]
    half = ph.start() + base
    # mov dx/ax, position; mov [cursor], dx/ax
    start_code = img[ms.start():ms.start() + (7 if img[ms.start()] == 0xBA else 6)]
    # cave: the music table's tail
    tbl = game.entries(game.music_table)
    last = max(k for k, e in enumerate(tbl) if e[0])
    cave = game.music_table + 4 * (last + 1) + 16
    room = game.music_table + 0x200 - cave
    src = """
    cnt:
        .byte 0, 0
    put2:
        {test}
        CALLN 0x{put:x}
        .byte 0xc3
    asc:
        push ax
        push dx
        {first}
        CALLN 0x{half:x}
        pop dx
        pop ax
        push ax
        push dx
        inc al
        {second}
        CALLN 0x{half:x}
        pop dx
        pop ax
        {advance}
        .byte 0xc3
    scrl:
        inc byte ptr cs:[{cnt}]
        cmp byte ptr cs:[{cnt}], {lines}
        jb go
        mov byte ptr cs:[{cnt}], 0
        push ax
        push bx
        push dx
        mov dx, 0x7fd9
    fl:
        mov ah, 1
        int 0x18
        cmp bh, 0
        je w0
        mov ah, 0
        int 0x18
        jmp fl
    w0:
        in al, dx
        test al, 0x80
        jz w0
    w1:
        mov ah, 1
        int 0x18
        cmp bh, 0
        jne wkey
        in al, dx
        test al, 0x80
        jnz w1
    w2:
        in al, dx
        test al, 0x80
        jz w2
        jmp wdone
    wkey:
        mov ah, 0
        int 0x18
    wdone:
        pop dx
        pop bx
        pop ax
    go:
        CALLN 0x{scroll:x}
        .byte 0xc3
    str2:
        push ax
        push bx
        push dx
        push si
        mov si, bx
        mov bx, word ptr [si]
        add si, 2
    s1:
        or bx, bx
        jz s2
        mov dx, word ptr [si]
        add si, 2
        CALLN put2
        {step}
        dec bx
        jmp s1
    s2:
        pop si
        pop dx
        pop bx
        pop ax
        .byte 0xc3
    reset:
        mov byte ptr cs:[{cnt}], 0
        .byte {start}
        .byte 0xc3
    """
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    if game.codec.jis:      # first letter in dl with bit 7, second in dh
        test, first, second = "test dl, 0x80\n        jnz asc", "and dl, 0x7f", "mov dl, dh"
    else:                   # first letter in dh (below 80h), second in dl
        test, first, second = "cmp dh, 0x80\n        jb asc", "mov dl, dh", ""
    fmt = dict(put=put, half=half, advance="add al, 2" if advances else "", test=test, first=first, second=second,
               step="" if advances else "add al, 2", scroll=scroll, lines=box_lines,
               cnt=cave, start=", ".join("0x%02x" % b for b in start_code))
    code, labels = _asm(ks, src.format(**fmt), cave, ("put2", "scrl", "reset", "str2"))
    if len(code) > room:
        raise ValueError("helpers need %d bytes, the music table tail has %d" % (len(code), room))
    if any(img[cave - base:cave - base + len(code)]):
        raise ValueError("music table tail is not free")
    if b"\x66" in code:
        raise ValueError("32-bit prefix in the helpers")
    game.poke(cave, code)
    for at in [put_at, menu_at]:
        rel = (labels["put2"] - (base + at + 2)) & 0xFFFF
        game.poke(base + at, struct.pack("<H", rel))
    for at in scrolls:
        rel = (labels["scrl"] - (base + at + 2)) & 0xFFFF
        game.poke(base + at, struct.pack("<H", rel))
    ps = PUT_STRING.search(img) if game.codec.jis else None
    if ps:      # the string put draws through the helper too
        at = ps.start()
        game.poke(base + at, b"\xe9" + struct.pack("<H", (labels["str2"] - (base + at + 3)) & 0xFFFF))
    at = ms.start()
    rel = (labels["reset"] - (base + at + 3)) & 0xFFFF
    game.poke(base + at, b"\xe8" + struct.pack("<H", rel) + b"\x90" * (len(start_code) - 3))


# ---- driver ------------------------------------------------------------------------------
def _images(cfg, src):
    base = os.path.dirname(src)
    return [src] + [os.path.join(base, n) for _t, n in sorted(cfg.get("floppies", {}).items())]


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    game = Game(_images(cfg, src))
    merged, order = {}, []

    def add(kind, jp, ref, max_cells):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": max_cells}
        order.append(key)

    for k, (data, msgs) in scene_messages(game).items():
        for num, s, e in msgs:
            jp = decode(data[s:e], game.codec)
            if not re.sub(r"\{[A-Z]\d+\}|\s|　", "", jp):
                continue
            add("msg", jp, "scene%d:%d" % (k, num), 3 * LINE_COLS // 2)
    data, tables, mtab = game.word_tables()
    for t, (a, b) in enumerate(tables):
        for i, o in enumerate(range(a, b, 16)):
            jp = "".join(game.codec.to_text(data[q:q + 2]) for q in range(o, o + 16, 2)
                         if game.codec.char_ok(data[q:q + 2])).rstrip("　 ")
            if jp:
                add("word", jp, "word%d:%d" % (t, i), WORD_CELLS)
    if mtab:
        for num, s, e in word_messages(data, mtab):
            jp = decode(data[s:e], game.codec)
            if re.sub(r"\{[A-Z]\d+\}|\s|　", "", jp):
                add("msg", jp, "words:%d" % num, 3 * LINE_COLS // 2)
    for a, n in game.engine_strings():
        o = a - game.base + 2
        add("engine", decode(game.img[o:o + 2 * n], game.codec), "engine:%x" % a, n)
    strings = []
    counters = {"msg": 0, "word": 0, "engine": 0}
    for key in order:
        e = merged[key]
        counters[e["kind"]] += 1
        strings.append({"id": "%s%05d" % ({"msg": "m", "word": "w", "engine": "e"}[e["kind"]],
                                            counters[e["kind"]]), **e})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                for k in ("en", "note", "max_cells"):
                    if k in prev:
                        e[k] = prev[k]
    doc = {"game": cfg["title"], "source_image_sha256": sha256(src), "strings": strings}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    game = Game(_images(cfg, src))
    by_ref, warnings = {}, []
    for e in doc["strings"]:
        if mode == "pseudo":
            if e["kind"] == "word":
                text = ("<%s>" % e["id"][1:])[:2 * WORD_CELLS]
            elif e["kind"] == "engine":
                text = pseudo(e["id"], 2 * e["max_cells"], 1.0)[:2 * e["max_cells"]]
            else:
                text = pseudo(e["id"], 2 * cells(e["jp"]))
                toks = re.findall(r"\{[A-Z]\d+\}", e["jp"])
                text = "".join(toks[:1]) + text + "".join(toks[1:])
        else:
            text = e["en"]
        if not text:
            continue
        if e["kind"] == "engine":
            n = e["max_cells"]
            b = encode_word(text)
            if len(b) > 2 * n:
                warnings.append("%s: %d letters, the string has room for %d" % (e["id"], len(b), 2 * n))
                b = b[:2 * n]
            val = game.codec.ascii(b.decode("ascii").ljust(2 * n))
        elif e["kind"] == "word":
            b = encode_word(text)
            if len(b) > 2 * WORD_CELLS:
                warnings.append("%s: %d letters, menu shows %d" % (e["id"], len(b), 2 * WORD_CELLS))
                b = b[:2 * WORD_CELLS]
            val = game.codec.ascii(b.decode("ascii").ljust(16))
        else:
            val = lay_out(text, game.codec)
        for r in e["refs"]:
            by_ref[r] = val
    # word file: entries in place; a message table is rebuilt
    data, tables, mtab = game.word_tables()
    words = bytearray(data)
    for t, (a, b) in enumerate(tables):
        for i, o in enumerate(range(a, b, 16)):
            v = by_ref.get("word%d:%d" % (t, i))
            if v is not None:
                words[o:o + 16] = v
    if mtab:
        out, pos = bytearray(words[:mtab[0]]), mtab[0]
        for num, s, e in word_messages(data, mtab):
            en = by_ref.get("words:%d" % num)
            out += words[pos:s] + (en if en is not None else words[s:e])
            pos = e
        out += words[pos:mtab[1]]
        struct.pack_into("<H", out, 6, len(out))
        game.set_words(bytes(out))
    else:
        o = game.word_lba * SECTOR
        game.disks[0][o:o + len(words)] = words
    # scenes: rebuilt and moved to free sectors
    free = {d: game.free_sectors(d) for d in range(1, len(game.disks) + 1)}
    parsed = scene_messages(game)
    for k, (disk, lba, cnt) in game.scenes():
        data, msgs = parsed[k]
        out, pos, changed = bytearray(), 0, False
        for num, s, e in msgs:
            en = by_ref.get("scene%d:%d" % (k, num))
            if en is None:
                continue
            out += data[pos:s] + en
            pos = e
            changed = True
        if not changed:
            continue
        out += _tail(data, pos)
        if len(out) > game.scene_limit:
            raise ValueError("scene %d is %d bytes; the scene buffer holds %d" % (k, len(out), game.scene_limit))
        need = -(-len(out) // SECTOR)
        if need <= cnt:
            new_lba = lba
        else:
            run = _take_run(free[disk], need)
            if run is None:
                raise ValueError("disk %d has no %d free sectors in a row for scene %d" % (disk, need, k))
            new_lba = run
        img = game.disks[disk - 1]
        body = bytes(out).ljust(need * SECTOR, b"\0")
        img[new_lba * SECTOR:(new_lba + need) * SECTOR] = body
        game.set_entry(game.scene_table, k, disk, new_lba, need)
    for a, n in game.engine_strings():
        v = by_ref.get("engine:%x" % a)
        if v is not None:
            game.poke(a + 2, v)
    patch_engine(game, cfg.get("box_lines", 3))
    with open(dst, "wb") as f:
        f.write(game.disks[0])
    stem = os.path.splitext(dst)[0]
    for p, img in zip(game.paths[1:], game.disks[1:]):
        with open("%s - %s" % (stem, os.path.basename(p)), "wb") as f:
            f.write(img)
    # the disks have no file system: the notice goes next to them
    with open(os.path.join(os.path.dirname(os.path.abspath(dst)), "MTL_NOTE.TXT"), "w", encoding="ascii",
              newline="\r\n") as f:
        f.write(MTL_NOTE.format(title=cfg["title"]))
    for w in warnings:
        print("warning: " + w)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))


def word_messages(data, mtab):
    """[(number, start, end)] in the word file's message table."""
    out, i, n = [], mtab[0], 0
    while i + 2 <= mtab[1]:
        e = i
        while e + 2 <= mtab[1] and data[e:e + 2] != b"\0\0":
            e += 2
        if e > i:
            out.append((n, i, e))
        n += 1
        i = e + 2
    return out


def _tail(data, pos):
    """What follows a scene's last listed message: a message cut off at the
    file's end is kept as it was; old sector contents (pieces ended by a
    zero word) are dropped."""
    for i in range(pos, len(data) - 1, 2):
        if data[i:i + 2] == b"\0\0":
            return b""
    return data[pos:]


def _take_run(free, need):
    """Take `need` consecutive sectors from the sorted free list."""
    for i in range(len(free) - need + 1):
        if free[i + need - 1] - free[i] == need - 1:
            start = free[i]
            del free[i:i + need]
            return start
    return None
