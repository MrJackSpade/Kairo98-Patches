"""English for the FLZ0 engine (pc98tl/flz.py: Yumemizaka, Hiiragizaka no Kyuukan): strings.json in, a
patched image out.

Strings (refs FILE.TXB:block:number, or PROGRAM:offset):

* "msg": a message: `\\n` a new line (CR in the file).  The program draws ASCII half-width, breaks a
  line at `LINE` half-width cells (mid-word) and shows `ROWS` lines; the patcher breaks the English
  between words at `LINE` cells.  A message past `ROWS` lines is cut there and reported (the scripts
  name a message by its number: one can't become two).  `max_cells` is `LINE`.  `LINE` and `ROWS`
  are Yumemizaka's; a game's own are game.json's "line" and "rows" (Hiiragizaka no Kyuukan: 56, 4).
* "label": a string of the program's (its menus, its notices; `\\n` a new line): in place,
  `max_cells` its room in bytes; past it cut and reported.

English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else `?`.
A changed block is packed again.  The program loads a block whole into one 64 KB segment; when the
English takes a block past it, every TXB file is written in the wide form (`flz.wide_block`, not
packed) and the program is patched to read it (`widen`): a loader of its own reads the block into as
many paragraphs as it takes, and the lookup takes a message's place in paragraphs.
"""
import json
import os
import re
import struct

from . import flz as F
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "label": "l"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}
LINE = 58
ROWS = 5
PROG_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e\r\n])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                      rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e\r\n])*\x00")
KANA = re.compile(r"[ぁ-ヶ一-龠]")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def cells(text):
    return max((sum(1 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 2 for c in line)
                for line in text.split("\n")), default=0)


def show(b):
    return b.decode("cp932", "replace").replace("\r\n", "\n").replace("\r", "\n")


def encode(text):
    out = bytearray()
    for ch in text:
        for c in SUBST.get(ch, ch):
            if c == "\n":
                out += b"\r"
            elif " " <= c <= "~":
                out.append(ord(c))
            else:
                try:
                    out += c.encode("cp932")
                except UnicodeEncodeError:
                    out += b"?"
    return bytes(out)


def wrap(text, width=LINE):
    lines = []
    for para in text.split("\n"):
        line, col = [], 0
        for word in para.split(" "):
            w = cells(word)
            if line and col + 1 + w > width:
                lines.append(" ".join(line))
                line, col = [], 0
            line.append(word)
            col += w + (1 if len(line) > 1 else 0)
        lines.append(" ".join(line))
    return lines


def prog_strings(exe):
    """[(start, end)]: the program's NUL-ended strings with Japanese in its data group (from the
    start-up's mov dx, DGROUP); a run with no kana of JIS level-2 kanji alone is data, left out."""
    hdr = int.from_bytes(exe[8:10], "little") * 16
    if exe[hdr] != 0xBA:
        raise SystemExit("program: the start-up's data group not found")
    ds = hdr + int.from_bytes(exe[hdr + 1:hdr + 3], "little") * 16
    out = []
    for m in PROG_STR.finditer(exe, ds):
        t = m.group()[:-1].decode("cp932", "replace")
        if not KANA.search(t) or m.end() - m.start() <= 4:
            continue
        if not re.search("[ぁ-ヶ]", t) and all(c.encode("cp932", "replace") >= b"\x98\x9f"
                                               for c in t if ord(c) > 0x7F):
            continue
        out.append((m.start(), m.end() - 1))
    return out


# the message lookup: mov ax, [block's segment] / mov dx, [block's offset] / add dx, es:[bx] (its place)
LOOKUP = re.compile(rb"\xa1(..)\x8b\x16(..)\x26\x03\x17", re.S)
# the TXB block's load: push dx / push ax (the file's name) / call far the block loader / add sp, 0Ah /
# mov [block's segment], dx / mov [block's offset], ax
LOAD = rb"\x52\x50\x9a(....)\x83\xc4\x0a\x89\x16%s\xa3%s"
# the wide block loader: (file name far, block number) -> the block's segment:0 (0:0 when it fails);
# its retf a byte (keystone writes a 32-bit one)
WIDE_LOADER = """
    push bp
    mov bp, sp
    push ds
    push si
    push di
    lds dx, [bp+6]
    mov ax, 0x3d00
    int 0x21
    jc fail
    mov bx, ax
    mov dx, [bp+0xa]
    shl dx, 2
    xor cx, cx
    mov ax, 0x4200
    int 0x21
    sub sp, 8
    mov dx, sp
    push ss
    pop ds
    mov cx, 8
    mov ah, 0x3f
    int 0x21
    pop dx
    pop cx
    pop si
    pop di
    sub si, dx
    sbb di, cx
    mov ax, 0x4200
    int 0x21
    add si, 15
    adc di, 0
    shr si, 4
    shl di, 12
    or si, di
    push bx
    mov bx, si
    mov ah, 0x48
    int 0x21
    pop bx
    jc close
    mov di, ax
    mov ds, ax
more:
    mov cx, si
    cmp cx, 0x800
    jbe part
    mov cx, 0x800
part:
    sub si, cx
    push cx
    shl cx, 4
    xor dx, dx
    mov ah, 0x3f
    int 0x21
    pop cx
    mov ax, ds
    add ax, cx
    mov ds, ax
    test si, si
    jnz more
    mov ah, 0x3e
    int 0x21
    mov dx, di
    xor ax, ax
    jmp done
close:
    mov ah, 0x3e
    int 0x21
fail:
    xor ax, ax
    xor dx, dx
done:
    pop di
    pop si
    pop ds
    pop bp
    .byte 0xcb
"""


def widen(exe):
    """The program reading wide blocks (`flz.wide_block`): a loader of its own put after the load
    image (a segment of its own, the stack moved past it) in place of the TXB block's load, and the
    lookup taking a message's place as paragraphs from the block's segment."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    exe = bytearray(exe)
    hdr = struct.unpack_from("<14H", exe, 0)
    base = hdr[4] * 16
    m = LOOKUP.search(exe, base)
    if not m:
        raise SystemExit("program: the message lookup not found")
    seg, off = m.group(1), m.group(2)
    # mov ax, es:[bx] / add ax, [block's segment] / xor dx, dx (the loader's block starts at 0) / nop
    exe[m.start():m.end()] = b"\x26\x8b\x07\x03\x06" + seg + b"\x31\xd2\x90"
    calls = list(re.finditer(LOAD % (re.escape(seg), re.escape(off)), exe, re.S))
    if len(calls) != 1:
        raise SystemExit("program: the TXB block's load not found")
    end = (hdr[2] - (1 if hdr[1] else 0)) * 512 + hdr[1]
    if (end - base) % 16 or len(exe) < end:
        raise SystemExit("program: the load image doesn't end on a paragraph")
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_16).asm(WIDE_LOADER, 0)[0])
    code += bytes(-len(code) % 16)
    new_seg = (end - base) // 16
    exe[calls[0].start(1):calls[0].end(1)] = struct.pack("<HH", 0, new_seg)  # (its segment word relocated)
    exe[end:] = code
    struct.pack_into("<HH", exe, 2, len(exe) % 512, (len(exe) + 511) // 512)
    # the stack (from SS:0, past the data's end) moved past the loader; the start-up sizes the
    # program's memory from SS
    struct.pack_into("<H", exe, 0x0E, max(hdr[7], new_seg + len(code) // 16))
    return bytes(exe)


def txbs(vol, gd):
    return [n for n, _e in vol.walk() if n.upper().startswith(gd.upper() + "/") and n.upper().endswith(".TXB")]


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    gd = cfg["game_dir"]
    line, rows = cfg.get("line", LINE), cfg.get("rows", ROWS)
    prog = vol.read(gd + "/" + cfg["program"])
    merged, order = {}, []

    def add(kind, jp, ref, cells_, note=None):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], cells_)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells_}
        if note:
            merged[key]["note"] = note
        order.append(key)
    for s, e in prog_strings(prog):
        add("label", show(prog[s:e]), "%s:%05x" % (cfg["program"], s), e - s,
            "a string of the program's: its room in bytes (a letter one, a full-width character two)")
    for n in txbs(vol, gd):
        base = n[len(gd) + 1:]
        for k, strings in enumerate(F.txb(vol.read(n))):
            for j, s in enumerate(strings):
                jp = show(s)
                if jp.strip("　 \n"):
                    add("msg", jp, "%s:%d:%d" % (base, k, j), line,
                        "a message: %d lines of %d half-width cells at most" % (rows, line))
    counts, strings = {}, []
    for key in order:
        ent = merged[key]
        counts[ent["kind"]] = counts.get(ent["kind"], 0) + 1
        strings.append({"id": "%s%05d" % (PREFIX[ent["kind"]], counts[ent["kind"]]), **ent})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):
        old = {(x["kind"], x["jp"]): x for x in json.load(open(out, encoding="utf-8"))["strings"]}
        for ent in strings:
            prev = old.get((ent["kind"], ent["jp"]))
            if prev:
                ent["en"] = prev.get("en", "")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _pseudo(e):
    if e["kind"] == "label":
        lines = e["jp"].split("\n")
        room = max(1, (e["max_cells"] - (len(lines) - 1)) // len(lines))
        return "\n".join(pseudo(e["id"], room, 1.0)[:room] for _l in lines)
    return pseudo(e["id"], cells(e["jp"].replace("\n", "")))


def _cut(b, room):
    b = b[:room]
    while b and len(b.decode("cp932", "ignore").encode("cp932")) != len(b):
        b = b[:-1]
    return b


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"]
    line, rows = cfg.get("line", LINE), cfg.get("rows", ROWS)
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            if text:
                by_ref[r] = text
    warn = []
    prog_path = gd + "/" + cfg["program"]
    prog = vol.read(prog_path)
    out = bytearray(prog)
    for s, e in prog_strings(prog):
        ref = "%s:%05x" % (cfg["program"], s)
        en = by_ref.get(ref)
        if en is None:
            continue
        b = encode(en)
        if b"\r\n" in prog[s:e]:              # (a notice printed through DOS)
            b = b.replace(b"\r", b"\r\n")
        if len(b) > e - s:
            warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), e - s))
            b = _cut(b, e - s)
        out[s:e] = b.ljust(e - s, b"\0")
    files = {}
    for n in txbs(vol, gd):
        base = n[len(gd) + 1:]
        raw = vol.read(n)
        new = files[n] = {}
        for k, strings in enumerate(F.txb(raw)):
            for j, _s in enumerate(strings):
                ref = "%s:%d:%d" % (base, k, j)
                en = by_ref.get(ref)
                if en is None:
                    continue
                lines = wrap(en, line)
                if len(lines) > rows:
                    warn.append("%s: %d lines, cut to %d" % (ids[ref], len(lines), rows))
                    lines = lines[:rows]
                new[(k, j)] = encode("\n".join(lines))
    built, wide = {}, False
    for n, new in files.items():
        if new:
            try:
                built[n] = F.txb_build(vol.read(n), new)
            except ValueError:
                wide = True                 # (a block past 64 KB: every file in the wide form)
    if wide:
        out = bytearray(widen(bytes(out)))
        built = {n: F.txb_build(vol.read(n), new, wide=True) for n, new in files.items()}
    if bytes(out) != prog:
        vol.write(prog_path, bytes(out))
    for n, data in built.items():
        vol.write(n, data)
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
