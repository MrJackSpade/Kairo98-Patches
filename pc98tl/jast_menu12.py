"""JAST's menu engine with its own 12x10 font (Tenshi-tachi no Gogo II
Bangaihen): extract/patch driver.

A sibling of pc98tl/jast_font12.py (Tenshi II - Minako): the same boot
loader, title screen, 12x10 font format and sector reader, but commands are
picked from menus instead of typed, and the text sits in different places.

The game runs in 200-line graphics mode and draws every character itself
from a font of 15-byte 12x10 glyphs in three banks; text is glyph numbers,
one byte each, with FE before a bank-2 glyph and FF before a bank-3 one, 00
ending a message, and bytes 01-08 as controls (the talking face's
animation; they take no operands).  The banks are laid out like the Minako
font (JIS X0201 order, hiragana where half-width katakana would be, kanji
in the gaps), with the game's own kanji: GLYPHS below gives each code's
character, Minako's glyphs matched by bitmap and the rest read off the
font.

Disk layout (2HD D88, 256-byte sectors; the game uses records 1-19 of each
track side, "sector n" counting only those):
* The boot sector loads the engine to 1000:0000, the font block (system
  messages, then the font) to 1000:8800 and the word block to 1000:8000,
  and draws the title screen from a run-length text-layer image on track 0.
  At start the engine copies 8000-AFFF to D000-FFFF, so the words are at
  D000, the system messages at D800 and the font at DA00.
* The word block is the verbs (a count, then zero-ended words) and the
  nouns (the same); menus pick them by position.  Menu words show 8 cells.
* The scene disk (B) starts with two tables of 3-byte entries (track,
  record, count): the scene files from offset 1, the pictures from 101h.
  A scene file is a 6-byte header (picture, flags, first message, number of
  event pictures), the event pictures, a command table (counts a and b,
  then 6a + 4b bytes), the messages (a count, then zero-ended messages) and
  the menus (lists of word numbers).  Scenes load at 1000:4000 and must end
  below 5000, which the save/load code uses as scratch.
* Saves go to track 0 record 16 and track 1 records 1-7 of the boot disk.

Patch.
* English is two letters to a cell: a letter pair is two bytes, a first
  byte from PAIR_CODES (bank-1 glyph numbers that are blank and unused by
  the script) and a second byte 1-FE; together they number the pair of two
  characters of font6x10.CHARS.  Both glyph lookups (the message draw and
  the menu word draw) go to helpers that build the pair's 12x10 glyph from
  the 6x10 font and hand it to the game's own draw; every other glyph is
  drawn as before.  Digits use the game's own glyphs.
* Message lines are padded with blank glyphs to the window edge, where the
  engine wraps.  The engine sets each window's geometry by writing its draw
  code (wrap column, restart and start columns): the main box is 3 lines of
  40 cells that scroll; its scroll goes through a pager, which waits for a
  key before a scroll once 3 lines of the message have been shown.  The
  opening's window is one line; its wrap column is moved in to the frame
  (opening_cols), and a wrap there waits for a key, blanks the line and
  goes on in place.  The opening's messages (opening_scenes, and the load
  prompt) are laid out for it.
* The helpers and the 6x10 font sit in the unused tail of font bank 3,
  which the boot already loads.
* The text moves: the nouns go above the engine (1000:3200-3CFF, free at
  run time; the boot's engine load grows to cover them), the verbs, the
  system messages and the engine's save and load prompts to the word block
  (loaded by the boot's word load, longer now, over the old system
  messages).  The start-up scan that found the nouns after the verbs is
  replaced by the two addresses, and the engine's message pointers follow.
* Scenes are rebuilt with the English; one that outgrows its sectors moves
  to free sectors of the scene disk and its table entry follows.
* The title screen's Japanese is rewritten in its text-layer image.

game.json: {"title", "key", "image", "encoding": "jast_menu12",
            "floppies": {"B": "<disk 2>"}, "box_lines" (3), "dipsw", "boot_steps",
            "opening_scenes": [scene numbers shown in the opening window],
            "opening_prompts": ["eng:<n>" shown there], "opening_cols" (its visible cells)}
Refs: "scene<n>:<message>", "sys:<n>", "eng:<n>" (0 save, 1 load prompt), "verb:<i>",
"noun:<i>", "title:<row>:<col>".  Message controls are "{A<n>}" tokens.
"""
import json
import os
import re
import struct

from .alice_sys2_tl import sha256
from .jast_boot import MTL_NOTE, _take_run, _images
from .jast_font12 import (D88, SECTOR, SPT, BOOT_LOAD, TITLE_LOAD, TITLE_PLANES, TITLE_END,
                          _title, title_segments, write_title, _asm16)
from . import font6x10

BOX_COLS = 40       # message cells per line (columns 2-41)
WORD_CELLS = 8      # menu words: columns 43-50
SCENE_ROOM = 0x1000  # 4000-4FFF

# ---- the font (read off the glyphs) ---------------------------------------------------------
_B1 = {
    0x0A: "俺", 0x0B: "見", 0x0C: "渡", 0x0D: "相", 0x0E: "手", 0x0F: "他", 0x10: "誰", 0x11: "後", 0x12: "悔", 0x13: "考",
    0x14: "行", 0x15: "動", 0x16: "方", 0x17: "梢", 0x18: "自", 0x19: "分", 0x1A: "寝", 0x1B: "室", 0x1C: "戻", 0x1D: "眠",
    0x1E: "仕", 0x1F: "事", 0x20: "　", 0x21: "！", 0x28: "（", 0x29: "）", 0x2C: "、", 0x30: "０", 0x31: "１", 0x32: "２",
    0x33: "３", 0x34: "４", 0x35: "５", 0x36: "６", 0x37: "７", 0x38: "８", 0x39: "９", 0x3C: "＜", 0x3E: "＞", 0x3F: "？",
    0x41: "Ａ", 0x42: "Ｂ", 0x43: "Ｃ", 0x44: "Ｄ", 0x45: "Ｅ", 0x46: "Ｆ", 0x47: "Ｇ", 0x48: "Ｈ", 0x49: "Ｉ", 0x4A: "Ｊ",
    0x4B: "Ｋ", 0x4C: "Ｌ", 0x4D: "Ｍ", 0x4E: "Ｎ", 0x4F: "Ｏ", 0x50: "Ｐ", 0x51: "Ｑ", 0x52: "Ｒ", 0x53: "Ｓ", 0x54: "Ｔ",
    0x55: "Ｕ", 0x56: "Ｖ", 0x57: "Ｗ", 0x58: "Ｘ", 0x59: "Ｙ", 0x5A: "Ｚ", 0x5B: "『", 0x5D: "』", 0x62: "外", 0x63: "国",
    0x64: "打", 0x65: "明", 0x67: "ァ", 0x68: "ィ", 0x6A: "ェ", 0x6B: "ォ", 0x6C: "ャ", 0x6D: "ュ", 0x6E: "ョ", 0x6F: "ッ",
    0x70: "決", 0x71: "ア", 0x72: "イ", 0x73: "ウ", 0x74: "エ", 0x75: "オ", 0x76: "カ", 0x77: "キ", 0x78: "ク", 0x79: "ケ",
    0x7A: "コ", 0x7B: "サ", 0x7C: "シ", 0x7D: "ス", 0x7E: "セ", 0x7F: "ソ", 0x80: "タ", 0x81: "チ", 0x82: "ツ", 0x83: "テ",
    0x84: "ト", 0x85: "ナ", 0x86: "ニ", 0x88: "ネ", 0x89: "ノ", 0x8A: "ハ", 0x8B: "ヒ", 0x8C: "フ", 0x8D: "ヘ", 0x8E: "ホ",
    0x8F: "マ", 0x90: "ミ", 0x91: "ム", 0x92: "メ", 0x93: "モ", 0x94: "ヤ", 0x95: "ユ", 0x97: "ラ", 0x98: "リ", 0x99: "ル",
    0x9A: "レ", 0x9B: "ロ", 0x9C: "ワ", 0x9D: "ン", 0xA0: "心", 0xA1: "。", 0xA2: "「", 0xA3: "」", 0xA4: "、", 0xA5: "・",
    0xA6: "を", 0xA7: "ぁ", 0xA8: "ぃ", 0xA9: "ぅ", 0xAA: "ぇ", 0xAB: "ぉ", 0xAC: "ゃ", 0xAD: "ゅ", 0xAE: "ょ", 0xAF: "っ",
    0xB0: "ー", 0xB1: "あ", 0xB2: "い", 0xB3: "う", 0xB4: "え", 0xB5: "お", 0xB6: "か", 0xB7: "き", 0xB8: "く", 0xB9: "け",
    0xBA: "こ", 0xBB: "さ", 0xBC: "し", 0xBD: "す", 0xBE: "せ", 0xBF: "そ", 0xC0: "た", 0xC1: "ち", 0xC2: "つ", 0xC3: "て",
    0xC4: "と", 0xC5: "な", 0xC6: "に", 0xC7: "ぬ", 0xC8: "ね", 0xC9: "の", 0xCA: "は", 0xCB: "ひ", 0xCC: "ふ", 0xCD: "へ",
    0xCE: "ほ", 0xCF: "ま", 0xD0: "み", 0xD1: "む", 0xD2: "め", 0xD3: "も", 0xD4: "や", 0xD5: "ゆ", 0xD6: "よ", 0xD7: "ら",
    0xD8: "り", 0xD9: "る", 0xDA: "れ", 0xDB: "ろ", 0xDC: "わ", 0xDD: "ん", 0xDE: "゛", 0xDF: "゜", 0xE0: "調", 0xE1: "話",
    0xE2: "聞", 0xE3: "起", 0xE4: "襲", 0xE5: "犯", 0xE6: "抱", 0xE7: "食", 0xE8: "飲", 0xE9: "名", 0xEA: "前", 0xEB: "使",
    0xEC: "帰", 0xED: "居", 0xEE: "間", 0xEF: "母", 0xF0: "家", 0xF1: "族", 0xF2: "義", 0xF3: "妹", 0xF4: "時", 0xF5: "廊",
    0xF6: "下", 0xF7: "右", 0xF8: "左", 0xF9: "父", 0xFA: "堂", 0xFB: "二", 0xFC: "階", 0xFD: "部",
}
_B2 = {
    0x01: "屋", 0x02: "机", 0x03: "本", 0x04: "棚", 0x05: "窓", 0x06: "一", 0x07: "室", 0x08: "床", 0x09: "中", 0x0A: "灯",
    0x0B: "人", 0x0C: "形", 0x0D: "胸", 0x0E: "腰", 0x0F: "乳", 0x10: "首", 0x11: "背", 0x12: "肩", 0x13: "腕", 0x14: "足",
    0x15: "昨", 0x16: "夜", 0x17: "着", 0x18: "金", 0x19: "朝", 0x1A: "学", 0x1B: "校", 0x1C: "駅", 0x1D: "公", 0x1E: "園",
    0x1F: "受", 0x20: "付", 0x21: "嬢", 0x22: "玄", 0x23: "関", 0x24: "舎", 0x25: "箱", 0x26: "教", 0x27: "三", 0x28: "女",
    0x29: "子", 0x2A: "高", 0x2B: "生", 0x2C: "曜", 0x2D: "日", 0x2E: "年", 0x2F: "令", 0x30: "電", 0x31: "番", 0x32: "号",
    0x33: "猫", 0x34: "恵", 0x35: "美", 0x36: "授", 0x37: "業", 0x38: "娘", 0x39: "指", 0x3A: "舌", 0x3B: "頭", 0x3C: "先",
    0x3D: "天", 0x3E: "気", 0x3F: "制", 0x40: "服", 0x41: "亀", 0x42: "杏", 0x43: "持", 0x44: "円", 0x45: "玉", 0x46: "水",
    0x47: "長", 0x48: "保", 0x49: "健", 0x4A: "音", 0x4B: "楽", 0x4C: "男", 0x4D: "元", 0x4E: "愛", 0x4F: "上", 0x50: "奈",
    0x51: "兄", 0x52: "柳", 0x53: "沢", 0x54: "十", 0x55: "八", 0x56: "歳", 0x57: "深", 0x58: "呼", 0x59: "出", 0x5A: "来",
    0x5B: "実", 0x5C: "四", 0x5D: "午", 0x5E: "何", 0x5F: "親", 0x60: "性", 0x61: "悪", 0x62: "今", 0x63: "度", 0x64: "五",
    0x65: "代", 0x66: "会", 0x67: "社", 0x68: "設", 0x69: "立", 0x6A: "揮", 0x6B: "取", 0x6C: "再", 0x6D: "婚", 0x6E: "感",
    0x6F: "発", 0x70: "荷", 0x71: "物", 0x72: "係", 0x73: "月", 0x74: "以", 0x75: "残", 0x76: "段", 0x77: "卒", 0x78: "思",
    0x79: "待", 0x7A: "開", 0x7B: "返", 0x7C: "入", 0x7D: "店", 0x7E: "書", 0x7F: "斎", 0x80: "兼", 0x81: "用", 0x82: "連",
    0x83: "七", 0x84: "準", 0x85: "備", 0x86: "終", 0x87: "不", 0x88: "況", 0x89: "大", 0x8A: "強", 0x8B: "知", 0x8C: "経",
    0x8D: "営", 0x8E: "法", 0x8F: "技", 0x90: "術", 0x91: "尊", 0x92: "敬", 0x93: "多", 0x94: "必", 0x95: "要", 0x96: "幸",
    0x97: "者", 0x98: "際", 0x99: "暗", 0x9A: "判", 0x9B: "特", 0x9C: "痛", 0x9D: "切", 0x9E: "野", 0x9F: "安", 0xA0: "作",
    0xA1: "同", 0xA2: "赤", 0xA3: "坊", 0xA4: "様", 0xA5: "声", 0xA6: "為", 0xA7: "最", 0xA8: "小", 0xA9: "乗", 0xAA: "理",
    0xAB: "向", 0xAC: "降", 0xAD: "顔", 0xAE: "藤", 0xAF: "希", 0xB0: "現", 0xB1: "万", 0xB2: "数", 0xB3: "始", 0xB4: "落",
    0xB5: "木", 0xB6: "香", 0xB7: "歩", 0xB8: "静", 0xB9: "閉", 0xBA: "頃", 0xBB: "近", 0xBC: "毛", 0xBD: "願", 0xBE: "所",
    0xBF: "目", 0xC0: "覚", 0xC1: "可", 0xC2: "頬", 0xC3: "通", 0xC4: "魚", 0xC5: "六", 0xC6: "欲", 0xC7: "初", 0xC8: "場",
    0xC9: "弾", 0xCA: "好", 0xCB: "素", 0xCC: "直", 0xCD: "々", 0xCE: "輩", 0xCF: "品", 0xD0: "第", 0xD1: "章", 0xD2: "演",
    0xD3: "奏", 0xD4: "賞", 0xD5: "陽", 0xD6: "睡", 0xD7: "結", 0xD8: "果", 0xD9: "色", 0xDA: "姦", 0xDB: "少", 0xDC: "丈",
    0xDD: "夫", 0xDE: "土", 0xDF: "求", 0xE0: "未", 0xE1: "練", 0xE2: "激", 0xE3: "込", 0xE4: "引", 0xE5: "客", 0xE6: "習",
    0xE7: "当", 0xE8: "路", 0xE9: "門", 0xEA: "原", 0xEB: "休", 0xEC: "逃", 0xED: "交", 0xEE: "換", 0xEF: "押", 0xF0: "正",
    0xF1: "建", 0xF2: "彼", 0xF3: "駆", 0xF4: "困", 0xF5: "勝", 0xF6: "差", 0xF7: "内", 0xF8: "組", 0xF9: "師", 0xFA: "徒",
    0xFB: "変", 0xFC: "夏", 0xFD: "世", 0xFE: "界", 0xFF: "式",
}
_B3 = {
    0x01: "全", 0x02: "員", 0x03: "恐", 0x04: "怖", 0x05: "英", 0x06: "語", 0x07: "哀", 0x08: "想", 0x09: "身", 0x0A: "幼",
    0x0B: "達", 0x0C: "回", 0x0D: "期", 0x0E: "体", 0x0F: "放", 0x10: "攻", 0x11: "育", 0x12: "針", 0x13: "貞", 0x14: "淑",
    0x15: "執", 0x16: "念", 0x17: "両", 0x18: "側", 0x19: "布", 0x1A: "反", 0x1B: "応", 0x1C: "故", 0x1D: "製", 0x1E: "能",
}

GLYPHS = (_B1, _B2, _B3)
_REV = {}
for _bank, _m in enumerate(GLYPHS):
    for _code, _ch in _m.items():
        _REV.setdefault(_ch, (_bank, _code))

# ---- engine signatures ---------------------------------------------------------------------
COPY = re.compile(rb"\xb9(..)\xbe(..)\xbf(..)\xfc\xf3\xa4", re.S)               # rep movsb of the text block
SYS_PTR = re.compile(rb"\xbb(..)\x80\xf9\x00\x75", re.S)                       # mov bx, <system messages>
MSG_GLYPH = re.compile(rb"\xb4\x00\x8b\xd0(?:\xd1\xe0){4}\x2b\xc2\xba(..)\x03\xd0\xa1(..)", re.S)
MENU_GLYPH = re.compile(rb"\xb4\x00\x2b\xd0(?:\xd1\xe0){4}\x03\xd0\xe8", re.S)
MSG_START = re.compile(rb"\x43\xe8(..)\x8a\x07\x3c\x09\x72", re.S)             # inc bx; call newline
SCROLL = re.compile(rb"\x80\xfa(.)\x74\x08\xfe\xc2\x88\x16..\x5a\xc3\xe8(..)", re.S)
# start-up: the verbs' address, then a scan past them for the nouns'
WORD_PTRS = re.compile(rb"\xbb(..)\x43\x89\x1e(..)\x4b\x8a\x0f\xb0\x00\x43\x3a\x07\x75\xfb\xfe\xc9\x75\xf7\x43\x43\x89\x1e(..)\xc3", re.S)
NOUN_END = 0x3D00     # the free space above the engine ends at the directory buffer
# before the message draw's glyph call: mov cx, [colour]; mov bl, [column]; mov bh, [row]
POSITION = re.compile(rb"\x8b\x0e(..)\x8a\x1e(..)\x8a\x3e(..)\xe8", re.S)
# the message draw's wrap: draw; inc bl; cmp bl, <wrap column>; jne; mov bl, <restart>; call newline
WRAP = re.compile(rb"\xe8(..)\xfe\xc3\x80\xfb(.)\x75\x05\xb3(.)\xe8(..)\x88\x1e", re.S)
# a window's geometry, written into the draw code: wrap column, restart and start columns
GEOMETRY = re.compile(rb"\xbb(..)\xb0(.)\x88\x47\x02\xb0(.)\x88\x47\x06\xbb(..)\x88\x47\x02", re.S)
# the load message: mov dx, [table]; mov bx, <engine messages>; mov [table], bx
ENG_MSGS = re.compile(rb"\x8b\x16(..)\xbb(..)\x89\x1e(..)", re.S)


def _call_target(mem, at):
    return (at + 3 + struct.unpack_from("<h", mem, at + 1)[0]) & 0xFFFF


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
        img = bytes(self.mem[:0x100 * self.engine["count"]])
        c, s, g, mg, ms, sc, w = (p.search(img) for p in (COPY, SYS_PTR, MSG_GLYPH, MENU_GLYPH, MSG_START,
                                                           SCROLL, WORD_PTRS))
        if not (c and s and g and mg and ms and sc and w):
            raise ValueError("engine pieces not found")
        size, src, dst = (struct.unpack("<H", c.group(i))[0] for i in (1, 2, 3))
        self.shift = dst - src                      # running copy = load address + shift
        self.copy_end = dst + size
        self.sys_ref = s.start() + 1
        self.sys_at = struct.unpack("<H", s.group(1))[0] - self.shift
        self.font_at = struct.unpack("<H", g.group(1))[0]      # running address
        self.bank_var = struct.unpack("<H", g.group(2))[0]
        self.msg_glyph = g.start()
        self.msg_glyph_len = g.end(1) + 2 - g.start()
        self.menu_glyph = mg.start()
        self.menu_glyph_len = mg.end() - 1 - mg.start()
        self.msg_start = ms.start() + 1
        self.newline = _call_target(self.mem, self.msg_start)
        self.last_row = sc.group(1)[0]
        self.scroll_call = sc.end() - 3
        self.scroll = _call_target(self.mem, self.scroll_call)
        pos = POSITION.search(img)
        if not pos:
            raise ValueError("engine pieces not found")
        self.color_var, self.col_var, self.row_var = (struct.unpack("<H", pos.group(i))[0] for i in (1, 2, 3))
        wr = WRAP.search(img)
        geo_hits = list(GEOMETRY.finditer(img))
        geos = [(m.group(2)[0], m.group(3)[0]) for m in geo_hits]
        eng = [m for m in ENG_MSGS.finditer(img) if m.group(1) == m.group(3)]
        if not (wr and len(geos) == 2 and eng):
            raise ValueError("engine pieces not found")
        self.draw = _call_target(self.mem, wr.start())
        self.wrap_col = wr.start(2)                 # the bytes the geometry code rewrites
        self.restart_col = wr.start(3)
        self.start_col = self.newline + 2
        self.wrap_call = wr.end(4) - 3
        if self.mem[self.start_col - 1] != 0xB2:         # newline: push dx; mov dl, <start>
            raise ValueError("newline start column not found")
        self.box = (self.mem[self.wrap_col], self.mem[self.start_col])
        self.opening_box = [g for g in geos if g != self.box][0]
        self.opening_wrap_at = [m.start(2) for m, g in zip(geo_hits, geos) if g == self.opening_box][0]
        # the save and load prompts, each pointed at by its own code
        self.eng = [(m.start(2), struct.unpack("<H", m.group(2))[0]) for m in eng]
        self.words_at = struct.unpack("<H", w.group(1))[0] - self.shift
        self.word_init, self.word_init_len = w.start(), w.end() - w.start()
        self.verbs_var, self.nouns_var = (struct.unpack("<H", w.group(i))[0] for i in (2, 3))
        self.words_load = [l for l in self.loads if l["dest"] <= self.words_at < l["dest"] + 0x100 * l["count"]][0]
        self.font_load = [l for l in self.loads if l["dest"] <= self.sys_at < l["dest"] + 0x100 * l["count"]][0]
        self.title = TITLE_LOAD.search(boot)
        self.title_planes = TITLE_PLANES.search(boot)
        self.title_end = TITLE_END.search(boot)

    # ---- text blocks ---------------------------------------------------------------------------
    def word_lists(self):
        """(verbs, nouns), each a list of the raw words."""
        mem, p = self.mem, self.words_at
        out = []
        for _ in range(2):
            n, p = mem[p], p + 1
            words = []
            for _k in range(n):
                q = mem.index(0, p)
                words.append(bytes(mem[p:q]))
                p = q + 1
            out.append(words)
        return out

    def box_cols(self, opening=False):
        """Message cells per line in the main box, or in the opening's
        one-line window."""
        wrap, start = self.opening_box if opening else self.box
        return wrap - start

    def sys_messages(self):
        return self._messages(self.sys_at)

    def eng_messages(self):
        """The message tables inside the engine (the save and load prompts),
        one message each: their first messages, in table order."""
        return [self._messages(at)[0] for _ref, at in self.eng]

    def _messages(self, p):
        """A message table: a lead byte (the count), then zero-ended
        messages; the engine skips the lead byte."""
        mem = self.mem
        n, p = mem[p], p + 1
        out = []
        for _k in range(n):
            q = mem.index(0, p)
            out.append(bytes(mem[p:q]))
            p = q + 1
        return out

    def used_a(self):
        """The boot disk's sectors something reads: boot sector and title
        screen, saves, the three loads, the event directory with its event
        pictures and voice clips."""
        used = set(range(D88.index(0, 1), D88.index(0, 9))) | {D88.index(0, 16)}
        used |= set(range(D88.index(1, 1), D88.index(1, 8)))
        if self.title:
            t = self.title
            n = D88.index(t.group(2)[0] * 2 + t.group(3)[0], t.group(4)[0])
            used.update(range(n, n + t.group(1)[0]))
        for ld in self.loads:
            n = D88.index(ld["track"], ld["rec"])
            used.update(range(n, n + ld["count"]))
        d = self.disks[0].read(D88.index(10, 1), 3)
        used.update(range(D88.index(10, 1), D88.index(10, 4)))
        for base in (1, 0x251):
            for k in range(85):
                t, r, c = d[base + 3 * k:base + 3 * k + 3]
                if not c:
                    break
                n = D88.index(t, r)
                used.update(range(n, n + c))
        return used

    # ---- scenes --------------------------------------------------------------------------------
    def scene_disk(self):
        return self.disks[1]

    def directory(self):
        return self.scene_disk().read(0, 2)

    def scene_entries(self):
        d, out = self.directory(), []
        for k in range(85):
            e = tuple(d[1 + 3 * k:4 + 3 * k])
            if e == (0, 0, 0):
                break
            out.append(e)
        return out

    def picture_entries(self):
        d, out = self.directory(), []
        for k in range(85):
            e = tuple(d[0x101 + 3 * k:0x104 + 3 * k])
            if e == (0, 0, 0):
                break
            out.append(e)
        return out

    def scene(self, e):
        t, r, c = e
        return self.scene_disk().read(D88.index(t, r), c)


def scene_messages(data):
    """(start of the message count, [(start, end)] of the messages, end of
    the last one + 1): the messages follow the header, the event pictures
    and the command table."""
    p = 6 + data[5]
    a, b = data[p], data[p + 1]
    q = p + 6 * a + 4 * b + 2
    out, i = [], q + 1
    for _k in range(data[q]):
        j = data.index(0, i)
        out.append((i, j))
        i = j + 1
    return q, out, i


# ---- text <-> glyph bytes --------------------------------------------------------------------
def decode(data):
    out, i = [], 0
    while i < len(data):
        b = data[i]
        if b in (0xFE, 0xFF) and i + 1 < len(data):
            bank = b - 0xFD
            out.append(GLYPHS[bank].get(data[i + 1], "{G%d}" % (0x100 * bank + data[i + 1])))
            i += 2
            continue
        if 1 <= b <= 8:
            out.append("{A%d}" % b)
        else:
            out.append(_B1.get(b, "{G%d}" % b))
        i += 1
    return "".join(out)


def glyph_cells(data):
    """On-screen cells of a glyph string (controls take none)."""
    n, i = 0, 0
    while i < len(data):
        b = data[i]
        if b in (0xFE, 0xFF):
            n, i = n + 1, i + 2
        else:
            n, i = n + (b > 8), i + 1
    return n


_SUBST = {"’": "'", "‘": "'", "“": "'", "”": "'", '"': "'", "—": "-", "–": "-", "…": "...", ":": " -",
          ";": ",", "(": "（", ")": "）"}
_TOKEN = re.compile(r"\{A([1-8])\}")


class Encoder:
    """English -> glyph bytes for one game: letter pairs on PAIR_CODES."""

    def __init__(self, pair_codes):
        self.codes = list(pair_codes)

    def pair(self, a, b):
        n = len(font6x10.CHARS)
        p = font6x10.CHARS.index(a) * n + font6x10.CHARS.index(b)
        return bytes([self.codes[p // 254], 1 + p % 254])

    def units(self, text):
        """[(bytes, cells)]: letter pairs, the game's own glyphs, controls."""
        out, run = [], []

        def flush():
            while run:
                a = run.pop(0)
                b = run.pop(0) if run else " "
                out.append((self.pair(a, b), 1))

        pos = 0
        text = "".join(_SUBST.get(c, c) for c in text)
        while pos < len(text):
            m = _TOKEN.match(text, pos)
            if m:
                flush()
                out.append((bytes([int(m.group(1))]), 0))
                pos = m.end()
                continue
            ch = text[pos]
            pos += 1
            if ch in font6x10.CHARS:
                run.append(ch)
                continue
            flush()
            full = chr(ord(ch) + 0xFEE0) if "!" <= ch <= "~" else ch
            if full in _REV:
                bank, code = _REV[full]
                out.append(((bytes([0xFD + bank]) if bank else b"") + bytes([code]), 1))
            else:
                run.append("?")
        flush()
        return out

    def word(self, text):
        return b"".join(b for b, _n in self.units(text))

    def lay_out(self, text, cols=BOX_COLS):
        """A message: words wrapped to the box, each line but the last
        padded with blank glyphs to the edge, where the engine wraps."""
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
            body = b"".join(b for b, _n in us)
            n = sum(c for _b, c in us)
            if k < len(lines) - 1:
                body += b"\x20" * ((-n) % cols if n else cols)
            out += body
        return out

    def width(self, text):
        return sum(c for _b, c in self.units(text))


def _opening(cfg, ref):
    """Whether a message is shown in the opening's one-line window: the
    opening scenes' messages and the load prompt."""
    if ref.startswith("eng:"):
        return ref in cfg.get("opening_prompts", [])
    m = re.match(r"scene(\d+):", ref)
    return bool(m) and int(m.group(1)) in cfg.get("opening_scenes", [])


def pair_codes(game, used):
    """Bank-1 glyph numbers that are blank in the font and never used by the
    script: enough of them to number every letter pair."""
    font = game.mem[game.font_at - game.shift:]
    need = -(-len(font6x10.CHARS) ** 2 // 254)
    free = [c for c in range(9, 0xFE) if c != 0x20 and c not in used and not any(font[15 * c:15 * c + 15])]
    if len(free) < need:
        raise ValueError("only %d free glyph numbers for letter pairs; %d needed" % (len(free), need))
    return free[:need]


def _texts(game):
    """Every text the engine draws: (ref, kind, glyph bytes)."""
    verbs, nouns = game.word_lists()
    out = [("verb:%d" % i, "word", w) for i, w in enumerate(verbs)]
    out += [("noun:%d" % i, "word", w) for i, w in enumerate(nouns)]
    out += [("sys:%d" % i, "msg", m) for i, m in enumerate(game.sys_messages())]
    out += [("eng:%d" % i, "msg", m) for i, m in enumerate(game.eng_messages())]
    for k, e in enumerate(game.scene_entries()):
        data = game.scene(e)
        _q, msgs, _end = scene_messages(data)
        out += [("scene%d:%d" % (k, n), "msg", data[s:t]) for n, (s, t) in enumerate(msgs)]
    return out


def used_codes(game):
    """(bank-1 codes, highest bank-3 code) the script uses."""
    b1, top3 = set(), 0
    for _r, _k, t in _texts(game):
        i = 0
        while i < len(t):
            if t[i] in (0xFE, 0xFF):
                if t[i] == 0xFF and i + 1 < len(t):
                    top3 = max(top3, t[i + 1])
                i += 2
                continue
            b1.add(t[i])
            i += 1
    return b1, top3


# ---- extraction ------------------------------------------------------------------------------
def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    game = Game(_images(cfg, src))
    merged, order = {}, []

    def add(kind, jp, ref, cells):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = max(merged[key]["max_cells"], cells)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells}
        order.append(key)

    ti = _title(game)
    if ti:
        for row, col, n, text in title_segments(ti["codes"]):
            add("title", text, "title:%d:%d" % (row, col), n)
    for ref, kind, raw in _texts(game):
        if not raw:
            continue
        jp = decode(raw)
        add(kind, jp, ref, WORD_CELLS if kind == "word" else glyph_cells(raw))
    prefix = {"msg": "m", "word": "w", "title": "t"}
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
                for k in ("note",):
                    if k in prev:
                        e[k] = prev[k]
    doc = {"source_image_sha256": sha256(src), "strings": strings}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def roundtrip(game):
    """Rebuild every scene, the word block and the system messages from
    their own parts; True when all match the disk bytes."""
    for e in game.scene_entries():
        data = game.scene(e)
        q, msgs, end = scene_messages(data)
        rebuilt = data[:q + 1] + b"".join(data[s:t] + b"\0" for s, t in msgs) + data[end:]
        if rebuilt != data:
            return False
    verbs, nouns = game.word_lists()
    block = _word_block(verbs, nouns)
    if bytes(game.mem[game.words_at:game.words_at + len(block)]) != block:
        return False
    tables = [(game.sys_at, game.sys_messages())] + [(at, game._messages(at)) for _r, at in game.eng]
    for at, msgs in tables:
        block = _sys_block(msgs)
        if bytes(game.mem[at:at + len(block)]) != block:
            return False
    return True


def _word_block(verbs, nouns):
    return (bytes([len(verbs)]) + b"".join(w + b"\0" for w in verbs) +
            bytes([len(nouns)]) + b"".join(w + b"\0" for w in nouns))


def _sys_block(msgs):
    return bytes([len(msgs)]) + b"".join(m + b"\0" for m in msgs)


# ---- patch -----------------------------------------------------------------------------------
HELPERS = """
    cnt:
        .byte 0
    codes:
        .byte {codes}
    buf:
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    msgput:
        cmp word ptr [0x{bank:x}], 0
        jne mnorm
        CALLN find
        jc mnorm
        mov ah, byte ptr [bx + 1]
        CALLN build
        push bp
        mov bp, sp
        inc word ptr [bp + 4]
        pop bp
        mov dx, 0x{buf:x}
        .byte 0xc3
    mnorm:
        mov ah, 0
        mov dx, ax
        shl ax, 1
        shl ax, 1
        shl ax, 1
        shl ax, 1
        sub ax, dx
        mov dx, 0x{font:x}
        add dx, ax
        .byte 0xc3
    menuput:
        cmp dx, 0x{font:x}
        jne nnorm
        push dx
        CALLN find
        jc nfail
        add sp, 2
        mov ah, byte ptr [si]
        inc si
        CALLN build
        mov dx, 0x{buf:x}
        .byte 0xc3
    nfail:
        pop dx
    nnorm:
        mov ah, 0
        sub dx, ax
        shl ax, 1
        shl ax, 1
        shl ax, 1
        shl ax, 1
        add dx, ax
        .byte 0xc3
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
        mov dl, {ncodes}
        sub dl, cl
        pop cx
        pop si
        clc
        .byte 0xc3
    build:
        push ax
        push bx
        push cx
        push si
        push di
        mov cl, ah
        mov ch, 0
        dec cx
        mov al, dl
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
        pop cx
        pop bx
        pop ax
        .byte 0xc3
    scrl:
        cmp byte ptr cs:[0x{cnt:x}], {lines}
        jb go
        mov byte ptr cs:[0x{cnt:x}], 0
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
        mov byte ptr cs:[0x{cnt:x}], 0
        CALLN 0x{newline:x}
        inc byte ptr cs:[0x{cnt:x}]
        .byte 0xc3
    wrapnl:
        cmp byte ptr cs:[0x{start_col:x}], {box_start}
        jne one
        CALLN 0x{newline:x}
        inc byte ptr cs:[0x{cnt:x}]
        .byte 0xc3
    one:
        push ax
        push bx
        push cx
        push dx
    ofl:
        mov ah, 1
        int 0x18
        or bh, bh
        je owk
        mov ah, 0
        int 0x18
        jmp ofl
    owk:
        mov ah, 1
        int 0x18
        or bh, bh
        je owk
        mov ah, 0
        int 0x18
        mov bl, byte ptr cs:[0x{start_col:x}]
        mov bh, byte ptr [0x{row:x}]
        mov cx, word ptr [0x{color:x}]
        mov dx, 0x{blank:x}
    clr:
        CALLN 0x{draw:x}
        inc bl
        cmp bl, byte ptr cs:[0x{wrap_col:x}]
        jb clr
        pop dx
        pop cx
        pop bx
        pop ax
        .byte 0xc3
    table:
"""


def _helpers(game, org, codes, lines):
    # labels as operands would be memory references in this syntax, so the
    # addresses go in as numbers: once with stand-ins to place the labels
    # (every one is a 16-bit immediate, so nothing moves), then for real
    names = ("msgput", "menuput", "scrl", "reset", "wrapnl", "table", "buf", "codes", "cnt")
    fmt = dict(codes=", ".join("0x%02x" % c for c in codes), ncodes=len(codes),
               bank=game.bank_var, font=game.font_at, nchars=len(font6x10.CHARS),
               lines=lines, scroll=game.scroll, newline=game.newline,
               start_col=game.start_col, box_start=game.box[1], wrap_col=game.wrap_col,
               row=game.row_var, color=game.color_var, blank=game.font_at + 15 * 0x20, draw=game.draw,
               buf=0x1111, codes_at=0x1111, table=0x1111, cnt=0x1111)
    _code, labels = _asm16(HELPERS.format(**fmt), org, names)
    fmt.update(buf=labels["buf"], codes_at=labels["codes"], table=labels["table"], cnt=labels["cnt"])
    code, again = _asm16(HELPERS.format(**fmt), org, names)
    if again != labels or labels["table"] - org != len(code):
        raise ValueError("helper layout")
    return code + font6x10.table(), labels


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    game = Game(_images(cfg, src))
    used1, top3 = used_codes(game)
    enc = Encoder(pair_codes(game, used1))
    # the opening window's frame shows fewer cells than its wrap column allows;
    # the engine is set to wrap at the frame (no Japanese line reaches it)
    ocols = min(cfg.get("opening_cols", game.box_cols(True)), game.box_cols(True))
    by_ref, warnings = {}, []
    for e in doc["strings"]:
        text = e["en"]
        if mode == "pseudo":
            if e["kind"] == "word":
                # all letters, so the menu shows 8 cells of pairs: the id's digits as a-j
                tag = "W" + "".join("abcdefghij"[int(c)] for c in str(int(e["id"][1:])))
                text = (tag + " menuwordfiller")[:2 * WORD_CELLS]
            elif e["kind"] == "title":
                text = pseudo(e["id"], 2 * e["max_cells"], 1.0)[:2 * e["max_cells"]]
            else:
                # the controls kept: those leading the Japanese first, the rest after the filler
                lead = re.match(r"(?:\{A\d\})*", e["jp"]).group(0)
                rest = "".join("{A%s}" % t for t in _TOKEN.findall(e["jp"][len(lead):]))
                text = lead + pseudo(e["id"], 2 * e["max_cells"]) + rest
        if not text:
            continue
        if e["kind"] == "word":
            if enc.width(text) > WORD_CELLS:
                warnings.append("%s: %d cells, a menu word shows %d" % (e["id"], enc.width(text), WORD_CELLS))
            v, n = b"", 0
            for b, c in enc.units(text):
                if n + c > WORD_CELLS:
                    break
                v, n = v + b, n + c
        elif e["kind"] == "title":
            v = text
        else:
            # laid out per use: the opening's one-line window is wider than the box
            for r in e["refs"]:
                by_ref[r] = enc.lay_out(text, ocols if _opening(cfg, r) else game.box_cols())
            continue
        for r in e["refs"]:
            by_ref[r] = v
    a, b = game.disks[0], game.scene_disk()

    # scenes: rebuilt; a grown one moves to free sectors of the scene disk
    entries = game.scene_entries()
    used_b = {n for n in range(2)}
    for t, r, c in entries + game.picture_entries():
        n = D88.index(t, r)
        used_b.update(range(n, n + c))
    free_b = sorted(set(b.at) - used_b)
    d = bytearray(game.directory())
    for k, e in enumerate(entries):
        data = game.scene(e)
        q, msgs, end = scene_messages(data)
        body = b"".join(by_ref.get("scene%d:%d" % (k, n), data[s:t]) + b"\0" for n, (s, t) in enumerate(msgs))
        out = data[:q + 1] + body + data[end:].rstrip(b"\0")
        if len(out) > SCENE_ROOM:
            raise ValueError("scene %d is %d bytes; the scene buffer holds %d" % (k, len(out), SCENE_ROOM))
        need = -(-len(out) // SECTOR)
        t, r, c = e
        n, size = D88.index(t, r), c
        if need > c:
            n, size = _take_run(free_b, need), need
            if n is None:
                raise ValueError("no %d free sectors in a row for scene %d" % (need, k))
            t, r = divmod(n, SPT)
            d[1 + 3 * k:4 + 3 * k] = bytes([t, r + 1, need])
        b.write(n, bytes(out).ljust(size * SECTOR, b"\0"))
    b.write(0, bytes(d))

    # the text: the nouns go above the engine (its load grows to cover them),
    # the verbs, system messages and prompts to the word block
    verbs, nouns = game.word_lists()
    verbs = [by_ref.get("verb:%d" % i, w) for i, w in enumerate(verbs)]
    nouns = [by_ref.get("noun:%d" % i, w) for i, w in enumerate(nouns)]
    sysm = [by_ref.get("sys:%d" % i, m) for i, m in enumerate(game.sys_messages())]
    wl, eng = game.words_load, game.engine
    block = b"".join(w + b"\0" for w in verbs)
    sys_at = wl["dest"] + len(block)
    block += _sys_block(sysm)
    eng_at = []
    for i, m in enumerate(game.eng_messages()):
        eng_at.append(wl["dest"] + len(block))
        block += _sys_block([by_ref.get("eng:%d" % i, m)])
    room = game.font_at - game.shift - wl["dest"]          # up to the font
    if len(block) > room:
        raise ValueError("verbs, system messages and prompts are %d bytes; there are %d below the font"
                         % (len(block), room))
    noun_block = b"".join(w + b"\0" for w in nouns)
    nouns_at = 0x100 * eng["count"]
    if nouns_at + len(noun_block) > NOUN_END:
        raise ValueError("the nouns are %d bytes; there are %d above the engine"
                         % (len(noun_block), NOUN_END - nouns_at))
    need_w = -(-len(block) // SECTOR)
    need_e = -(-(nouns_at + len(noun_block)) // SECTOR)
    used = game.used_a()
    for ld, need in ((wl, need_w), (eng, need_e)):
        n0 = D88.index(ld["track"], ld["rec"])
        if set(range(n0 + ld["count"], n0 + need)) & used:
            raise ValueError("the load at track %d record %d cannot grow to %d sectors" % (ld["track"], ld["rec"], need))
    mem = game.mem
    mem[nouns_at:nouns_at + len(noun_block)] = noun_block
    a.write(D88.index(wl["track"], wl["rec"]), block.ljust(need_w * SECTOR, b"\0"))
    boot = bytearray(a.read(0, 2))
    boot[wl["at"] + 3] = need_w
    boot[eng["at"] + 3] = need_e
    struct.pack_into("<H", mem, game.sys_ref, sys_at + game.shift)
    for (ref, _at), at in zip(game.eng, eng_at):
        struct.pack_into("<H", mem, ref, at + game.shift)
    # the start-up scan that found the nouns after the verbs: now two pointers
    at = game.word_init
    code = (b"\xc7\x06" + struct.pack("<HH", game.verbs_var, wl["dest"] + game.shift) +
            b"\xc7\x06" + struct.pack("<HH", game.nouns_var, nouns_at) + b"\xc3")
    mem[at:at + game.word_init_len] = code.ljust(game.word_init_len, b"\x90")

    # helpers in the unused tail of font bank 3
    cave = game.font_at + 0x1E00 + 15 * (top3 + 1)
    cave = (cave + 15) & ~15
    code, labels = _helpers(game, cave, enc.codes, cfg.get("box_lines", 3))
    fl = game.font_load
    at_load = cave - game.shift
    if at_load + len(code) > fl["dest"] + 0x100 * fl["count"] or cave + len(code) > game.copy_end:
        raise ValueError("helpers need %d bytes; the font block has %d after its glyphs"
                         % (len(code), fl["dest"] + 0x100 * fl["count"] - at_load))
    if any(mem[at_load:at_load + len(code)]):
        raise ValueError("the helpers' place in the font block is not empty")
    mem[at_load:at_load + len(code)] = code

    def call(at, target, length):
        mem[at:at + length] = b"\xe8" + struct.pack("<H", (target - (at + 3)) & 0xFFFF) + b"\x90" * (length - 3)

    call(game.msg_glyph, labels["msgput"], game.msg_glyph_len)
    call(game.menu_glyph, labels["menuput"], game.menu_glyph_len)
    call(game.scroll_call, labels["scrl"], 3)
    mem[game.opening_wrap_at] = game.opening_box[1] + ocols
    call(game.msg_start, labels["reset"], 3)
    call(game.wrap_call, labels["wrapnl"], 3)
    a.write(D88.index(eng["track"], eng["rec"]), bytes(mem[eng["dest"]:eng["dest"] + 0x100 * need_e]))
    a.write(D88.index(fl["track"], fl["rec"]), bytes(mem[fl["dest"]:fl["dest"] + 0x100 * fl["count"]]))
    write_title(game, by_ref)
    a.write(0, bytes(boot))
    with open(dst, "wb") as f:
        f.write(a.raw)
    stem = os.path.splitext(dst)[0]
    for p, disk in zip(game.paths[1:], game.disks[1:]):
        with open("%s - %s" % (stem, os.path.basename(p)), "wb") as f:
            f.write(disk.raw)
    with open(os.path.join(os.path.dirname(os.path.abspath(dst)), "MTL_NOTE.TXT"), "w", encoding="ascii",
              newline="\r\n") as f:
        f.write(MTL_NOTE.format(title=cfg["title"]))
    for w in warnings:
        print("warning: " + w)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
