"""JAST's older self-booting engine (Tenshi-tachi no Gogo III - Ribbon):
extract/patch driver.  The disk layout and the scene format are those of
the later builds in pc98tl/jast_boot.py (text in JIS words, low byte first,
wrapping at the box edge; no colour codes), with these differences:

* There is no scene table.  All scenes are one blob (a table of offsets,
  then the scenes back to back), loaded whole into its own 64 KB segment at
  start; a scene is copied from there to offset 0 of the engine segment
  when it is needed.  The blob fills its segment, so it cannot grow.
* The word file (verbs, nouns, system messages; 16-byte entries of 8 JIS
  characters, 7 shown) is loaded into the same segment first and copied
  to offset 800h, just above the 2 KB scene buffer.
* The message draw, the menu draw and the plain string draw each write
  the characters to the text layer themselves (the same few instructions
  in each).

Patch.
* Scenes are rebuilt with the English messages and written to free
  sectors of the boot disk (no table refers to them; one filler byte
  throughout), with a table of their places; the scene copy now reads the
  scene from disk into the scene buffer instead (the blob is still loaded,
  unused).
* The word file is rebuilt (the English messages of its message table) and
  copied to the top of the space below the engine instead of 800h, so the
  scene buffer gets everything below it; the engine's references to 800h
  (and its size check) are updated.
* Every character write goes to one helper that writes a code whose first
  byte has bit 7 set as two ASCII letters in two half-width cells (see
  jast_boot.Codec); the line scroll in the message draw goes through the
  same pager as in the later builds (every third new line of a message
  waits for a key or a left click).  The helpers and the scene table sit in
  the unused (zero) tails of the two directory tables, which stay zero in a
  running game.

game.json: as jast_boot, with "encoding": "jast_ribbon".
A string's ref is "scene<n>:<message number>", "word<table>:<entry>" or
"words:<message number>".
"""
import json
import os
import re
import struct

from .alice_sys2_tl import sha256
from .jast_boot import (Codec, LOAD, SECTOR, MTL_NOTE, TABLE, WORD_CELLS, LINE_COLS, _u16, _rel, _take_run,
                        messages, decode, cells, lay_out, encode_word, word_messages, _images)

# the scenario and word file loads: es = segment, bp = 0, bx = sector, cx = count
SEG_LOAD = re.compile(rb"\xb8\x00(.)\x8e\xc0\x33\xed\xbb(..)\xb9(..)\x33\xc0\xe8(..)\x07(\x72\x01\xc3|\x73\x02)", re.S)
# the word copy: table pointers rebased to 800h, size check, copy to 800h
WORD_COPY = re.compile(rb"\x8b\x44\x02\x2b\x04\x05(..)\x26\xa3..\x8b\x44\x04\x2b\x04\x05(..)\x26\xa3.."
                       rb"\x8b\x4c\x06\x2b\x0c\x81\xf9(..)\x77.\x8b\x34\xbf(..)\xf3\xa4", re.S)
# the verb table's fixed address in the menu draw
VERBS = re.compile(rb"\xbe(..)\x03\xf0\xba", re.S)
# the scene copy from the blob
FETCH = re.compile(rb"\x1e\x06\xbb\x00(.)\x8e\xdb\x8c\xcb\x8e\xc3\xfc\x8a\xd8\x33\xf6\x32\xe4\xd1\xe0\x03\xf0"
                   rb"\x8b\x6c\x02\x8b\x34\x2b\xee\x81\xfd..\x77.\x33\xff\x8b\xcd\xf3\xa4\x07\x1f"
                   rb"\xbe(.)\x00\xb8(.)\x00\x03\x04\xa3(..)\xc3", re.S)
# one character written to the text layer: word in ax (swapped here), attribute from memory
WRITE = re.compile(rb"\x86\xc4\x2c\x20\x26\x89\x05\x26\xc7\x45\x02\x20\x00\xa0(..)\x26\x88\x85\x00\x20"
                   rb"\x26\x88\x85\x02\x20\x83\xc7\x04", re.S)
# the message draw: start (line start saved), controls below 2000h, the wrap
MSG_START = re.compile(rb"\x8b\xf8(\x33\xc9\xa3(..))\xb8\x00\xa0\x8e\xc0\xad\x0b\xc0\x74."
                       rb"(?:\x80\xfc\x20|\x3d\x56\x21)", re.S)
WRAP = re.compile(rb"\xe8(..)\x8b\x3e..\x33\xc9", re.S)
# the read routine: ah = 0 read, al = disk - 1, bx = sector, cx = count, es:bp = buffer


# the character write, the pager on the line scroll and the message start
# (format keys: attr, cnt, lines, scroll, cursor)
DRAW_HELPERS = """
    cnt:
        .byte 0
    w2:
        test al, 0x80
        jnz asc
        xchg ah, al
        sub al, 0x20
        mov word ptr es:[di], ax
        mov word ptr es:[di + 2], 0x20
        jmp at
    asc:
        and al, 0x7f
        mov byte ptr es:[di], al
        mov byte ptr es:[di + 1], 0
        mov byte ptr es:[di + 2], ah
        mov byte ptr es:[di + 3], 0
    at:
        mov al, byte ptr [{attr}]
        mov byte ptr es:[di + 0x2000], al
        mov byte ptr es:[di + 0x2002], al
        add di, 4
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
        or bh, bh
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
        or bh, bh
        jne wkey
        in al, dx
        test al, 0x80
        jnz w1
    w2b:
        in al, dx
        test al, 0x80
        jz w2b
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
        xor cx, cx
        mov word ptr [{cursor}], ax
        .byte 0xc3
"""


class Game:
    def __init__(self, paths):
        self.paths = list(paths)
        self.disks = [bytearray(open(p, "rb").read()) for p in self.paths]
        boot = bytes(self.disks[0])
        m = [m for m in LOAD.finditer(boot) if _u16(m.group(3), 0) >= 8]
        if not m:
            raise ValueError("engine load code not found")
        self.lba, self.base, self.count = (_u16(m[0].group(k), 0) for k in (1, 2, 3))
        self.img_off = self.lba * SECTOR
        self.img = boot[self.img_off:self.img_off + self.count * SECTOR]
        loads = {mm.group(5)[:1]: mm for mm in SEG_LOAD.finditer(self.img)}
        if b"\x72" not in loads or b"\x73" not in loads:
            raise ValueError("scenario / word file load not found")
        sc, wd = loads[b"\x72"], loads[b"\x73"]
        self.blob_lba, self.blob_count = _u16(sc.group(2), 0), _u16(sc.group(3), 0)
        self.word_lba, self.word_count = _u16(wd.group(2), 0), _u16(wd.group(3), 0)
        self.word_load = wd
        self.read_call = _rel(self.img, sc.start(4), self.base)
        self.tables = sorted({_u16(t.group(1), 0) for t in TABLE.finditer(self.img)})
        f = FETCH.search(self.img)
        if not f:
            raise ValueError("scene copy not found")
        self.text_hdr = f.group(3)[0]
        self.codec = Codec(jis=True, newline=False, colours={})

    def _at(self, addr):
        return self.img_off + addr - self.base

    def poke(self, addr, data):
        o = self._at(addr)
        self.disks[0][o:o + len(data)] = data
        self.img = bytes(self.disks[0][self.img_off:self.img_off + self.count * SECTOR])

    def entries(self, table):
        out = []
        for k in range(128):
            e = self.img[table - self.base + 4 * k:table - self.base + 4 * k + 4]
            if len(e) < 4:
                break
            v = int.from_bytes(e[1:4], "little")
            out.append((e[0], v & 0xFFF, v >> 12))
        return out

    def scenes(self):
        """[(scene, data)] from the blob's offset table."""
        blob = bytes(self.disks[0][self.blob_lba * SECTOR:(self.blob_lba + self.blob_count) * SECTOR])
        n = _u16(blob, 0) // 2
        offs = struct.unpack_from("<%dH" % n, blob, 0)
        return [(k, blob[a:b]) for k, (a, b) in enumerate(zip(offs, offs[1:]))]

    def word_file(self):
        data = bytes(self.disks[0][self.word_lba * SECTOR:(self.word_lba + self.word_count) * SECTOR])
        h = struct.unpack_from("<4H", data, 0)
        return data, [(h[0], h[1]), (h[1], h[2])], (h[2], h[3])

    def free_sectors(self):
        used = set(range(0, self.lba + self.count))
        used.update(range(self.word_lba, self.word_lba + self.word_count))
        used.update(range(self.blob_lba, self.blob_lba + self.blob_count))
        for t in self.tables:
            for d, lba, cnt in self.entries(t):
                if d == 1:
                    used.update(range(lba, lba + cnt))
        img = self.disks[0]
        return [s for s in range(len(img) // SECTOR)
                if s not in used and len(set(img[s * SECTOR:(s + 1) * SECTOR])) == 1]

    def table_tail(self, table):
        """(start, end) of the zero tail after a directory table's last entry."""
        es = self.entries(table)
        last = max(k for k, e in enumerate(es) if any(e))
        start = table + 4 * (last + 1)
        end = start
        while end < table + 0x200 and self.img[end - self.base] == 0:
            end += 1
        return start, end


def _pad16(n):
    return (n + 15) & ~15


def patch_engine(game, scene_places, word_size, box_lines=3):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm
    img, base = game.img, game.base
    # word file: to the top of the space below the engine
    wc = WORD_COPY.search(img)
    vb = VERBS.search(img)
    old = _u16(wc.group(4), 0) if wc else None
    if not (wc and vb) or _u16(vb.group(1), 0) != old or _u16(img, 4) != old:
        raise ValueError("word file copy not found")
    words_at = base - _pad16(word_size)
    for grp in (1, 2, 4):
        game.poke(base + wc.start(grp), struct.pack("<H", words_at))
    game.poke(base + wc.start(3), struct.pack("<H", base - words_at))
    game.poke(base + vb.start(1), struct.pack("<H", words_at))
    game.poke(base + 4, struct.pack("<H", words_at))          # the verb table pointer's initial value
    # scene table: 3 bytes a scene (sector, count), in the first table's tail
    t0, t1 = game.table_tail(game.tables[0]), game.table_tail(game.tables[1])
    table = b"".join(struct.pack("<HB", lba, cnt) for lba, cnt in scene_places)
    if len(table) > t0[1] - t0[0]:
        raise ValueError("scene table needs %d bytes, the table tail has %d" % (len(table), t0[1] - t0[0]))
    game.poke(t0[0], table)
    img = game.img
    ms = MSG_START.search(img)
    wr = WRAP.search(img, ms.start() if ms else 0)
    writes = [m for m in WRITE.finditer(img)]
    fetches = [m for m in FETCH.finditer(img)]
    if not (ms and wr and writes and fetches):
        raise ValueError("message draw not found")
    attr = _u16(writes[0].group(1), 0)
    scroll = _rel(img, wr.start(1), base)
    cursor = _u16(ms.group(2), 0)
    text_ptr = _u16(fetches[0].group(4), 0)
    hdr = fetches[0].group(3)[0]
    src = DRAW_HELPERS + """
    fetch:
        push es
        push bx
        push cx
        push bp
    f1:
        xor ah, ah
        mov bx, ax
        shl bx, 1
        add bx, ax
        add bx, {table}
        mov cl, byte ptr cs:[bx + 2]
        xor ch, ch
        mov bx, word ptr cs:[bx]
        push cs
        pop es
        xor bp, bp
        push ax
        xor ax, ax
        CALLN 0x{read:x}
        pop ax
        jc f1
        pop bp
        pop cx
        pop bx
        pop es
        mov ax, word ptr [{hdrm2}]
        add ax, {hdr}
        mov word ptr [{text}], ax
        .byte 0xc3
    """
    fmt = dict(attr=attr, cnt=t1[0], lines=box_lines, scroll=scroll, cursor=cursor, table=t0[0],
               read=game.read_call, hdrm2=hdr - 2, hdr=hdr, text=text_ptr)
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    code, labels = _asm(ks, src.format(**fmt), t1[0], ("w2", "scrl", "reset", "fetch"))
    if len(code) > t1[1] - t1[0]:
        raise ValueError("helpers need %d bytes, the table tail has %d" % (len(code), t1[1] - t1[0]))
    if b"\x66" in code:
        raise ValueError("32-bit prefix in the helpers")
    game.poke(t1[0], code)

    def call_at(at, target, total):
        rel = (target - (base + at + 3)) & 0xFFFF
        game.poke(base + at, b"\xe8" + struct.pack("<H", rel) + b"\x90" * (total - 3))

    for w in writes:
        call_at(w.start(), labels["w2"], w.end() - w.start())
    game.poke(base + wr.start(1), struct.pack("<H", (labels["scrl"] - (base + wr.start(1) + 2)) & 0xFFFF))
    call_at(ms.start(1), labels["reset"], 5)
    for f in fetches:
        rel = (labels["fetch"] - (base + f.start() + 3)) & 0xFFFF
        game.poke(base + f.start(), b"\xe9" + struct.pack("<H", rel))
    return words_at


# ---- driver ------------------------------------------------------------------------------
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

    def real(jp):
        return re.sub(r"\{[A-Z]\d+\}|\s|　", "", jp)

    for k, data in game.scenes():
        for num, s, e in messages(data, game.text_hdr, game.codec)[0]:
            jp = decode(data[s:e], game.codec)
            if real(jp):
                add("msg", jp, "scene%d:%d" % (k, num), 3 * LINE_COLS // 2)
    data, tables, mtab = game.word_file()
    for t, (a, b) in enumerate(tables):
        for i, o in enumerate(range(a, b, 16)):
            jp = "".join(game.codec.to_text(data[q:q + 2]) for q in range(o, o + 16, 2)
                         if game.codec.char_ok(data[q:q + 2])).rstrip("　 ")
            if jp:
                add("word", jp, "word%d:%d" % (t, i), WORD_CELLS)
    for num, s, e in word_messages(data, mtab):
        jp = decode(data[s:e], game.codec)
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
            val = codec.ascii(b.decode("ascii").ljust(16))
        else:
            val = lay_out(text, codec)
        for r in e["refs"]:
            by_ref[r] = val
    # word file
    data, tables, mtab = game.word_file()
    words = bytearray(data)
    for t, (a, b) in enumerate(tables):
        for i, o in enumerate(range(a, b, 16)):
            v = by_ref.get("word%d:%d" % (t, i))
            if v is not None:
                words[o:o + 16] = v
    out, pos = bytearray(words[:mtab[0]]), mtab[0]
    for num, s, e in word_messages(data, mtab):
        en = by_ref.get("words:%d" % num)
        out += words[pos:s] + (en if en is not None else words[s:e])
        pos = e
    out += words[pos:mtab[1]]
    struct.pack_into("<H", out, 6, len(out))
    word_size = len(out) - _u16(out, 0)
    free = game.free_sectors()
    need = -(-len(out) // SECTOR)
    wlba = game.word_lba
    if need > game.word_count:
        wlba = _take_run(free, need)
        if wlba is None:
            raise ValueError("no %d free sectors in a row for the word file" % need)
        w = game.word_load
        game.poke(game.base + w.start(2), struct.pack("<H", wlba))
        game.poke(game.base + w.start(3), struct.pack("<H", need))
    game.disks[0][wlba * SECTOR:(wlba + need) * SECTOR] = bytes(out).ljust(need * SECTOR, b"\0")
    scene_limit = game.base - _pad16(word_size)
    # scenes: every one to free sectors, with its place in the new table
    places = []
    for k, data in game.scenes():
        body, pos = bytearray(), 0
        for num, s, e in messages(data, game.text_hdr, codec)[0]:
            en = by_ref.get("scene%d:%d" % (k, num))
            if en is None:
                continue
            body += data[pos:s] + en
            pos = e
        body += data[pos:]
        if len(body) > scene_limit:
            raise ValueError("scene %d is %d bytes; the scene buffer holds %d" % (k, len(body), scene_limit))
        n = -(-len(body) // SECTOR)
        lba = _take_run(free, n)
        if lba is None:
            raise ValueError("no %d free sectors in a row for scene %d" % (n, k))
        game.disks[0][lba * SECTOR:(lba + n) * SECTOR] = bytes(body).ljust(n * SECTOR, b"\0")
        places.append((lba, n))
    patch_engine(game, places, word_size, cfg.get("box_lines", 3))
    with open(dst, "wb") as f:
        f.write(game.disks[0])
    stem = os.path.splitext(dst)[0]
    for p, img in zip(game.paths[1:], game.disks[1:]):
        with open("%s - %s" % (stem, os.path.basename(p)), "wb") as f:
            f.write(img)
    with open(os.path.join(os.path.dirname(os.path.abspath(dst)), "MTL_NOTE.TXT"), "w", encoding="ascii",
              newline="\r\n") as f:
        f.write(MTL_NOTE.format(title=cfg["title"]))
    for w in warnings:
        print("warning: " + w)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
