"""English for Leaf's DR^2 Night Janki (NJ.EXE): strings.json in, a patched hard disk out.

NJ.EXE (a C program, its data group at 12F1h) keeps every text of the game in its data: the story's and
the matches' lines (each a line of the screen, drawn at its place: a speaker's name and its full-width
padding, then the speech; a speech's further lines are strings of their own), menus, the cards', the
characters' and the hands' names, and DOS's messages.  The program draws a string with one routine
(far 0C25h): a two-byte character from the CG ROM's kanji, a byte from its half-width row (09h) - but it
swaps the code's two bytes for a byte, so a byte was drawn as nothing; the patch takes the swap out
(`ANK_SWAP`), and English is ASCII, half-width.

Strings:
* l (line): a line of the screen, or a menu's, a name's, a hand's text: in place, up to max_cells letters (the
  Japanese's bytes: two letters for each full-width character).  Keep %s and %d.
* e (program): DOS's message (before "$"): in place, up to max_cells letters.
"""
import json
import os
import re

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .aypio import ascii_text
from .disk import DiskImage
from .text import pseudo

PREFIX = {"line": "l", "prog": "e"}
NOTE = {"line": "a line of the screen (or a menu's, a name's, a hand's text), drawn at its place: max_cells "
                "letters; keep %s and %d",
        "prog": "DOS's message, printed when a disk or file is missing: max_cells letters"}
TEXT = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e])*"
                  rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){2,}"
                  rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e])*")
JAPANESE = re.compile("[ぁ-ヺ一-鿿]")
KANA = re.compile("[ぁ-ヺ]")
LEAD_IN = re.compile(rb"[ \[%$@0-9a-z]*")   # ASCII a string may start with
# the string drawer's byte path: mov ah, 9 / cmp al, 0A0h / jb / add ax, 80h / xchg al, ah / mov dx, ax
ANK_SWAP = re.compile(rb"\xb4\x09\x3c\xa0\x72\x03\x05\x80\x00(\x86\xe0)\x8b\xd0")
DATA_SEG = re.compile(rb"\xb8(..)\x8e\xd8\x8e\xd0", re.S)   # the start-up's mov ax, DGROUP / mov ds, ax / mov ss, ax


def _path(cfg, name):
    return cfg["dir"] + "/" + name if cfg.get("dir") else name


def data_start(exe):
    """File offset of the data group (the start-up's DGROUP)."""
    hdr = int.from_bytes(exe[8:10], "little") * 16
    m = DATA_SEG.search(exe, hdr)
    if not m:
        raise SystemExit("NJ.EXE: the data group's segment not found")
    return hdr + int.from_bytes(m.group(1), "little") * 16


def texts(exe):
    """[(file offset, end, japanese, kind)]: the data group's strings with Japanese."""
    ds = data_start(exe)
    out = []
    for m in TEXT.finditer(exe, ds):
        # the string begins at its first two-byte character, or before it when the ASCII there is the
        # string's own (a format, spaces, brackets, @ new lines); other bytes before it (a marker the program
        # checks, a menu item's place) are not the string's
        first = next(i for i in range(m.start(), m.end()) if exe[i] >= 0x80)
        start = first
        if LEAD_IN.fullmatch(exe[m.start():first]):
            start = m.start()
        try:
            t = exe[start:m.end()].decode("cp932")
        except UnicodeDecodeError:
            continue
        if not JAPANESE.search(t):
            continue
        if not KANA.search(t) and any(len(c.encode("cp932")) == 2 and c.encode("cp932") >= b"\x98\x9f"
                                      for c in t):
            continue                # (bytes of data that read as JIS level-2 kanji)
        kind = "prog" if exe[m.end():m.end() + 1] == b"$" or t.endswith("$") else "line"
        out.append((start, m.end(), t.rstrip("$"), kind))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    exe = DiskImage(src).volumes[0].read(_path(cfg, cfg["program"]))
    merged, order = {}, []
    for s, e, jp, kind in texts(exe):
        key = (kind, jp)
        ref = "E:%05x" % s
        if key in merged:
            merged[key]["refs"].append(ref)
            continue
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": e - s, "note": NOTE[kind]}
        order.append(key)
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
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _cols(t):
    return sum(2 if ord(c) > 0x7F else 1 for c in t)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    p = _path(cfg, cfg["program"])
    exe = bytearray(vol.read(p))
    by_ref, warn = {}, []
    for e in doc["strings"]:
        text = pseudo(e["id"], _cols(e["jp"]), 1.0) if mode == "pseudo" else e["en"]
        if not text:
            continue
        b = ascii_text(text).replace("\n", " ").encode("ascii")
        if len(b) > e["max_cells"]:
            warn.append("%s: %d letters, room for %d (cut)" % (e["id"], len(b), e["max_cells"]))
            b = b[:e["max_cells"]]
        for r in e["refs"]:
            by_ref[r] = b
    if not by_ref:
        img.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    m = ANK_SWAP.search(exe)
    if not m:
        raise SystemExit("NJ.EXE: the string drawer's byte path not found")
    exe[m.start(1):m.end(1)] = b"\x90\x90"
    for s, e, _jp, kind in texts(bytes(vol.read(p))):
        b = by_ref.get("E:%05x" % s)
        if b is not None:
            # (a DOS message runs up to its "$": spaces after the English; a line ends at its NUL)
            exe[s:e] = b + (b" " if kind == "prog" else b"\0") * (e - s - len(b))
    vol.write(p, bytes(exe))
    vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
