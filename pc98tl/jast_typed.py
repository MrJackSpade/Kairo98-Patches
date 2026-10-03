"""JAST's first typed-command engine (Tenshi-tachi no Gogo): extract/patch
driver.

The forerunner of pc98tl/jast_font12.py (Tenshi II - Minako), on one
self-booting 2HD floppy laid out like an N88-BASIC disk: track 0 has 26
records of 128 bytes, the other tracks 26 of 256, of which the game uses
records 1-16 (the save is record 17 of track 1).  "Sector n" below counts
records 1-16 of each track side.

* The boot loads the font to 1000:6000 and the engine to 1000:0100.  The
  font is the 12x10 glyph font of Tenshi II (15 bytes a glyph, bank 1 at
  6200, bank 2 at 7100, FF before a bank-2 glyph) with the same layout for
  kana, digits and capitals; the kanji are this game's own (GLYPHS, read
  off the font).  Message numbers below 0D draw from 6000, which is empty.
* Scenes come from a table of 6-byte entries in the engine: disk half
  (0, or 1 = 80 tracks on), track, record, count, two bytes the engine
  keeps.  A scene loads at 1000:8000 and is a picture (a run-length byte
  stream of 64x159 bytes, then two bytes, a colour byte and a list of
  sprites ended by 00 00), the messages (zero-ended, the list ended by an
  empty one) and a command table (a count, then 6-byte entries: verb,
  noun, two flags, message, flag).  Portraits load to 1000:E000 through a
  second table of 4-byte entries.
* Typed commands: the player types romaji, which the engine turns into
  kana; the verbs and nouns are 4-glyph entries, each found anywhere in the
  typed line (FF in a command entry matches anything).
* The message box is the full screen width, 53 cells a line; the engine
  wraps at the edge and scrolls the box, waiting for a key every fourth
  scrolled line.

Patch.
* English is two letters to a cell: a letter pair is two bytes, a first
  byte from the bank-1 glyph numbers that are blank and unused by the
  script, and a second byte 1-FE numbering the pair of two characters of
  font6x10.CHARS.  The message draw's glyph lookup goes to a helper that
  builds the pair's glyph from the 6x10 font; every other glyph is drawn
  as before.
* Lines are padded with blank glyphs to the box edge, where the engine
  wraps.
* Scenes are rebuilt with the English; one that outgrows its sectors moves
  to free sectors and its table entry follows.
* Typed commands: the word tables get the English words (up to 4 capitals
  or digits, typed and shown with the game's own glyphs), and the romaji
  conversion is bypassed so a typed letter is stored as the capital itself.
* The helpers and the 6x10 font sit in the engine load's zero tail, which
  stays zero in a running game.

game.json: {"title", "key", "image", "encoding": "jast_typed", "dipsw", "boot_steps"}
Refs: "scene<n>:<message>", "verb:<i>", "noun:<i>".
"""
import json
import os
import re
import struct

from .alice_sys2_tl import sha256
from .jast_boot import MTL_NOTE
from .jast_font12 import BOOT_LOAD, _asm16
from . import font6x10

SPT = 16            # records used per track side
SECTOR = 256
WORD_LEN = 4
BOX_COLS = 53
SCENE_ROOM = 0x6000     # 8000-DFFF, the portraits load at E000

# ---- the font -------------------------------------------------------------------------------
_B1 = {0xA1: "。", 0xA2: "「", 0xA3: "」", 0xA4: "、", 0xA5: "・", 0x20: "　", 0x21: "！", 0x28: "（",
       0x29: "）", 0x2D: "ー", 0x3C: "＜", 0x3E: "＞", 0x3F: "？", 0x5B: "『", 0x5D: "』",
       0x27: "’", 0xE2: "〜", 0xE7: "‼", 0x60: "┌", 0x61: "┐", 0x62: "└", 0x63: "┘", 0x64: "│", 0x65: "─", 0x2E: "．"}
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
_B2 = {}
for _code, _c in zip(
        [0x04, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x19, 0x1A, 0x1D, 0x20, 0x21, 0x22, 0x23, 0x27, 0x2C,
         0x2E, 0x31, 0x33, 0x35, 0x3E, 0x42, 0x43, 0x4B, 0x4C, 0x4D, 0x4E, 0x50, 0x54, 0x56, 0x57, 0x58,
         0x5B, 0x5D, 0x5E, 0x64, 0x6C, 0x6D, 0x6E, 0x70, 0x77, 0x85, 0x8B, 0x8C, 0x8D, 0x91, 0x92, 0x96,
         0x98, 0x9C, 0x9F, 0xA9, 0xAC, 0xB2, 0xB7, 0xBA, 0xBC, 0xBD, 0xC1, 0xC3, 0xC7, 0xD3, 0xD7, 0xD9,
         0xDD, 0xDE, 0xE4, 0xE5],
        "相一入言行育今男女落終課顔学外活金彼館帰業口下子高校好後心込探視静授習舎少先生説体頭手的庭"
        "徒動何中熱能早番部放待万皆向目門弱練訳由美無夢"):
    _B2[_code] = _c
_B1.update({0xE0: "♡", 0xE1: "♥"})
_B2.update({0xEF: "取"})
_B2.update({
    0x01: "浴", 0x02: "安", 0x06: "会", 0x07: "穴", 0x08: "兄", 0x09: "雨", 0x0A: "以", 0x10: "居", 0x12: "妹", 0x13: "上",
    0x15: "映", 0x16: "駅", 0x17: "円", 0x18: "園", 0x1B: "同", 0x1C: "大", 0x1E: "思", 0x1F: "親", 0x24: "書", 0x25: "階",
    0x26: "介", 0x29: "画", 0x2A: "格", 0x2B: "勝", 0x2D: "考", 0x32: "間", 0x34: "感", 0x36: "木", 0x37: "気", 0x38: "聞",
    0x39: "逆", 0x3A: "客", 0x3B: "級", 0x3F: "近", 0x41: "来", 0x44: "暗", 0x45: "係", 0x48: "消", 0x49: "玄", 0x4A: "原",
    0x4F: "交", 0x51: "公", 0x52: "声", 0x53: "告", 0x55: "答", 0x59: "時", 0x5A: "自", 0x5C: "白", 0x5F: "食", 0x60: "初",
    0x61: "小", 0x62: "関", 0x63: "紹", 0x65: "車", 0x66: "信", 0x67: "新", 0x68: "人", 0x69: "姿", 0x6A: "拾", 0x6F: "性",
    0x72: "草", 0x74: "外", 0x75: "達", 0x76: "立", 0x79: "他", 0x7A: "通", 0x7B: "玉", 0x7D: "助", 0x7F: "台", 0x80: "血",
    0x81: "誰", 0x82: "段", 0x84: "父", 0x86: "机", 0x87: "続", 0x88: "使", 0x8A: "冷", 0x8E: "出", 0x8F: "天", 0x90: "電",
    0x93: "同", 0x95: "所", 0x97: "泣", 0x99: "直", 0x9A: "二", 0x9B: "日", 0x9D: "寝", 0x9E: "年", 0xA0: "野", 0xA1: "飲",
    0xA3: "乗", 0xA5: "果", 0xA6: "話", 0xA7: "走", 0xAA: "母", 0xAD: "晩", 0xAE: "半", 0xAF: "必", 0xB1: "左", 0xB3: "服",
    0xB4: "分", 0xB5: "別", 0xB6: "方", 0xB8: "本", 0xB9: "前", 0xBB: "街", 0xBE: "見", 0xBF: "湖", 0xC0: "右", 0xC4: "持",
    0xC6: "森", 0xC8: "山", 0xCA: "屋", 0xCB: "夕", 0xCC: "友", 0xCD: "用", 0xCE: "要", 0xCF: "曜", 0xD1: "呼", 0xD2: "世",
    0xD4: "読", 0xD5: "夜", 0xD6: "力", 0xDA: "悪", 0xDB: "洋", 0xDC: "私", 0xDF: "久", 0xE0: "真", 0xE1: "理", 0xE2: "石",
    0xE3: "井", 0xE6: "従", 0xE7: "最", 0xE8: "家", 0xE9: "恋", 0xEA: "犯", 0xEB: "月", 0xEC: "路", 0xED: "地", 0xEE: "調",
})
GLYPHS = (_B1, _B2)
_REV = {}
for _bank, _m in enumerate(GLYPHS):
    for _code, _ch in _m.items():
        _REV.setdefault(_ch, (_bank, _code))

# ---- engine signatures ----------------------------------------------------------------------
# the message draw: mov dx, <bank 1>; cmp al, FF; jne; mov al, [bx]; inc bx; mov dx, <bank 2>; push bx; jmp
MSG_DRAW = re.compile(rb"\xba(..)\x3c\xff\x75\x06\x8a\x07\x43\xba(..)\x53\xeb(.)", re.S)
SCENES = re.compile(rb"\x8d\x16(..)\x03\xda\x89\x1e(..)\x53\x5e\xbb(..)", re.S)
WORDS = re.compile(rb"\x8a\x04\xba(..)\xe8..\xa0..\x0a\xc0\x74.\x8a\x44\x01\x8d\x16(..)", re.S)
PORTRAITS = re.compile(rb"\x8d\x36(..)\x87\xd3\x03\xf2\xbb(..)\xe8", re.S)
# the romaji path for a letter: mov ch, al; call <consonant table>; mov cl, al; cmp al, FF; je
ROMAJI = re.compile(rb"\x8a\xe8\xe8..\x8a\xc8\x3c\xff\x74", re.S)
STORE = re.compile(rb"\xe8..\xb1\x04\xe9..\x8a\xe8\xe8", re.S)          # call; mov cl, 4; jmp <store>
MSG_ENTRY = re.compile(rb"\x32\xc0\xa2..\x8a\x07\x43\x0a\xc0\x75\x01\xc3", re.S)
# the viewer's scene load: mov al, [choice]; ... mov dx, <table>; add bx, dx; mov [entry], bx; push bx; pop si; mov bx, <buffer>; call
VIEWER = re.compile(rb"\xa0(..)\x8a\xd8\xb7\x00\x03\xdb\x03\xdb\xba(..)\x03\xda\x89\x1e(..)\x53\x5e\xbb(..)\xe8", re.S)
# the box pager: mov al, [lines]; inc al; cmp al, <limit>; jb
PAGER = re.compile(rb"\xa0..\xfe\xc0\x3c(\x04)\x72", re.S)
# a string in the engine handed to the message draw: lea bx, [s] / mov bx, s; call <draw>
ENG_STR = re.compile(rb"(\x8d\x1e|\xbb)(..)\xe8(..)", re.S)
# the command help panel: lea bx, [rows]; mov dx, <position>; mov ch, <rows>
PANEL = re.compile(rb"\x8d\x1e(..)\xba(..)\xb5(.)", re.S)
SAVE = re.compile(rb"\xb0\x80\xb1\x01\xba(.)(.)\xbb", re.S)


class Disk:
    """A D88 image: track 0 of 128-byte records (the boot), the rest of
    256-byte ones."""

    def __init__(self, path):
        self.path = path
        self.raw = bytearray(open(path, "rb").read())
        self.at = {}
        for t in range(164):
            off = struct.unpack_from("<I", self.raw, 0x20 + 4 * t)[0]
            if not off or off >= len(self.raw):
                continue
            n = struct.unpack_from("<H", self.raw, off + 4)[0]
            p = off
            for _k in range(n):
                r = self.raw[p + 2]
                size = struct.unpack_from("<H", self.raw, p + 14)[0]
                self.at[(t, r)] = (p + 16, size)
                p += 16 + size

    def boot(self):
        return b"".join(self.sector(0, r) for r in range(1, 27))

    def write_boot(self, data):
        for r in range(1, 27):
            p, size = self.at[(0, r)]
            self.raw[p:p + size] = data[(r - 1) * 128:r * 128]

    def sector(self, t, r):
        p, size = self.at[(t, r)]
        return bytes(self.raw[p:p + size])

    @staticmethod
    def index(t, r):
        return (t - 1) * SPT + r - 1

    @staticmethod
    def place(n):
        t, r = divmod(n, SPT)
        return t + 1, r + 1

    def read(self, t, r, count):
        n = self.index(t, r)
        return b"".join(self.sector(*self.place(k)) for k in range(n, n + count))

    def write(self, t, r, data):
        n = self.index(t, r)
        for k in range(len(data) // SECTOR):
            p, _size = self.at[self.place(n + k)]
            self.raw[p:p + SECTOR] = data[k * SECTOR:(k + 1) * SECTOR]

    def sectors(self):
        return {self.index(t, r) for (t, r) in self.at if t >= 1 and r <= SPT}


def _track(e):
    return e[1] + (80 if e[0] else 0)


class Game:
    def __init__(self, path):
        self.path = path
        self.disk = Disk(path)
        boot = self.disk.boot()
        self.loads = []
        for m in BOOT_LOAD.finditer(boot):
            cnt, rec, trk, dest = m.group(1)[0], m.group(2)[0], m.group(3)[0], struct.unpack("<H", m.group(4))[0]
            self.loads.append({"at": m.start(), "count": cnt, "track": trk, "rec": rec, "dest": dest})
        if len(self.loads) != 2:
            raise ValueError("boot loads not found")
        self.mem = bytearray(0x10000)
        for ld in self.loads:
            data = self.disk.read(ld["track"], ld["rec"], ld["count"])
            self.mem[ld["dest"]:ld["dest"] + len(data)] = data
        self.engine = [l for l in self.loads if l["dest"] < 0x1000][0]
        img = bytes(self.mem)
        md, me = MSG_DRAW.search(img), MSG_ENTRY.search(img)
        if not (md and me):
            raise ValueError("message draw not found")
        self.font = struct.unpack("<H", md.group(1))[0]
        self.font2 = struct.unpack("<H", md.group(2))[0]
        self.hook = md.end(2)                           # push bx; jmp <draw>
        self.draw = self.hook + 3 + struct.unpack("b", md.group(3))[0]
        self.after_lookup = self.draw + 3               # past "call <glyph address>"
        self.msg_entry = me.start()
        pg = PAGER.search(img)
        if not pg:
            raise ValueError("box pager not found")
        self.pager_limit = pg.start(1)
        end = self.engine["dest"] + 0x100 * self.engine["count"]
        # the cave: past the engine's code and variables, in its load's zero tail
        code_end = len(img[:end].rstrip(b"\0"))
        self.cave = (code_end + 0x1FF) & ~0xFF
        self.eng_refs = {}                              # string address: [immediate offsets]
        for m in ENG_STR.finditer(img[:code_end]):
            if (m.end() + struct.unpack("<h", m.group(3))[0]) & 0xFFFF == self.msg_entry:
                self.eng_refs.setdefault(struct.unpack("<H", m.group(2))[0], []).append(m.start(2))
        sc = SCENES.search(img)
        if sc:
            # the game: typed commands, a help panel, portraits and a save
            wd, pt, rj, st, sv, pn = (p.search(img) for p in (WORDS, PORTRAITS, ROMAJI, STORE, SAVE, PANEL))
            if not (wd and pt and rj and st and sv and pn):
                raise ValueError("engine pieces not found")
            self.kind, self.stride = "typed", 6
            self.scene_at = struct.unpack("<H", sc.group(1))[0]
            self.scene_buf = struct.unpack("<H", sc.group(3))[0]
            self.verbs_at, self.nouns_at = (struct.unpack("<H", wd.group(i))[0] for i in (1, 2))
            self.portraits_at = struct.unpack("<H", pt.group(1))[0]
            self.romaji = rj.start()
            self.store = st.start()
            self.save = (sv.group(2)[0], sv.group(1)[0])       # dh = track, dl = record
            self.panel_ref = pn.start(1)
            self.panel_at = struct.unpack("<H", pn.group(1))[0]
            self.panel_rows = pn.group(3)[0]
            return
        vw = VIEWER.search(img)
        if not vw:
            raise ValueError("scene table not found")
        # the scene viewer (the Bangaihen): a typed digit picks a scene
        self.kind, self.stride = "viewer", 4
        self.scene_at = struct.unpack("<H", vw.group(2))[0]
        self.scene_buf = struct.unpack("<H", vw.group(4))[0]
        self.save = None
        self.portraits_at = None
        self.panel_rows = 0

    def scene_entries(self):
        out, at, n = [], self.scene_at, self.stride
        while True:
            e = bytes(self.mem[at + n * len(out):at + n * len(out) + n])
            if e[0] not in (0, 1) or not 1 <= e[2] <= SPT or not e[3]:
                return out
            out.append(e)

    def portrait_entries(self):
        out, at = [], self.portraits_at
        while at is not None:
            e = self.mem[at + 4 * len(out):at + 4 * len(out) + 4]
            if e[0] not in (0, 1) or not e[3] or not e[2] or e[2] > SPT:
                return out
            out.append(bytes(e))
        return out

    def panel(self):
        """The command help panel's rows: zero-ended glyph strings, the first
        and last the frame, the others a frame glyph, a space, the text,
        spaces and a frame glyph."""
        if not self.panel_rows:
            return []
        out, p = [], self.panel_at
        for _k in range(self.panel_rows):
            q = self.mem.index(0, p)
            out.append(bytes(self.mem[p:q]))
            p = q + 1
        return out

    def scene(self, e):
        return self.disk.read(_track(e), e[2], e[3])

    def words(self):
        """(verbs, nouns), raw 4-byte entries; the nouns run until the
        table stops looking like words.  The viewer has none."""
        if self.kind != "typed":
            return [], []
        verbs = [bytes(self.mem[a:a + WORD_LEN]) for a in range(self.verbs_at, self.nouns_at, WORD_LEN)]
        nouns, a = [], self.nouns_at
        while all(b == 0 or b in _B1 for b in self.mem[a:a + WORD_LEN]):
            nouns.append(bytes(self.mem[a:a + WORD_LEN]))
            a += WORD_LEN
        return verbs, nouns

    def used(self):
        """Sectors something reads: the loads, scenes, portraits."""
        used = set()
        for ld in self.loads:
            n = Disk.index(ld["track"], ld["rec"])
            used.update(range(n, n + ld["count"]))
        for e in self.scene_entries():
            n = Disk.index(_track(e), e[2])
            used.update(range(n, n + e[3]))
        for e in self.portrait_entries():
            n = Disk.index(_track(e), e[2])
            used.update(range(n, n + e[3]))
        return used


def picture_end(d):
    """Where the messages start: past the picture's run-length stream (64
    bytes a row until row 9F), two bytes, the colour byte and the sprite
    list (3-byte entries, or 5-byte ones starting with 00; 00 00 ends it)."""
    bx, col, row = 0, 0xFF, 0

    def step():
        nonlocal col, row
        col = (col + 1) & 0xFF
        if col >= 0x40:
            col, row = 0, row + 1

    while row < 0x9F:
        if d[bx] not in (0, 0xFF):
            step()
            bx += 1
        else:
            for _k in range(d[bx + 1] or 256):
                step()
            bx += 2
    bx += 2
    while True:
        bx += 1
        if d[bx] != 0:
            bx += 2
            continue
        bx += 1
        if d[bx] == 0:
            return bx + 1
        bx += 3


def scene_messages(d):
    """([(start, end)] of the messages, start of the command table)."""
    p = picture_end(d)
    out = []
    while d[p] != 0:
        q = d.index(0, p)
        out.append((p, q))
        p = q + 1
    return out, p + 1


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


def glyph_cells(data):
    n, i = 0, 0
    while i < len(data):
        n, i = n + 1, i + (2 if data[i] == 0xFF else 1)
    return n


_SUBST = {"’": "'", "‘": "'", "“": "'", "”": "'", '"': "'", "—": "-", "–": "-", "…": "...", ":": " -",
          ";": ",", "(": "（", ")": "）"}


class Encoder:
    """English -> glyph bytes: letter pairs on the given first bytes."""

    def __init__(self, pair_codes):
        self.codes = list(pair_codes)

    def pair(self, a, b):
        n = len(font6x10.CHARS)
        p = font6x10.CHARS.index(a) * n + font6x10.CHARS.index(b)
        return bytes([self.codes[p // 254], 1 + p % 254])

    def units(self, text):
        out, run = [], []

        def flush():
            while run:
                a = run.pop(0)
                b = run.pop(0) if run else " "
                out.append(self.pair(a, b))

        for ch in "".join(_SUBST.get(c, c) for c in text):
            if ch in font6x10.CHARS:
                run.append(ch)
                continue
            flush()
            full = chr(ord(ch) + 0xFEE0) if "!" <= ch <= "~" else ch
            if full in _REV:
                bank, code = _REV[full]
                out.append((b"\xff" if bank else b"") + bytes([code]))
            else:
                run.append("?")
        flush()
        return out

    def width(self, text):
        return len(self.units(text))

    def lay_out(self, text, cols=BOX_COLS):
        lines = []
        for para in text.split("\n"):
            line = ""
            for w in para.split(" "):
                cand = (line + " " + w) if line else w
                if self.width(cand) <= cols or not line:
                    line = cand
                else:
                    lines.append(line)
                    line = w
            lines.append(line)
        out = b""
        for k, ln in enumerate(lines):
            us = self.units(ln)
            out += b"".join(us)
            if k < len(lines) - 1:
                out += b"\x20" * ((-len(us)) % cols if us else cols)
        return out


def encode_word(text):
    """A typed command word: capitals and digits, as the game's own glyphs."""
    return "".join(c for c in text.upper() if "A" <= c <= "Z" or "0" <= c <= "9").encode("ascii")


def _texts(game):
    verbs, nouns = game.words()
    out = [("verb:%d" % i, "word", w.rstrip(b"\0")) for i, w in enumerate(verbs)]
    out += [("noun:%d" % i, "word", w.rstrip(b"\0")) for i, w in enumerate(nouns)]
    for at in sorted(game.eng_refs):
        q = game.mem.index(0, at)
        out.append(("eng:%04x" % at, "engine", bytes(game.mem[at:q])))
    for k, row in enumerate(game.panel()):
        if 0 < k < len(game.panel()) - 1:
            out.append(("panel:%d" % k, "panel", _panel_text(row)))
    seen = {}
    for k, e in enumerate(game.scene_entries()):
        if e[:4] in seen:           # two table entries for one scene file
            continue
        seen[e[:4]] = k
        d = game.scene(e)
        msgs, _cmd = scene_messages(d)
        out += [("scene%d:%d" % (k, n), "msg", d[s:t]) for n, (s, t) in enumerate(msgs)]
    return out


def _panel_text(row):
    """A panel row's text: between the frame glyphs and the leading space,
    trailing spaces dropped."""
    return row[2:-1].rstrip(b"\x20")


def _panel_room(row):
    return glyph_cells(row) - 3


def pair_codes(game, texts):
    used = set()
    for _r, _k, t in texts:
        i = 0
        while i < len(t):
            if t[i] == 0xFF:
                i += 2
                continue
            used.add(t[i])
            i += 1
    font = game.mem[game.font:game.font + 256 * 15]
    need = -(-len(font6x10.CHARS) ** 2 // 254)
    free = [c for c in range(1, 0xFF) if c not in (0x20, 0x0D) and c not in used and c not in _B1
            and not any(font[15 * c:15 * c + 15])]
    if len(free) < need:
        raise ValueError("only %d free glyph numbers for letter pairs; %d needed" % (len(free), need))
    return free[:need]


# ---- extraction ------------------------------------------------------------------------------
def run_extract(here, src):
    game = Game(src)
    merged, order = {}, []
    for ref, kind, raw in _texts(game):
        if not raw:
            continue
        jp = decode(raw)
        cells = WORD_LEN if kind == "word" else glyph_cells(raw)
        if kind == "panel":
            cells = _panel_room(game.panel()[int(ref.split(":")[1])])
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = max(merged[key]["max_cells"], cells)
            continue
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells}
        order.append(key)
    prefix = {"msg": "m", "word": "w", "engine": "e", "panel": "p"}
    counters, strings = {}, []
    for key in order:
        e = merged[key]
        counters[e["kind"]] = counters.get(e["kind"], 0) + 1
        strings.append({"id": "%s%05d" % (prefix[e["kind"]], counters[e["kind"]]), **e})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                e["en"] = prev.get("en", "")
                if "note" in prev:
                    e["note"] = prev["note"]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def roundtrip(game):
    """Every scene rebuilt from its parts matches the disk."""
    for e in game.scene_entries():
        d = game.scene(e)
        msgs, cmd = scene_messages(d)
        start = msgs[0][0] if msgs else cmd - 1
        if d[:start] + b"".join(d[s:t] + b"\0" for s, t in msgs) + b"\0" + d[cmd:] != d:
            return False
    return True


# ---- patch -----------------------------------------------------------------------------------
HELPERS = """
    codes:
        .byte {codes}
    buf:
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    put:
        cmp dx, 0x{font:x}
        jne norm
        CALLN find
        jc norm
        mov al, byte ptr [bx]
        inc bx
        CALLN build
        push bx
        mov bx, 0x{buf:x}
        mov si, 0x{after:x}
        jmp si
    norm:
        push bx
        mov si, 0x{draw:x}
        jmp si
    find:
        push si
        push cx
        mov si, 0x{codes_at:x}
        mov cx, {ncodes}
    floop:
        cmp al, byte ptr [si]
        je found
        inc si
        loop floop
        pop cx
        pop si
        stc
        .byte 0xc3
    found:
        mov ah, {ncodes}
        sub ah, cl
        pop cx
        pop si
        clc
        .byte 0xc3
    build:
        push ax
        push bx
        push cx
        push dx
        push si
        push di
        mov cl, al
        mov ch, 0
        dec cx
        mov al, ah
        mov ah, 0
        mov bx, 254
        mul bx
        add ax, cx
        mov bl, {nchars}
        div bl
        mov cl, 10
        mov bl, ah
        mul cl
        add ax, 0x{table:x}
        mov si, ax
        mov al, bl
        mul cl
        add ax, 0x{table:x}
        mov di, ax
        mov bx, 0x{buf:x}
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
        pop di
        pop si
        pop dx
        pop cx
        pop bx
        pop ax
        .byte 0xc3
    table:
"""


def _helpers(game, codes):
    names = ("put", "table", "buf", "codes")
    fmt = dict(codes=", ".join("0x%02x" % c for c in codes), ncodes=len(codes), font=game.font,
               nchars=len(font6x10.CHARS), after=game.after_lookup, draw=game.draw,
               buf=0x1111, codes_at=0x1111, table=0x1111)
    _c, labels = _asm16(HELPERS.format(**fmt), game.cave, names)
    fmt.update(buf=labels["buf"], codes_at=labels["codes"], table=labels["table"])
    code, again = _asm16(HELPERS.format(**fmt), game.cave, names)
    if again != labels or labels["table"] - game.cave != len(code):
        raise ValueError("helper layout")
    return code + font6x10.table(), labels


def _word_clashes(words, ids):
    """English command words that hold another word: the engine finds a
    word anywhere in the typed line, so typing the longer one also matches
    commands of the shorter."""
    out = []
    for a, w in words.items():
        for b, x in words.items():
            if a != b and x and w and x != w and x in w and (a in ids or b in ids):
                out.append("%s (%s) contains %s (%s): typing it also matches that word's commands"
                           % (ids.get(a, a), a, ids.get(b, b), b))
    return out


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    game = Game(src)
    texts = _texts(game)
    enc = Encoder(pair_codes(game, texts))
    by_ref, warnings = {}, []
    for e in doc["strings"]:
        text = e["en"]
        if mode == "pseudo":
            if e["kind"] == "word":
                text = ("W%03d" % int(e["id"][1:]))[-WORD_LEN:]
            elif e["kind"] == "panel":          # a fixed-width row: filled to its room
                tag = "P" + "".join("abcdefghij"[int(c)] for c in str(int(e["id"][1:])))
                text = (tag + " panelrowfiller")[:2 * e["max_cells"]]
            else:
                text = pseudo(e["id"], 2 * e["max_cells"])
        if not text:
            continue
        if e["kind"] == "word":
            v = encode_word(text)
            if len(v) > WORD_LEN:
                warnings.append("%s: %d letters, a command word has %d" % (e["id"], len(v), WORD_LEN))
                v = v[:WORD_LEN]
        elif e["kind"] in ("engine", "panel"):
            us = enc.units(text)
            room = e["max_cells"] if e["kind"] == "panel" else len(us)
            if len(us) > room:
                warnings.append("%s: %d cells, the panel row has %d" % (e["id"], len(us), room))
            v = b"".join(us[:room])
        else:
            v = enc.lay_out(text)
        for r in e["refs"]:
            by_ref[r] = v
    disk, mem = game.disk, game.mem
    # scenes: rebuilt and placed again, first fit, in their own old sectors and
    # the free ones (the free space alone is too scattered for grown scenes)
    entries = game.scene_entries()
    scene_secs = set()
    for e in entries:
        n = Disk.index(_track(e), e[2])
        scene_secs.update(range(n, n + e[3]))
    others = game.used() - scene_secs
    free = sorted(disk.sectors() - others - ({Disk.index(*game.save)} if game.save else set()))
    done = {}
    for k, e in enumerate(entries):
        if e[:4] in done:
            new = done[e[:4]]
            mem[game.scene_at + game.stride * k:game.scene_at + game.stride * k + 4] = new
            continue
        d = game.scene(e)
        msgs, cmd = scene_messages(d)
        start = msgs[0][0] if msgs else cmd - 1
        out = d[:start] + b"".join(by_ref.get("scene%d:%d" % (k, n), d[s:t]) + b"\0"
                                   for n, (s, t) in enumerate(msgs)) + b"\0" + d[cmd:]
        out = out.rstrip(b"\0") + b"\0"
        if len(out) > SCENE_ROOM:
            raise ValueError("scene %d is %d bytes; the scene buffer holds %d" % (k, len(out), SCENE_ROOM))
        need = -(-len(out) // SECTOR)
        n = _take(free, need)
        if n is None:
            raise ValueError("no %d free sectors in a row for scene %d" % (need, k))
        t, r = Disk.place(n)
        size = need
        disk.write(t, r, bytes(out).ljust(size * SECTOR, b"\0"))
        half, tt = (1, t - 80) if t > 80 else (0, t)
        new = bytes([half, tt, r, size])
        mem[game.scene_at + game.stride * k:game.scene_at + game.stride * k + 4] = new
        done[e[:4]] = new
    # command words
    verbs, nouns = game.words()
    table = {}
    tables = (("verb", game.verbs_at, verbs), ("noun", game.nouns_at, nouns)) if game.kind == "typed" else ()
    for name, at, words in tables:
        for i, w in enumerate(words):
            v = by_ref.get("%s:%d" % (name, i))
            if v is not None:
                mem[at + WORD_LEN * i:at + WORD_LEN * (i + 1)] = v.ljust(WORD_LEN, b"\0")
            table["%s:%d" % (name, i)] = bytes(mem[at + WORD_LEN * i:at + WORD_LEN * (i + 1)]).rstrip(b"\0")
    ids = {r: e["id"] for e in doc["strings"] if e["kind"] == "word" for r in e["refs"] if r in by_ref}
    warnings += _word_clashes(table, ids)
    if ids:
        # typed letters stay capitals: the romaji path jumps to the plain store
        at = game.romaji
        mem[at:at + 3] = b"\xe9" + struct.pack("<H", (game.store - (at + 3)) & 0xFFFF)
    # helpers
    code, labels = _helpers(game, enc.codes)
    if any(mem[game.cave:game.engine["dest"] + 0x100 * game.engine["count"]]):
        raise ValueError("the helpers' place in the engine is not free")
    # the engine's strings and the help panel, after the helpers
    extra = b""
    for at, refs in sorted(game.eng_refs.items()):
        v = by_ref.get("eng:%04x" % at)
        if v is None:
            continue
        here = game.cave + len(code) + len(extra)
        extra += v + b"\0"
        for r in refs:
            struct.pack_into("<H", mem, r, here)
    rows = game.panel()
    panel = b""
    for k, row in enumerate(rows):
        v = by_ref.get("panel:%d" % k) if 0 < k < len(rows) - 1 else None
        if v is not None:
            n = glyph_cells(v)
            row = row[:2] + v + b"\x20" * (_panel_room(row) - n) + row[-1:]
        panel += row + b"\0"
    if rows:
        struct.pack_into("<H", mem, game.panel_ref, game.cave + len(code) + len(extra))
    code += extra + panel
    if game.cave + len(code) > game.engine["dest"] + 0x100 * game.engine["count"]:
        raise ValueError("helpers, engine strings and panel need %d bytes; there are %d"
                         % (len(code), game.engine["dest"] + 0x100 * game.engine["count"] - game.cave))
    mem[game.cave:game.cave + len(code)] = code
    at = game.hook
    mem[at:at + 3] = b"\xe9" + struct.pack("<H", (labels["put"] - (at + 3)) & 0xFFFF)
    # the box's own pager counts a message's scrolled lines from 0, waiting at
    # the fourth, so a message's first lines scrolled out unread: in the game
    # (a 4-line box that is never empty) the count starts at 1; in the viewer
    # (a 3-line box, empty at each scene) it waits at every third scroll from
    # the first
    start, limit = (1, 4) if game.kind == "typed" else (2, 3)
    mem[game.msg_entry:game.msg_entry + 2] = bytes([0xB0, start])     # xor al, al -> mov al, <start>
    mem[game.pager_limit] = limit
    eng = game.engine
    disk.write(eng["track"], eng["rec"], bytes(mem[eng["dest"]:eng["dest"] + 0x100 * eng["count"]]))
    with open(dst, "wb") as f:
        f.write(disk.raw)
    with open(os.path.join(os.path.dirname(os.path.abspath(dst)), "MTL_NOTE.TXT"), "w", encoding="ascii",
              newline="\r\n") as f:
        f.write(MTL_NOTE.format(title=cfg["title"]))
    for w in warnings:
        print("warning: " + w)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))


def _take(free, need):
    for i in range(len(free) - need + 1):
        if free[i + need - 1] - free[i] == need - 1:
            start = free[i]
            del free[i:i + need]
            return start
    return None
