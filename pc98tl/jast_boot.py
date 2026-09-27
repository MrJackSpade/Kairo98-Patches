"""JAST family-C games: self-booting 2HD floppies with no file system
(Tenshi-tachi no Gogo IV - Yuko, Tenshi-tachi no Gogo III Bangaihen,
Gomen ne Angel): extract/patch driver.

Disk layout.  The boot sector loads the engine (hand-written assembly) from
logical sector 8 onwards into one segment and jumps to it; the load code is
also kept inside the engine ("b8 08 00 bd <base> b9 <count> ... retf"), which
gives the engine's load offset.  Everything else is found through four
directory tables in the engine (graphics, animation, scenes, music), one
4-byte entry per file: disk number (1 = the boot disk), then 24 bits with
the logical sector (1 KB sectors, 8 per track side) in the low 12 and the
sector count in the high 12.  The menu words are one more file, loaded by a
fixed call (sector, count, address).

Scenes.  A scene file is command tables, then the messages from offset
4C + (word at 4A).  The engine reads a message two bytes at a time: a zero
word ends it, a word up to 2000h (little-endian) is an animation control,
anything else is a Shift-JIS character.  "－", "＋" and "±" only switch the
text colour (name, highlight, normal) and aren't drawn; "↓" starts a new
line.  A message is found by counting, so messages may change length.  The
disk tool that built the floppies cut files at a sector boundary, so a
scene's last message can be cut off (the next file starts there): only
messages that end inside the file are listed, and the rest of the file is
kept as it is.

Patch.
* Scenes are rebuilt with the English messages and written to free sectors
  of their disk (sectors still holding the format filler E5 that no table
  refers to); their table entries are updated.  A scene must fit the
  engine's scene buffer (it loads at offset 0 of the engine segment, below
  the word file).
* The menu words are 16-byte entries (7 cells shown), rewritten in place.
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
A string's ref is "scene<n>:<message number>" or "word<table>:<entry>".
"""
import json
import os
import re
import struct

from .alice_sys2_tl import sha256

SECTOR = 1024
FILLER = b"\xe5" * SECTOR

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""

# the engine's own load code (in the boot sector and again in the engine)
LOAD = re.compile(rb"\xb8(..)\xbd(..)\xb9(..)\xe8\x12\x00\x72\x31\x40\x81\xc5\x00\x04\xe2\xf4"
                  rb"\xb8..\x50\xb8..\x50\xcb", re.S)
# a directory lookup: si = table + 4 * index ... ax = [si+1], cl = [si+3]
TABLE = re.compile(rb"\xbe(..)[^\xbe]{2,8}?\x32\xe4\xd1\xe0\xd1\xe0\x03\xf0.{0,10}?\x8b\x44\x01\x8a\x4c\x03", re.S)
# the scene load: bp = 0 ... then si = 4C + [4A]
SCENE = re.compile(rb"\xbe(..)\xa0..\x32\xe4\xd1\xe0\xd1\xe0\x03\xf0\xbd\x00\x00\x8b\x44\x01.{20,40}?"
                   rb"\xbe(.)\x00\x03\x74\xfe", re.S)
# the music load (its table is the last one; the helpers go in its tail)
MUSIC = re.compile(rb"\xbe(..)\xa0..\xfe\xc8\x32\xe4\xd1\xe0\xd1\xe0\x03\xf0\xbd", re.S)
# the word file load: bp = address, bx = sector, cx = count, then the three table offsets
WORDS = re.compile(rb"\xbd(..)\xbb(..)\xb9(..)\x33\xc0\xe8..\x72.\xbe(..)\x8b\x04\x03\xc6\xa3", re.S)
# the message draw: start position, then the character loop
MSG_START = re.compile(rb"\xba..\x89\x16..\x33\xc9\xc6\x06..\x00\xad\x0b\xc0", re.S)
MSG_PUT = re.compile(rb"\x51\x8a\x0e..\x92\xe8(..)\x92", re.S)
NEWLINE = re.compile(rb"\x3d\xab\x81\x75\x0b\xe8(..)", re.S)
# the menu word draw: dx = [si], swapped, attribute, put
MENU_PUT = re.compile(rb"\x8b\x14\x46\x46\x86\xd6\x8a\x0e..\xe8(..)", re.S)
# the half-width put: position in ax, character in dl, attribute in cl
PUT_HALF = re.compile(rb"\x1e\x50\x52\x57\xfc\x8a\xf0\x32\xc0\xd1\xe8\x8b\xf8", re.S)

COLOURS = {b"\x81\x7b": "{C1}", b"\x81\x7c": "{C2}", b"\x81\x7d": "{C0}"}
NEWLINE_CHAR = b"\x81\xab"
LINE_COLS = 72      # 36 cells from column 4
WORD_CELLS = 7      # menu entries show 7 of their 8 cells


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
        hits = [m for m in LOAD.finditer(boot)]
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
        self.text_hdr = s.group(2)[0]
        self.tables = sorted({_u16(t.group(1), 0) for t in TABLE.finditer(self.img)})
        if self.scene_table not in self.tables:
            raise ValueError("directory tables not found")
        mu = MUSIC.search(self.img)
        if not mu:
            raise ValueError("music load not found")
        self.music_table = _u16(mu.group(1), 0)
        w = WORDS.search(self.img)
        if not w:
            raise ValueError("word file load not found")
        self.word_addr, self.word_lba, self.word_count = (_u16(w.group(k), 0) for k in (1, 2, 3))
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

    def scenes(self):
        return [(k, e) for k, e in enumerate(self.entries(self.scene_table)) if e[0]]

    # ---- words -------------------------------------------------------------------
    def word_tables(self):
        data = self.read(1, self.word_lba, self.word_count)
        h = struct.unpack_from("<3H", data, 0)
        return data, [(h[0], h[1]), (h[1], h[2])]

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
                if s not in used and img[s * SECTOR:(s + 1) * SECTOR] == FILLER]


def _word_ok(w):
    v = w[0] | w[1] << 8
    if v <= 0x2000:
        return True
    return (0x81 <= w[0] <= 0x9F or 0xE0 <= w[0] <= 0xEF) and 0x40 <= w[1] <= 0xFC


def messages(data, hdr):
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
            if not _word_ok(w):
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
        raw[k] = (data, messages(data, game.text_hdr)[0])
    texts = {decode(d[s:e]) for d, ms in raw.values() for _n, s, e in ms}
    out = {}
    for k, (data, ms) in raw.items():
        keep = []
        for i, (n, s, e) in enumerate(ms):
            t = decode(data[s:e])
            if i and t[:1] not in OPENERS and any(o != t and o.endswith(t) for o in texts):
                break
            keep.append((n, s, e))
        out[k] = (data, keep)
    return out


def decode(piece):
    """A message as shown: colours and controls as tokens, "↓" as a newline."""
    out = []
    for i in range(0, len(piece), 2):
        w = piece[i:i + 2]
        v = w[0] | w[1] << 8
        if v <= 0x2000:
            out.append("{A%d}" % v)
        elif w in COLOURS:
            out.append(COLOURS[w])
        elif w == NEWLINE_CHAR:
            out.append("\n")
        else:
            out.append(w.decode("cp932", "replace"))
    return "".join(out)


def cells(jp):
    """Display width of a decoded message in 2-column cells."""
    return len(re.sub(r"\{[A-Z]\d+\}|\n", "", jp))


# ---- English -> engine words ------------------------------------------------------------
_SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
_TOKEN = re.compile(r"\{([A-Z])(\d+)\}")


def _items(text):
    """[(kind, value, cols)]: 'a' ASCII char, 'w' a 2-byte word (Shift-JIS
    character, colour or control), 'n' newline."""
    out, i = [], 0
    rev = {v: k for k, v in COLOURS.items()}
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
            try:
                b = c.encode("cp932")
            except UnicodeEncodeError:
                b = b""
            if len(b) == 2:
                out.append(("w", b, 2))
            else:
                out.append(("a", "?", 1))
    return out


def _encode_line(items):
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
            out += s.encode("ascii")
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


def lay_out(text, cols=LINE_COLS):
    """English -> message bytes (without the zero word): lines wrapped at
    word boundaries to `cols` columns and joined by "↓"."""
    lines = []
    for para in text.split("\n"):
        items = _items(para)
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
    return NEWLINE_CHAR.join(_encode_line(ln) for ln in lines)


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
    nl = NEWLINE.search(img, ms.start() if ms else 0)
    mn = MENU_PUT.search(img)
    ph = PUT_HALF.search(img)
    if not (ms and mp and nl and mn and ph):
        raise ValueError("message/menu draw not found")
    put_at = mp.start(1)                        # rel16 of the put call
    put = _rel(img, put_at, base)
    menu_at = mn.start(1)
    if _rel(img, menu_at, base) != put:
        raise ValueError("menu draw uses another put routine")
    scroll = _rel(img, nl.start(1), base)
    # the scroll calls inside the message draw (the "↓" one and the wrap one)
    end = mp.end() + 0x60
    scrolls = [c.start() + 1 for c in re.finditer(rb"\xe8(..)", img[ms.start():end], re.S)]
    scrolls = [ms.start() + a for a in scrolls if _rel(img, ms.start() + a, base) == scroll]
    if len(scrolls) < 2:
        raise ValueError("message line scrolls not found")
    half = ph.start() + base
    start_code = img[ms.start():ms.start() + 7]   # mov dx, pos; mov [cursor], dx
    # cave: the music table's tail
    tbl = game.entries(game.music_table)
    last = max(k for k, e in enumerate(tbl) if e[0])
    cave = game.music_table + 4 * (last + 1) + 16
    room = game.music_table + 0x200 - cave
    src = """
    cnt:
        .byte 0, 0
    put2:
        cmp dh, 0x80
        jb asc
        CALLN 0x{put:x}
        .byte 0xc3
    asc:
        push dx
        mov dl, dh
        CALLN 0x{half:x}
        pop dx
        CALLN 0x{half:x}
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
    reset:
        mov byte ptr cs:[{cnt}], 0
        .byte {start}
        .byte 0xc3
    """
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    fmt = dict(put=put, half=half, scroll=scroll, lines=box_lines,
               cnt=cave, start=", ".join("0x%02x" % b for b in start_code))
    code, labels = _asm(ks, src.format(**fmt), cave, ("put2", "scrl", "reset"))
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
    at = ms.start()
    rel = (labels["reset"] - (base + at + 3)) & 0xFFFF
    game.poke(base + at, b"\xe8" + struct.pack("<H", rel) + b"\x90" * 4)


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
            jp = decode(data[s:e])
            if not re.sub(r"\{[A-Z]\d+\}|\s|　", "", jp):
                continue
            add("msg", jp, "scene%d:%d" % (k, num), 3 * LINE_COLS // 2)
    data, tables = game.word_tables()
    for t, (a, b) in enumerate(tables):
        for i, o in enumerate(range(a, b, 16)):
            jp = data[o:o + 16].decode("cp932", "replace").rstrip("　 ")
            if jp:
                add("word", jp, "word%d:%d" % (t, i), WORD_CELLS)
    strings = []
    counters = {"msg": 0, "word": 0}
    for key in order:
        e = merged[key]
        counters[e["kind"]] += 1
        strings.append({"id": "%s%05d" % ("m" if e["kind"] == "msg" else "w", counters[e["kind"]]), **e})
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
            else:
                text = pseudo(e["id"], 2 * cells(e["jp"]))
                toks = re.findall(r"\{[A-Z]\d+\}", e["jp"])
                text = "".join(toks[:1]) + text + "".join(toks[1:])
        else:
            text = e["en"]
        if not text:
            continue
        if e["kind"] == "word":
            b = encode_word(text)
            if len(b) > 2 * WORD_CELLS:
                warnings.append("%s: %d letters, menu shows %d" % (e["id"], len(b), 2 * WORD_CELLS))
                b = b[:2 * WORD_CELLS]
            val = b.ljust(16, b" ")
        else:
            val = lay_out(text)
        for r in e["refs"]:
            by_ref[r] = val
    # word file, in place
    data, tables = game.word_tables()
    words = bytearray(data)
    for t, (a, b) in enumerate(tables):
        for i, o in enumerate(range(a, b, 16)):
            v = by_ref.get("word%d:%d" % (t, i))
            if v is not None:
                words[o:o + 16] = v
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
        out += data[pos:]
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


def _take_run(free, need):
    """Take `need` consecutive sectors from the sorted free list."""
    for i in range(len(free) - need + 1):
        if free[i + need - 1] - free[i] == need - 1:
            start = free[i]
            del free[i:i + need]
            return start
    return None
