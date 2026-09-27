"""JAST's oldest self-booting engine on 2HD D88 floppies with 256-byte
sectors (Cosmos Club): extract/patch driver.  The engine family of
pc98tl/jast_ribbon.py (JIS words, low byte first; the character writes,
the line wrap and the menu draw are the same instructions), laid out
differently:

* Logical sectors are 256 bytes, 26 to a track side (sector n: track n // 26,
  record n % 26 + 1).  The boot sector loads the engine from sector 4; the
  engine's own reload code gives its offset.
* Two blobs are loaded whole at start into one segment: the scenes' command
  parts at offset 0 and, at offset 3000h, a text blob: a header of offsets
  (the word file's three tables and its end, then the end of each scene's
  text part), the word file (16-byte words of 8 JIS characters, 7 shown,
  and a list of system messages) and the scenes' text parts, which are
  messages ended by a zero word, found by count.  A scene's command part is
  copied to offset 0 of the engine segment (1 KB), its text part to 400h
  (3 KB), the word file to 1000h (4 KB).
* There are no control words and no colour codes in the text.

Patch.
* The text blob is rebuilt with the English and its header recomputed.  It
  may grow to the end of its segment (the running game leaves that memory
  alone); when it no longer fits its old sectors it moves to free ones (no
  table refers to them; one filler byte throughout) and its load call is
  updated.  The patcher refuses a text part or word file larger than its
  buffer, or a blob larger than the segment.
* Engine: every character write goes to one helper that writes a code whose
  first byte has bit 7 set as two ASCII letters in two half-width cells;
  the line scroll in the message draw goes through the pager (every third
  new line of a message waits for a key or a left click).  The helpers sit
  in the unused (zero) tail of the directory table.

game.json: as jast_boot, with "encoding": "jast_cosmos".
A string's ref is "scene<n>:<message number>", "word<table>:<entry>" or
"words:<message number>".
"""
import json
import os
import re
import struct

from .alice_sys2_tl import sha256
from .jast_boot import (Codec, MTL_NOTE, WORD_CELLS, LINE_COLS, _u16, _rel, _take_run,
                        messages, decode, cells, lay_out, encode_word, word_messages, _images)
from .jast_ribbon import DRAW_HELPERS, WRITE, WRAP, MSG_START

SECTOR = 256
SPT = 26
LOAD = re.compile(rb"\xb8(..)\xbd(..)\xb9(..)\xe8\x0a\x00\x72\x07\x40\x81\xc5\x00\x01\xe2\xf4\xcc", re.S)
# the two blob loads into one segment: command parts (bp = 0), text blob (bp = 3000h)
CMD_LOAD = re.compile(rb"\xb8\x00(.)\x8e\xc0\x33\xed\xbb(..)\xb9(..)\x33\xc0\xe8..\x07\x73", re.S)
TEXT_LOAD = re.compile(rb"\xb8\x00(.)\x8e\xc0\xbd(..)\xbb(..)\xb9(..)\x33\xc0\xe8..\x07\x72\x01\xc3", re.S)
# the scene copy: command part (size check), text part (size check, offset 3006h, to 400h),
# and for AL = FF the word file (size check, to 1000h)
COPY = re.compile(rb"\x81\xfd(..)\x77.\x33\xff\x8b\xcd\xf3\xa4\x26\x89\x2e..\xbe(..)\x8a\xc3\x32\xe4\xd1\xe0"
                  rb"\x03\xf0\x8b\x4c\x02\x8b\x34\x2b\xce\x81\xf9(..)\x77.\x81\xc6(..)\xbf(..)\xf3\xa4.."
                  rb".*?\x81\xf9(..)\x77.\x03\x34\xbf(..)\xf3\xa4", re.S)
# a directory lookup: 8-byte entries (disk, -, sector, count)
TABLE8 = re.compile(rb"\xbe(..)[^\xbe]{2,8}?\x32\xe4\xd1\xe0\xd1\xe0\xd1\xe0\x03\xf0", re.S)
# the save slots: bx = sector, cx = 2
SAVE = re.compile(rb"\xbb(..)\xb4[\x00\x01]\xb0\x00\xb9(..)\xbd", re.S)


class D88:
    """Logical 256-byte sectors of a D88 image, read and written in place."""

    def __init__(self, path):
        self.path = path
        self.raw = bytearray(open(path, "rb").read())
        self.at = {}
        for t in range(164):
            off = struct.unpack_from("<I", self.raw, 0x20 + 4 * t)[0]
            if not off or off >= len(self.raw):
                continue
            p = off
            ns = struct.unpack_from("<H", self.raw, p + 4)[0]
            for _ in range(ns):
                c, h, r = self.raw[p], self.raw[p + 1], self.raw[p + 2]
                size = struct.unpack_from("<H", self.raw, p + 14)[0]
                if size == SECTOR:
                    self.at[(c * 2 + h) * SPT + r - 1] = p + 16
                p += 16 + size
        self.count = max(self.at) + 1

    def read(self, lba, n):
        return b"".join(bytes(self.raw[self.at[s]:self.at[s] + SECTOR]) for s in range(lba, lba + n))

    def write(self, lba, data):
        data = data.ljust(-(-len(data) // SECTOR) * SECTOR, b"\0")
        for k in range(len(data) // SECTOR):
            o = self.at[lba + k]
            self.raw[o:o + SECTOR] = data[k * SECTOR:(k + 1) * SECTOR]


class Game:
    def __init__(self, paths):
        self.paths = list(paths)
        self.disks = [D88(p) for p in self.paths]
        d = self.disks[0]
        boot = d.read(0, d.count)
        m = [m for m in LOAD.finditer(boot) if _u16(m.group(3), 0) >= 8]
        if not m:
            raise ValueError("engine load code not found")
        self.lba, self.base, self.count = (_u16(m[0].group(k), 0) for k in (1, 2, 3))
        self.img = d.read(self.lba, self.count)
        c, t = CMD_LOAD.search(self.img), TEXT_LOAD.search(self.img)
        cp = COPY.search(self.img)
        if not (c and t and cp):
            raise ValueError("blob loads / scene copy not found")
        self.cmd_lba, self.cmd_count = _u16(c.group(2), 0), _u16(c.group(3), 0)
        self.text_at = _u16(t.group(2), 0)
        self.text_lba, self.text_count = _u16(t.group(3), 0), _u16(t.group(4), 0)
        self.text_load = t
        self.cmd_max, self.text_max, self.word_max = (_u16(cp.group(k), 0) for k in (1, 3, 6))
        self.tables = sorted({_u16(x.group(1), 0) for x in TABLE8.finditer(self.img)})
        self.saves = [(_u16(x.group(1), 0), _u16(x.group(2), 0)) for x in SAVE.finditer(self.img)]
        self.codec = Codec(jis=True, newline=False, colours={})

    def poke(self, addr, data):
        o = addr - self.base
        self.img = self.img[:o] + data + self.img[o + len(data):]

    def entries(self, table):
        out = []
        for k in range((0x240C - table) // 8 if table < 0x240C else 64):
            e = self.img[table - self.base + 8 * k:table - self.base + 8 * k + 8]
            if len(e) < 8:
                break
            out.append((e[0], _u16(e, 2), _u16(e, 4)))
        return out

    def table_tail(self, table):
        es = self.entries(table)
        last = max(k for k, e in enumerate(es) if any(e))
        start = table + 8 * (last + 1)
        end = start
        while end - self.base < len(self.img) and self.img[end - self.base] == 0 and end < table + 8 * len(es):
            end += 1
        return start, end

    def blob(self):
        return self.disks[0].read(self.text_lba, self.text_count)

    def layout(self, blob):
        """(word file (start, end) in the blob, [scene text (start, end)])."""
        hdr_end = _u16(blob, 0)
        offs = struct.unpack_from("<%dH" % (hdr_end // 2), blob, 0)
        scenes = []
        for a, b in zip(offs[3:], offs[4:]):
            if b < a or b > len(blob):
                break
            scenes.append((a, b))
        return (offs[0], offs[3]), scenes, offs

    def free_sectors(self):
        used = set(range(0, self.lba + self.count))
        used.update(range(self.cmd_lba, self.cmd_lba + self.cmd_count))
        used.update(range(self.text_lba, self.text_lba + self.text_count))
        for lba, n in self.saves:
            used.update(range(lba, lba + n))
        for t in self.tables:
            for disk, lba, n in self.entries(t):
                if disk == 1:
                    used.update(range(lba, lba + n))
        d = self.disks[0]
        return [s for s in range(d.count) if s not in used and s in d.at
                and len(set(d.read(s, 1))) == 1]


def _word_tables(blob, w):
    """The word file's tables inside the blob: offsets are blob-relative."""
    h = struct.unpack_from("<4H", blob, 0)
    return [(h[0], h[1]), (h[1], h[2])], (h[2], h[3])


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    game = Game(_images(cfg, src))
    blob = game.blob()
    words, scenes, _offs = game.layout(blob)
    merged, order = {}, []

    def add(kind, jp, ref, max_cells):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": max_cells}
        order.append(key)

    def real(jp):
        return re.sub(r"\{[A-Z]\d+\}|\s|　", "", jp)

    for k, (a, b) in enumerate(scenes):
        part = blob[a:b]
        for num, s, e in word_messages(part, (0, len(part))):
            jp = decode(part[s:e], game.codec)
            if real(jp):
                add("msg", jp, "scene%d:%d" % (k, num), 3 * LINE_COLS // 2)
    tables, mtab = _word_tables(blob, words)
    for t, (a, b) in enumerate(tables):
        for i, o in enumerate(range(a, b, 16)):
            jp = "".join(game.codec.to_text(blob[q:q + 2]) for q in range(o, o + 16, 2)
                         if game.codec.char_ok(blob[q:q + 2])).rstrip("　 ")
            if jp:
                add("word", jp, "word%d:%d" % (t, i), WORD_CELLS)
    for num, s, e in word_messages(blob, mtab):
        jp = decode(blob[s:e], game.codec)
        if real(jp):
            add("msg", jp, "words:%d" % num, 3 * LINE_COLS // 2)
    strings, counters = [], {"msg": 0, "word": 0}
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


def _rebuild(piece, mtab, by_ref, ref):
    """A list of zero-ended messages with the English put in."""
    out, pos = bytearray(), mtab[0]
    for num, s, e in word_messages(piece, mtab):
        en = by_ref.get(ref % num)
        out += piece[pos:s] + (en if en is not None else piece[s:e])
        pos = e
    out += piece[pos:mtab[1]]
    return bytes(out)


def patch_engine(game, box_lines=3):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm
    img, base = game.img, game.base
    ms = MSG_START.search(img)
    wr = WRAP.search(img, ms.start() if ms else 0)
    writes = list(WRITE.finditer(img))
    if not (ms and wr and writes and game.tables):
        raise ValueError("message draw not found")
    cave = game.table_tail(game.tables[0])
    fmt = dict(attr=_u16(writes[0].group(1), 0), cnt=cave[0], lines=box_lines,
               scroll=_rel(img, wr.start(1), base), cursor=_u16(ms.group(2), 0))
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    code, labels = _asm(ks, DRAW_HELPERS.format(**fmt), cave[0], ("w2", "scrl", "reset"))
    if len(code) > cave[1] - cave[0]:
        raise ValueError("helpers need %d bytes, the table tail has %d" % (len(code), cave[1] - cave[0]))
    if b"\x66" in code:
        raise ValueError("32-bit prefix in the helpers")
    game.poke(cave[0], code)

    def call_at(at, target, total):
        rel = (target - (base + at + 3)) & 0xFFFF
        game.poke(base + at, b"\xe8" + struct.pack("<H", rel) + b"\x90" * (total - 3))

    for w in writes:
        call_at(w.start(), labels["w2"], w.end() - w.start())
    game.poke(base + wr.start(1), struct.pack("<H", (labels["scrl"] - (base + wr.start(1) + 2)) & 0xFFFF))
    call_at(ms.start(1), labels["reset"], 5)


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    game = Game(_images(cfg, src))
    codec = game.codec
    by_ref, warnings = {}, []
    for e in doc["strings"]:
        if mode == "pseudo":
            if e["kind"] == "word":
                text = ("<%s>" % e["id"][1:])[:2 * WORD_CELLS]
            else:
                text = pseudo(e["id"], 2 * cells(e["jp"]))
        else:
            text = e["en"]
        if not text:
            continue
        if e["kind"] == "word":
            b = encode_word(text)
            if len(b) > 2 * WORD_CELLS:
                warnings.append("%s: %d letters, menu shows %d" % (e["id"], len(b), 2 * WORD_CELLS))
                b = b[:2 * WORD_CELLS]
            val = codec.ascii(b.decode("ascii").ljust(16))
        else:
            val = lay_out(text, codec)
        for r in e["refs"]:
            by_ref[r] = val
    blob = game.blob()
    words, scenes, offs = game.layout(blob)
    tables, mtab = _word_tables(blob, words)
    wfile = bytearray(blob[words[0]:mtab[0]])
    for t, (a, b) in enumerate(tables):
        for i, o in enumerate(range(a, b, 16)):
            v = by_ref.get("word%d:%d" % (t, i))
            if v is not None:
                wfile[o - words[0]:o - words[0] + 16] = v
    wfile += _rebuild(blob, mtab, by_ref, "words:%d")
    if len(wfile) > game.word_max:
        raise ValueError("word file is %d bytes; its buffer holds %d" % (len(wfile), game.word_max))
    parts = []
    for k, (a, b) in enumerate(scenes):
        part = _rebuild(blob[a:b], (0, b - a), by_ref, "scene%d:%%d" % k)
        if len(part) > game.text_max:
            raise ValueError("scene %d's text is %d bytes; its buffer holds %d" % (k, len(part), game.text_max))
        parts.append(part)
    # header: the word tables' offsets and end, then each scene's end
    hdr_len = offs[0]              # the header keeps its size (its first offset)
    new = bytearray(blob[:hdr_len])
    pos = hdr_len
    t_off = [tables[0][0], tables[1][0], mtab[0]]
    shift = pos - words[0]
    for i, o in enumerate(t_off):
        struct.pack_into("<H", new, 2 * i, o + shift)
    body = bytes(wfile)
    pos += len(body)
    struct.pack_into("<H", new, 6, pos)
    for k, part in enumerate(parts):
        body += part
        pos += len(part)
        struct.pack_into("<H", new, 8 + 2 * k, pos)
    blob_new = bytes(new) + body
    limit = 0x10000 - game.text_at - 1
    if len(blob_new) > limit:
        raise ValueError("text blob is %d bytes; its segment holds %d" % (len(blob_new), limit))
    need = -(-len(blob_new) // SECTOR)
    lba = game.text_lba
    if need > game.text_count:
        lba = _take_run(game.free_sectors(), need)
        if lba is None:
            raise ValueError("no %d free sectors in a row for the text blob" % need)
        t = game.text_load
        game.poke(game.base + t.start(3), struct.pack("<H", lba))
        game.poke(game.base + t.start(4), struct.pack("<H", need))
    game.disks[0].write(lba, blob_new)
    patch_engine(game, cfg.get("box_lines", 3))
    game.disks[0].write(game.lba, game.img)
    with open(dst, "wb") as f:
        f.write(game.disks[0].raw)
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
