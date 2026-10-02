"""JAST's typed-command engine with its own 12x10 font (Tenshi-tachi no
Gogo II - Minako): extract/patch driver.

The game runs in 200-line graphics mode and draws every character itself
from a font of 512 glyphs of 12x10 pixels (two banks) that the game loads
from its boot disk; the text is glyph numbers, one byte each, with FF
before a bank-2 glyph and 00 ending a message.  Bank 1 is laid out like
JIS X0201 (digits, capitals, katakana), but with hiragana where the
half-width katakana would be, and kanji in the gaps.  GLYPHS below gives
the characters of both banks (read off the font; the rare ones checked
against the script).

Disk layout (2HD D88, 256-byte sectors; the game uses records 1-19 of each
track side, "sector n" below counts only those):
* The boot sector loads the engine to 1000:0000, the word tables to
  1000:5600 and the system messages plus the font to 1000:6000, and draws
  the title screen (the sound setup) from a run-length text-layer image on
  track 0.
* Scenes are on the second disk, found through a table of 6-byte entries
  in the engine: half (1 = tracks from 1, 2 = tracks from 78), track,
  record, count and two bytes the engine keeps.  A scene file is the
  picture (6-byte header, then three planes of run-length words), a spare
  byte, a command table (count, then 5 bytes each: verb, noun, reply
  message, next scene, event routine) and the messages, found by count.
  Scenes load at 1000:8000.  After a command the engine runs the event
  routine when it's nonzero (a jump table in the engine); otherwise it shows
  the reply, and loads the next scene when that differs from the current one.
* The player types commands: the words are looked up in two tables of 5-byte
  entries (verbs, nouns: the first glyphs of a word, space-padded).  For each
  entry in table order the engine searches the whole typed line, anywhere in
  it, and the first entry found wins; its 1-based position is what the
  command tables use.  The keys are turned into glyphs through two tables
  (plain, shifted) in the engine.

Patch.
* English is two letters to a cell.  A letter pair is two bytes: a first
  byte 09-16 (glyph numbers that are blank and unused) and a second byte
  1-FE; together they number the pair of two characters of
  font6x10.CHARS.  So English takes about as much room as the Japanese.
  The message draw's glyph call goes to a helper that builds the pair's
  12x10 glyph from the 6x10 font and draws it with the game's own routine;
  every other glyph is drawn as before.  Digits and brackets use the
  game's own glyphs.
* Lines are padded with blank glyphs to the box edge, where the engine
  wraps; the line scrolls in the message draw go through a pager.  The box
  shows box_lines (2) lines and starts each message empty, so the first
  lines need no scroll: the pager waits for a key at the message's first
  scroll and then at every box_lines-th, before a line would scroll out
  unread.
* Scenes are rebuilt with the English and written back to back on their
  disk using all 26 records of a track (the engine's reader now takes 26 a
  track on that disk and still 19 on the boot disk, which it also reads),
  which gives the second disk a third more room; the scene table follows.
* The system messages move to a free part of the engine segment, loaded
  with the word tables (the boot's table load now reads a new block from a
  free track: the helpers, the 6x10 font, the system messages, then the
  word tables).
* Typed commands: the word tables get the English words (up to 5 capital
  letters, typed and shown with the game's own A-Z glyphs), and the key
  tables give capitals for the letter keys.
* The title screen's Japanese is rewritten in the text-layer image.

game.json: {"title", "key", "image", "encoding": "jast_font12",
            "floppies": {"B": "<disk 2>"}, "box_lines" (2), "dipsw", "boot_steps"}
Refs: "scene<n>:<message>", "sys:<n>", "verb:<i>", "noun:<i>", "title:<row>:<col>".
"""
import json
import os
import re
import struct

from .alice_sys2_tl import sha256
from .jast_boot import MTL_NOTE, LINE_COLS, _take_run, _images
from . import font6x10

SECTOR = 256
SPT = 19            # records used per track side
PAIR_FIRST, PAIR_LAST = 0x09, 0x16
WORD_LEN = 5

# ---- the font ------------------------------------------------------------------------
_B1 = {0xA1: "。", 0xA2: "「", 0xA3: "」", 0xA4: "、", 0xA5: "・", 0x20: "　", 0x21: "！", 0x28: "（",
       0x29: "）", 0x2D: "ー", 0x3C: "＜", 0x3E: "＞", 0x3F: "？", 0x5B: "『", 0x5D: "』", 0x5F: "＿",
       0xE0: "♡", 0xE1: "♥"}
for _i, _c in enumerate("をぁぃぅぇぉゃゅょっーあいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわん゛゜"):
    _B1[0xA6 + _i] = _c
for _i, _c in enumerate("ヲァィゥェォャュョッ"):
    _B1[0x66 + _i] = _c
for _i, _c in enumerate("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン"):
    _B1[0x71 + _i] = _c
for _i in range(10):
    _B1[0x30 + _i] = "０１２３４５６７８９"[_i]
for _i in range(26):
    _B1[0x41 + _i] = chr(0xFF21 + _i)
for _i, _c in enumerate("一二三四五六七八九"):
    _B1[0x17 + _i] = _c
_B1.update({0x01: "美", 0x02: "今", 0x03: "奈", 0x04: "令", 0x05: "香", 0x06: "明", 0x07: "堀", 0x08: "江",
            0x22: "十", 0x23: "百", 0x24: "千", 0x25: "万", 0x26: "良", 0x27: "優", 0x2A: "役", 0x2B: "増",
            0x2C: "組", 0x2E: "卒", 0x2F: "数", 0x3A: "食", 0x3B: "気", 0x3D: "休", 0x40: "意", 0x5C: "差",
            0x5E: "染", 0x60: "坐", 0x61: "調", 0x62: "並", 0x63: "輸", 0x64: "接", 0x65: "座", 0x70: "湘",
            0x9E: "風", 0x9F: "坊", 0xA0: "愁", 0xE2: "昼", 0xE3: "婚", 0xE4: "裁", 0xE5: "独", 0xE6: "側",
            0xE7: "週", 0xE8: "英", 0xE9: "裸", 0xEA: "噂", 0xEB: "窓", 0xEC: "誕", 0xED: "毎", 0xEE: "慎",
            0xEF: "謹", 0xF0: "堂", 0xF1: "刻", 0xF2: "遅", 0xF3: "緑", 0xF4: "編", 0xF5: "歩", 0xF6: "散",
            0xF7: "薄", 0xF8: "眼", 0xF9: "章", 0xFA: "幼", 0xFB: "想", 0xFC: "哀", 0xFD: "解", 0xFE: "辞"})
_B2 = dict(enumerate(
    "　浴安庫相愛会常兄国首拍入藤行育睡製妹上柳沢駅円園男女命大玲眠親"
    "族課顔学又階木外弾松素奥銀土金海湯彼間館名制実荻境主客俊職教業近"
    "事来口下暗線経未義商原子高校痛交後公音計心身買探句時自亡白授習店"
    "初小裏慣識車形矢人賞籍室少先生性翌姦空席陽達表体広閉通廊確星望易"
    "血料結地父頭流第使作冷色的庭出天電化動俺抱所何正中直師日熱寝年数"
    "可飲品無南果話走春具母々番員長太輩左部服分病方放本前楽街仮娘花絶"
    "右健明問末物文門夫奴屋都題用道曜酔補導夏読汚力練朝蔵島橋魚肉美久"
    "真理喫転茶際保杏家恋灯月路梢聖水判典志遊等宅字不曲昔青好午強引河"))
GLYPHS = (_B1, _B2)
_REV = {}
for _bank, _m in ((0, _B1), (1, _B2)):
    for _code, _ch in _m.items():
        _REV.setdefault(_ch, (_bank, _code))


def decode(data):
    out, i = [], 0
    while i < len(data):
        b = data[i]
        if b == 0xFF and i + 1 < len(data):
            out.append(_B2.get(data[i + 1], "{G%d}" % (0x100 + data[i + 1])))
            i += 2
            continue
        out.append(_B1.get(b, "{G%d}" % b))
        i += 1
    return "".join(out)


# ---- English -> glyph bytes ------------------------------------------------------------------
_SUBST = {"’": "'", "‘": "'", "“": "'", "”": "'", '"': "'", "—": "-", "–": "-", "…": "...", ":": " -",
          ";": ",", "(": "（", ")": "）"}
_NATIVE = {c: bytes([0x30 + i]) for i, c in enumerate("0123456789")}


def _pair(a, b):
    n = len(font6x10.CHARS)
    p = font6x10.CHARS.index(a) * n + font6x10.CHARS.index(b)
    return bytes([PAIR_FIRST + p // 254, 1 + p % 254])


def _cells(text):
    """[(bytes, cells)] for the text: letter pairs, native glyphs."""
    out, run = [], []

    def flush():
        while run:
            a = run.pop(0)
            b = run.pop(0) if run else " "
            out.append((_pair(a, b), 1))

    for ch in "".join(_SUBST.get(c, c) for c in text):
        if ch in font6x10.CHARS:
            run.append(ch)
            continue
        flush()
        if ch in _NATIVE:
            out.append((_NATIVE[ch], 1))
        elif ch in _REV:
            bank, code = _REV[ch]
            out.append(((b"\xff" if bank else b"") + bytes([code]), 1))
        else:
            run.append("?")
    flush()
    return out


def lay_out(text, cols=46, first=47):
    """English -> message bytes: words wrapped to the box (the first line
    one cell wider: it starts a column further left), each line but the
    last padded with blank glyphs to the edge, where the engine wraps."""
    lines = []
    for para in text.split("\n"):
        words, line = para.split(" "), ""
        for w in words:
            limit = 2 * (first if not lines else cols)
            cand = (line + " " + w) if line else w
            if len(cand) <= limit or not line:
                line = cand
            else:
                lines.append(line)
                line = w
        lines.append(line)
    out = b""
    for k, ln in enumerate(lines):
        cells = _cells(ln)
        room = first if k == 0 else cols
        body = b"".join(b for b, _n in cells)
        n = sum(c for _b, c in cells)
        if k < len(lines) - 1:
            body += b"\x20" * max(0, room - n)
        out += body
    return out


def encode_word(text):
    """A typed command word: capitals, as the game's own glyphs."""
    s = "".join(c for c in text.upper() if "A" <= c <= "Z" or "0" <= c <= "9")
    return s.encode("ascii")


# ---- disks ---------------------------------------------------------------------------------
class D88:
    def __init__(self, path, spt=SPT):
        self.path, self.spt = path, spt
        self.raw = bytearray(open(path, "rb").read())
        self.at = {}
        for t in range(164):
            off = struct.unpack_from("<I", self.raw, 0x20 + 4 * t)[0]
            if not off or off >= len(self.raw):
                continue
            p = off
            for _ in range(struct.unpack_from("<H", self.raw, p + 4)[0]):
                c, h, r = self.raw[p], self.raw[p + 1], self.raw[p + 2]
                size = struct.unpack_from("<H", self.raw, p + 14)[0]
                if size == SECTOR and 1 <= r <= spt:
                    self.at[(c * 2 + h) * spt + r - 1] = p + 16
                p += 16 + size

    @staticmethod
    def index(track, rec):
        return track * SPT + rec - 1

    def read(self, n, count):
        return b"".join(bytes(self.raw[self.at[k]:self.at[k] + SECTOR]) for k in range(n, n + count))

    def write(self, n, data):
        data = data.ljust(-(-len(data) // SECTOR) * SECTOR, b"\0")
        for k in range(len(data) // SECTOR):
            o = self.at[n + k]
            self.raw[o:o + SECTOR] = data[k * SECTOR:(k + 1) * SECTOR]

    def free(self, used):
        return [k for k in sorted(self.at) if k not in used and len(set(self.read(k, 1))) == 1]


# boot: "xor al,al; mov cl,count; mov dx,(track<<8)|rec; mov bx,dest; call load"
BOOT_LOAD = re.compile(rb"\x32\xc0\xb1(.)\xba(.)(.)\xbb(..)\xe8", re.S)
TITLE_LOAD = re.compile(rb"\xb4\x56\xbb\x00(.)\xb1(.)\xb6(.)\xb2(.)\xb5\x01\xbd(..)\xcd\x1b", re.S)
TITLE_PLANES = re.compile(rb"\xba\x00\xa0\xbe\x00\x00\xbb(..)\xe8..\xba\x00\xa2\xbe\x00\x00\xbb(..)\xe8", re.S)
TITLE_END = re.compile(rb"\x81\xfe(..)\x74", re.S)
# engine
SYS_MSGS = re.compile(rb"\xbe(..)\xa0(..)\x8a\xf0\x3c(.)\x76\x06\x8b\x36(..)\x2c(.)", re.S)
DIRECTORY = re.compile(rb"\xb4\x00\xbb(..)\x03\xc0\x03\xd8\x03\xc0\x03\xd8\xbe", re.S)
DICTS = re.compile(rb"\xbf(..)\xbe(..)\xe8..\x8a\xc6\xa2..\xbe(..)\xe8", re.S)
KEYS = re.compile(rb"\xbe(..)\xf6\xc4\x01\x74\x03\x83\xc6(.)\xb4\x00\x03\xf0\x8a\x24\x80\xfc\x2a", re.S)
DRAW_CALL = re.compile(rb"\x8a\xea\xe8(..)\x52\xe8", re.S)
GLYPH = re.compile(rb"\x50\x53\x52\x56\x57\xbe(..)\x8a\x16", re.S)
GLYPH_BODY = re.compile(rb"\x56\xb2\x05\xbb", re.S)
# the scene reader: records left in a track = 14h - first record
READER_SPT = re.compile(rb"\x8b\x44\x02\xb1(\x14)\x2a\xc8\x3a\xcc", re.S)
FULL_SPT = 26
SCENE_BUF = re.compile(rb"\xb8\x00\x80\x89\x44\x04\xe8..\xbe\x00\x80", re.S)


class Game:
    def __init__(self, paths):
        self.paths = list(paths)
        self.disks = [D88(p) for p in self.paths]
        a = self.disks[0]
        boot = a.read(0, 2)
        self.loads = []
        for m in BOOT_LOAD.finditer(boot):
            cnt, rec, trk, dest = m.group(1)[0], m.group(2)[0], m.group(3)[0], struct.unpack("<H", m.group(4))[0]
            self.loads.append({"at": m.start(), "count": cnt, "track": trk, "rec": rec, "dest": dest})
        if len(self.loads) != 3:
            raise ValueError("boot loads not found")
        self.mem = bytearray(0x10000)
        for ld in self.loads:
            data = a.read(D88.index(ld["track"], ld["rec"]), ld["count"])
            self.mem[ld["dest"]:ld["dest"] + len(data)] = data
        self.engine = min(self.loads, key=lambda l: l["dest"])
        self.tables_load = sorted(self.loads, key=lambda l: l["dest"])[1]
        img = bytes(self.mem)
        s = SYS_MSGS.search(img)
        d = DIRECTORY.search(img)
        k = DICTS.search(img)
        y = KEYS.search(img)
        dc = DRAW_CALL.search(img)
        g, gb = GLYPH.search(img), GLYPH_BODY.search(img)
        if not (s and d and k and y and dc and g and gb):
            raise ValueError("engine pieces not found")
        self.sys_at, self.sys_count = struct.unpack("<H", s.group(1))[0], s.group(3)[0] + 1
        self.sys_ref = s.start() + 1
        self.dir_at = struct.unpack("<H", d.group(1))[0]
        self.input_at = struct.unpack("<H", k.group(1))[0]
        self.verbs_at, self.nouns_at = (struct.unpack("<H", k.group(i))[0] for i in (2, 3))
        self.keys_at, self.keys_shift = struct.unpack("<H", y.group(1))[0], y.group(2)[0]
        self.draw_call = dc.start() + 2
        self.glyph, self.glyph_body = g.start(), gb.start()
        self.font_at = struct.unpack("<H", g.group(1))[0]
        rs = READER_SPT.search(img)
        if not rs:
            raise ValueError("scene reader not found")
        self.reader_spt = rs.start(1)
        self.title = TITLE_LOAD.search(boot)
        self.title_planes = TITLE_PLANES.search(boot)
        self.title_end = TITLE_END.search(boot)

    # ---- scenes ----------------------------------------------------------------------------
    def entries(self):
        out = []
        for k in range(256):
            e = self.mem[self.dir_at + 6 * k:self.dir_at + 6 * k + 6]
            if e[0] not in (1, 2):
                break
            out.append(bytes(e))
        return out

    @staticmethod
    def place(e):
        """(sector index on the scene disk, count) of a table entry."""
        track = e[1] + 1 + (77 if e[0] == 2 else 0)
        return D88.index(track, e[2]), e[3]

    @staticmethod
    def entry_for(e, n, count):
        track, rec = divmod(n, SPT)
        rec += 1
        if track >= 78:
            half, t = 2, track - 78
        else:
            half, t = 1, track - 1
        if t < 0 or t > 255 or count > 255:
            raise ValueError("no table entry can address sector %d" % n)
        return bytes([half, t, rec, count]) + e[4:6]

    def scene_disk(self):
        return self.disks[1]

    def scene(self, e):
        n, count = self.place(e)
        return self.scene_disk().read(n, count)


def picture_end(data):
    """Offset of the command table: after the 6-byte header and three planes
    of width x height run-length words (a word written twice, then a count:
    that many words in all), and one spare byte."""
    w, h = data[2], data[3]
    pos, left = 6, 3 * w * h
    while left > 0:
        word = data[pos:pos + 2]
        pos += 2
        left -= 1
        if left > 0 and data[pos:pos + 2] == word:
            pos += 2
            run = data[pos]
            pos += 1
            # the engine counts down before a loop that writes at least once:
            # count 1 means 256 more, 0 means 255
            left -= {0: 255, 1: 256}.get(run, run - 1)
    return pos + 1


def text_start(data):
    p = picture_end(data)
    return p + 1 + 5 * data[p]


def messages(data, start):
    """[(number, start, end)] of the messages (end = the 00), numbered by
    position.  The list ends with an empty message (two 00s); what follows
    is old sector contents."""
    out, i, n = [], start, 0
    while i < len(data):
        s = i
        while i < len(data) and data[i] != 0:
            i += 2 if data[i] == 0xFF else 1
        if i >= len(data) or i == s:
            break
        out.append((n, s, i))
        n += 1
        i += 1
    return out


# ---- title screen (text layer, run-length words) --------------------------------------------
def rle_decode(data, pos, end):
    words = []
    while len(words) * 2 < end:
        w = data[pos:pos + 2]
        pos += 2
        words.append(w)
        if data[pos] == 0xFF:
            n = data[pos + 1]
            pos += 2
            words += [w] * (n - 1)
    return words[:end // 2], pos


def rle_encode(words):
    out, i = bytearray(), 0
    while i < len(words):
        j = i
        while j < len(words) and words[j] == words[i] and j - i < 255:
            j += 1
        out += words[i]
        if j - i > 1:
            out += bytes([0xFF, j - i])
        i = j
    return bytes(out)


def screen_text(w):
    """One text-layer cell as text: low byte = JIS first byte - 20h, high
    byte = second byte (with bit 7 on the right half of a full-width
    character); rows 09-0B are one cell wide; high byte 0 is a one-byte
    character."""
    lo, hi = w[0], w[1]
    if hi == 0:
        return chr(lo) if 0x20 <= lo < 0x7F else ("　" if lo == 0 else bytes([lo]).decode("cp932", "replace"))
    if 0x09 <= lo <= 0x0B:
        return chr(hi) if 0x20 <= hi < 0x7F else "?"
    if hi & 0x80:
        return ""                    # right half of a full-width character
    j1, j2 = lo + 0x20, hi
    try:
        return bytes([j1 | 0x80, j2 | 0x80]).decode("euc_jp")
    except UnicodeDecodeError:
        return "?"


def _blank(w):
    """A blank or box-drawing cell (a one-byte character above 7F)."""
    return w in (b"\x20\x00", b"\x00\x00") or (w[1] == 0 and w[0] >= 0x80)


def title_segments(codes):
    """[(row, col, cells, text)] of the Japanese on the title screen: runs
    on a row split by two or more blank cells or by box-drawing cells."""
    out = []
    for row in range(len(codes) // 80):
        cells = codes[row * 80:(row + 1) * 80]
        col = 0
        while col < 80:
            if _blank(cells[col]):
                col += 1
                continue
            s, gap = col, 0
            while col < 80 and gap < 2:
                if cells[col][1] == 0 and cells[col][0] >= 0x80:     # box drawing ends the run
                    break
                gap = gap + 1 if _blank(cells[col]) else 0
                col += 1
            e = col - gap
            text = "".join(screen_text(c) for c in cells[s:e])
            if re.search(r"[぀-ヿ一-鿿]", text):
                out.append((row, s, e - s, text))
    return out


# ---- extraction ------------------------------------------------------------------------------
def _words(mem, at, count):
    for i in range(count):
        raw = bytes(mem[at + WORD_LEN * i:at + WORD_LEN * i + WORD_LEN])
        yield i, raw


def _word_clashes(game, ids):
    """Warnings for English command words the engine can't tell apart: it
    finds each table's words anywhere in the typed line, first entry first,
    so a word holding an earlier word of its table, or a word of the other
    table, is read as that word.  ids: {"verb:<i>": string id} of the
    English words; clashes between two Japanese words are the game's own."""
    tables = {}
    for name, at in (("verb", game.verbs_at), ("noun", game.nouns_at)):
        limit = game.input_at if name == "verb" else game.sys_at
        tables[name] = [(i, raw.split(b" ")[0].split(b"\0")[0])
                        for i, raw in _words(game.mem, at, min(255, (limit - at) // WORD_LEN))]
    out = []
    for name, words in tables.items():
        other = "noun" if name == "verb" else "verb"
        for i, w in words:
            # an earlier word of the same table, or a different word of the other
            rivals = [(name, j, x) for j, x in words[:i]] + \
                     [(other, j, x) for j, x in tables[other] if x != w]
            for kind, j, x in rivals:
                a, b = "%s:%d" % (name, i), "%s:%d" % (kind, j)
                if x and w and x in w and (a in ids or b in ids):
                    out.append("%s (%s) contains %s (%s): typing it is read as that %s"
                               % (ids.get(a, a), a, ids.get(b, b), b, kind))
    return out


def _title(game):
    t, pl, te = game.title, game.title_planes, game.title_end
    if not (t and pl and te):
        return None
    count, cyl, head, rec = t.group(1)[0], t.group(2)[0], t.group(3)[0], t.group(4)[0]
    n = D88.index(cyl * 2 + head, rec)
    data = game.disks[0].read(n, count)
    base = struct.unpack("<H", t.group(5))[0]
    end = struct.unpack("<H", te.group(1))[0]
    c_at, a_at = (struct.unpack("<H", pl.group(i))[0] - base for i in (1, 2))
    codes, _p = rle_decode(data, c_at, end)
    attrs, _q = rle_decode(data, a_at, end)
    return {"sector": n, "count": count, "data": data, "codes": codes, "attrs": attrs,
            "c_at": c_at, "a_at": a_at, "end": end}


def write_title(game, by_ref):
    """Rewrite the title screen's Japanese runs ("title:<row>:<col>" refs)
    in its run-length text-layer image on the boot disk; ASCII only, cut to
    the run's cells."""
    ti = _title(game)
    if not ti:
        return
    codes = list(ti["codes"])
    for row, col, n, _text in title_segments(ti["codes"]):
        v = by_ref.get("title:%d:%d" % (row, col))
        if v is None:
            continue
        s = "".join(c if 0x20 <= ord(c) < 0x7F else "?" for c in v)[:n].ljust(n)
        for i, ch in enumerate(s):
            codes[row * 80 + col + i] = bytes([ord(ch), 0])
    cdata = rle_encode(codes)
    adata = rle_encode(ti["attrs"])
    room_c = ti["a_at"] - ti["c_at"]
    if len(cdata) > room_c or ti["a_at"] + len(adata) > len(ti["data"]):
        raise ValueError("title screen does not fit its sectors")
    data = bytearray(ti["data"])
    data[ti["c_at"]:ti["c_at"] + room_c] = cdata.ljust(room_c, b"\0")
    game.disks[0].write(ti["sector"], bytes(data))


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    game = Game(_images(cfg, src))
    merged, order = {}, []

    def add(kind, jp, ref, cells):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells}
        order.append(key)

    sysdata = bytes(game.mem[game.sys_at:game.font_at])
    for n, s, e in messages(sysdata, 0)[:game.sys_count]:
        add("msg", decode(sysdata[s:e]), "sys:%d" % n, 3 * 46)
    for k, e in enumerate(game.entries()):
        data = game.scene(e)
        for n, s, t in messages(data, text_start(data)):
            add("msg", decode(data[s:t]), "scene%d:%d" % (k, n), 3 * 46)
    for name, at, limit in (("verb", game.verbs_at, game.input_at), ("noun", game.nouns_at, game.sys_at)):
        for i, raw in _words(game.mem, at, min(255, (limit - at) // WORD_LEN)):
            jp = decode(raw.rstrip(b" \0")).strip()
            if jp and "{G" not in jp:
                add("word", jp, "%s:%d" % (name, i), WORD_LEN)
    ti = _title(game)
    if ti:
        for row, col, n, text in title_segments(ti["codes"]):
            add("title", text, "title:%d:%d" % (row, col), n // 2)
    strings, counters = [], {}
    prefix = {"msg": "m", "word": "w", "title": "t"}
    for key in order:
        e = merged[key]
        counters[e["kind"]] = counters.get(e["kind"], 0) + 1
        strings.append({"id": "%s%05d" % (prefix[e["kind"]], counters[e["kind"]]), **e})
    for e in strings:
        if e["kind"] == "word":
            e["note"] = "typed command word: up to 5 capital letters; each entry keeps its position"
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


# ---- patch -----------------------------------------------------------------------------------
HELPERS = """
    cnt:
        .byte 0
    put:
        cmp byte ptr [0x{bank:x}], 0
        jne orig
        cmp al, {first}
        jb orig
        cmp al, {last}
        jbe pair
    orig:
        CALLN 0x{call800:x}
        .byte 0xc3
    pair:
        push ax
        push bx
        push cx
        push dx
        push di
        xor ah, ah
        sub al, {first}
        mov bx, 254
        mul bx
        mov bl, byte ptr [si]
        xor bh, bh
        dec bx
        add ax, bx
        inc si
        mov bl, {nchars}
        div bl
        push si
        mov cl, 10
        mov bl, ah
        mul cl
        add ax, {font}
        mov si, ax
        mov al, bl
        mul cl
        add ax, {font}
        mov di, ax
        mov bx, {buf}
        xor dx, dx
    row:
        mov al, byte ptr [si]
        xor ah, ah
        shl ax, 6
        or al, byte ptr [di]
        push ax
        shr ax, 4
        push bx
        add bx, dx
        mov byte ptr [bx], al
        pop bx
        pop ax
        and al, 0x0f
        push bx
        push dx
        shr dx, 1
        add bx, dx
        pop dx
        test dl, 1
        jnz odd
        shl al, 4
        mov byte ptr [bx + 10], al
        jmp next
    odd:
        or byte ptr [bx + 10], al
    next:
        pop bx
        inc si
        inc di
        inc dx
        cmp dx, 10
        jb row
        pop si
        pop di
        pop dx
        pop cx
        pop bx
        pop ax
        push cx
        mov cl, byte ptr [0x{color:x}]
        mov byte ptr [0x{color:x}], ch
        CALLN drawbuf
        mov byte ptr [0x{color:x}], cl
        pop cx
        .byte 0xc3
    drawbuf:
        push ax
        push bx
        push dx
        push si
        push di
        mov si, {buf}
        mov ax, 0x{body:x}
        jmp ax
    scrl:
        inc byte ptr cs:[{cnt}]
        cmp byte ptr cs:[{cnt}], {lines}
        jb go
        mov byte ptr cs:[{cnt}], 0
        push ax
        push bx
    fl:
        mov ah, 1
        int 0x18
        or bh, bh
        je wk
        mov ah, 0
        int 0x18
        jmp fl
    wk:
        mov ah, 1
        int 0x18
        or bh, bh
        je wk
        mov ah, 0
        int 0x18
        pop bx
        pop ax
    go:
        CALLN 0x{scroll:x}
        .byte 0xc3
    reset:
        mov byte ptr cs:[{cnt}], {lines} - 1
        CALLN 0x{draw:x}
        .byte 0xc3
    spt:
        mov cl, 0x14
        cmp byte ptr [si], 0
        je sp1
        mov cl, {full}
    sp1:
        sub cl, al
        .byte 0xc3
    buf:
        .byte 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
"""


def _asm16(src, org, want):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm
    code, labels = _asm(Ks(KS_ARCH_X86, KS_MODE_16), src, org, want)
    if b"\x66" in code:
        raise ValueError("32-bit prefix in the helpers")
    return code, labels


def patch_engine(game, sys_block, box_lines):
    """The helpers, the 6x10 font and the system messages go to CAVE (below
    the word tables); returns the block to load there."""
    mem = game.mem
    cave = game.engine["dest"] + 0x100 * game.engine["count"]
    tables = game.tables_load["dest"]
    call800 = (game.draw_call + 3 + struct.unpack_from("<h", mem, game.draw_call + 1)[0]) & 0xFFFF
    # the scroll calls in the message draw (after its start) and the draw's start call
    draw = game.draw_call
    while not (mem[draw] == 0x50 and mem[draw + 1] == 0x51 and mem[draw + 2] == 0x52):
        draw -= 1
    scrolls = []
    for m in re.finditer(rb"\xe8(..)", bytes(mem[draw:draw + 0x70]), re.S):
        t = (draw + m.start() + 3 + struct.unpack("<h", m.group(1))[0]) & 0xFFFF
        scrolls.append((draw + m.start(), t))
    counts = {}
    for _a, t in scrolls:
        counts[t] = counts.get(t, 0) + 1
    scroll = max((t for t in counts if t != call800), key=lambda t: counts[t])
    scroll_sites = [a for a, t in scrolls if t == scroll]
    # the message lookup's last call, to the draw (then pops and the jump out)
    starts = [m.start() for m in re.finditer(rb"\xe8(..)\x5f\x5e\x5a\x58\x5b\xe9", bytes(mem), re.S)
              if (m.start() + 3 + struct.unpack("<h", m.group(1))[0]) & 0xFFFF == draw]
    if len(starts) != 1:
        raise ValueError("message draw call not found")
    font = font6x10.table()
    fmt = dict(bank=0x4250, first=PAIR_FIRST, last=PAIR_LAST, nchars=len(font6x10.CHARS), font=cave, buf=0,
               color=0x4AC3, call800=call800, body=game.glyph_body, cnt=0, lines=box_lines, scroll=scroll,
               draw=draw, full=FULL_SPT + 1)
    org = cave + len(font)
    code, labels = _asm16(HELPERS.format(**fmt), org, ("put", "scrl", "reset", "buf", "cnt", "spt"))
    fmt.update(buf=labels["buf"], cnt=labels["cnt"])
    code, labels = _asm16(HELPERS.format(**fmt), org, ("put", "scrl", "reset", "buf", "cnt", "spt"))
    sys_at = org + len(code)
    block = font + code + sys_block
    if cave + len(block) > tables:
        raise ValueError("helpers, font and system messages need %d bytes; there are %d"
                         % (len(block), tables - cave))
    block = block.ljust(tables - cave, b"\0")

    def rel(at, target):
        struct.pack_into("<H", mem, at + 1, (target - (at + 3)) & 0xFFFF)

    rel(game.draw_call, labels["put"])
    for a in scroll_sites:
        rel(a, labels["scrl"])
    for a in starts:
        rel(a, labels["reset"])
    struct.pack_into("<H", mem, game.sys_ref, sys_at)
    # the reader's records per track: 26 on the repacked scene disk, 19 on
    # the boot disk (unit 0, which the engine also reads through it)
    at = game.reader_spt - 1                     # "mov cl, 14h; sub cl, al"
    mem[at:at + 4] = b"\xe8" + struct.pack("<H", (labels["spt"] - (at + 3)) & 0xFFFF) + b"\x90"
    # keys: capitals for the letter keys, digits
    rows = {0x10: "QWERTYUIOP", 0x1D: "ASDFGHJKL", 0x29: "ZXCVBNM"}
    for shift in (0, game.keys_shift):
        t = game.keys_at + shift
        for scan, letters in rows.items():
            for i, c in enumerate(letters):
                mem[t + scan + i] = ord(c)
        for i, c in enumerate("1234567890"):
            mem[t + 1 + i] = ord(c)
    return block


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    game = Game(_images(cfg, src))
    by_ref, warnings = {}, []
    for e in doc["strings"]:
        text = e["en"]
        if mode == "pseudo":
            if e["kind"] == "word":
                text = "W%03d" % int(e["id"][1:])      # fixed width: the engine matches words anywhere in the typed line
            elif e["kind"] == "title":
                text = pseudo(e["id"], 2 * e["max_cells"], 1.0)[:2 * e["max_cells"]]
            else:
                text = pseudo(e["id"], 2 * len(e["jp"]))
        if not text:
            continue
        if e["kind"] == "word":
            v = encode_word(text)
            if len(v) > WORD_LEN:
                warnings.append("%s: %d letters, a command word has %d" % (e["id"], len(v), WORD_LEN))
                v = v[:WORD_LEN]
        elif e["kind"] == "title":
            v = text
        else:
            v = lay_out(text)
        for r in e["refs"]:
            by_ref[r] = v
    # scenes: every one rewritten, back to back from track 1 using all 26
    # records of a track (the reader is set to 26); the table entries follow
    old = game.scene_disk()
    packed = D88(old.path, FULL_SPT)
    entries = game.entries()
    new_entries, n1 = [], FULL_SPT          # track 1, record 1
    for k, e in enumerate(entries):
        data = game.scene(e)
        start = text_start(data)
        msgs = messages(data, start)
        out, pos = bytearray(), 0
        for n, s0, t in msgs:
            v = by_ref.get("scene%d:%d" % (k, n))
            if v is not None:
                out += data[pos:s0] + v
                pos = t
        last = msgs[-1][2] + 1 if msgs else start
        out += data[pos:max(last, pos)]
        if 0x8000 + len(out) > 0x10000:
            raise ValueError("scene %d is %d bytes; the scene buffer holds 32768" % (k, len(out)))
        need = -(-len(out) // SECTOR)
        if n1 + need > max(packed.at) + 1:
            raise ValueError("the scenes do not fit the disk")
        packed.write(n1, bytes(out).ljust(need * SECTOR, b"\0"))
        track, rec = divmod(n1, FULL_SPT)
        if track - 1 > 255 or need > 255:
            raise ValueError("scene %d cannot be addressed" % k)
        new_entries.append(bytes([1, track - 1, rec + 1, need]) + e[4:6])
        n1 += need
    game.disks[1] = packed
    for k, e in enumerate(new_entries):
        game.mem[game.dir_at + 6 * k:game.dir_at + 6 * k + 6] = e
    # system messages
    sysdata = bytes(game.mem[game.sys_at:game.font_at])
    sys_block, pos = bytearray(), 0
    for n, s, t in messages(sysdata, 0)[:game.sys_count]:
        v = by_ref.get("sys:%d" % n)
        sys_block += sysdata[pos:s] + (v if v is not None else sysdata[s:t])
        pos = t
    sys_block += b"\0"
    # word tables
    for name, at in (("verb", game.verbs_at), ("noun", game.nouns_at)):
        limit = game.input_at if name == "verb" else game.sys_at
        for i, _raw in _words(game.mem, at, min(255, (limit - at) // WORD_LEN)):
            v = by_ref.get("%s:%d" % (name, i))
            if v is not None:
                game.mem[at + WORD_LEN * i:at + WORD_LEN * (i + 1)] = v.ljust(WORD_LEN, b" ")
    warnings += _word_clashes(game, {r: e["id"] for e in doc["strings"] if e["kind"] == "word"
                                     for r in e["refs"] if r in by_ref})
    block = patch_engine(game, bytes(sys_block), cfg.get("box_lines", 2))
    # boot disk: engine back in place, the new block (cave + word tables) on a free track
    a = game.disks[0]
    eng = game.engine
    a.write(D88.index(eng["track"], eng["rec"]), bytes(game.mem[eng["dest"]:eng["dest"] + 0x100 * eng["count"]]))
    tl = game.tables_load
    cave = eng["dest"] + 0x100 * eng["count"]
    whole = block + bytes(game.mem[tl["dest"]:tl["dest"] + 0x100 * tl["count"]])
    used_a = set()
    for ld in game.loads:
        n = D88.index(ld["track"], ld["rec"])
        used_a.update(range(n, n + ld["count"]))
    need = -(-len(whole) // SECTOR)
    start = None
    # past the last track that holds anything (a blank run inside the
    # opening's pictures looks free too)
    last = max(k for k in a.at if len(set(a.read(k, 1))) > 1) // SPT
    for t in range(last + 1, 160):
        n = D88.index(t, 1)
        if all(k in a.at and k not in used_a and len(set(a.read(k, 1))) == 1 for k in range(n, n + need)):
            start = t
            break
    if start is None or need > 255:
        raise ValueError("no free tracks on the boot disk for the word tables block")
    a.write(D88.index(start, 1), whole)
    boot = bytearray(a.read(0, 2))
    at = tl["at"]
    boot[at + 3] = need
    boot[at + 5], boot[at + 6] = 1, start
    struct.pack_into("<H", boot, at + 8, cave)
    # title screen
    write_title(game, by_ref)
    a.write(0, bytes(boot))
    with open(dst, "wb") as f:
        f.write(a.raw)
    stem = os.path.splitext(dst)[0]
    for p, d in zip(game.paths[1:], game.disks[1:]):
        with open("%s - %s" % (stem, os.path.basename(p)), "wb") as f:
            f.write(d.raw)
    with open(os.path.join(os.path.dirname(os.path.abspath(dst)), "MTL_NOTE.TXT"), "w", encoding="ascii",
              newline="\r\n") as f:
        f.write(MTL_NOTE.format(title=cfg["title"]))
    for w in warnings:
        print("warning: " + w)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
