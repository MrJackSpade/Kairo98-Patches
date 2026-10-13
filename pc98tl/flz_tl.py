"""English for the FLZ0 engine (pc98tl/flz.py: Yumemizaka): strings.json in, a patched image out.

Strings (refs FILE.TXB:block:number, or PROGRAM:offset):

* "msg": a message: `\\n` a new line (CR in the file).  The program draws ASCII half-width, breaks a
  line at `LINE` half-width cells (mid-word) and shows `ROWS` lines; the patcher breaks the English
  between words at `LINE` cells.  A message past `ROWS` lines is cut there and reported (the scripts
  name a message by its number: one can't become two).  `max_cells` is `LINE`.
* "label": a string of the program's (its menus, its notices; `\\n` a new line): in place,
  `max_cells` its room in bytes; past it cut and reported.

English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else `?`.
A changed block is packed again; a block past 65535 bytes is refused and names its strings.
"""
import json
import os
import re

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
    """[(start, end)]: the program's NUL-ended strings with Japanese in its data: from the largest run
    of them (its menus) on (a kanji-like run in the code before it left out)."""
    hits = [(m.start(), m.end() - 1) for m in PROG_STR.finditer(exe)
            if KANA.search(m.group()[:-1].decode("cp932", "replace")) and m.end() - m.start() > 4]
    groups, cur = [], []
    for s, e in hits:
        if cur and s - cur[-1][1] > 64:
            groups.append(cur)
            cur = []
        cur.append((s, e))
    if cur:
        groups.append(cur)
    if not groups:
        return []
    first = max(groups, key=len)[0][0]
    return [h for h in hits if h[0] >= first]


def txbs(vol, gd):
    return [n for n, _e in vol.walk() if n.upper().startswith(gd.upper() + "/") and n.upper().endswith(".TXB")]


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    gd = cfg["game_dir"]
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
                    add("msg", jp, "%s:%d:%d" % (base, k, j), LINE,
                        "a message: %d lines of %d half-width cells at most" % (ROWS, LINE))
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
    if bytes(out) != prog:
        vol.write(prog_path, bytes(out))
    for n in txbs(vol, gd):
        base = n[len(gd) + 1:]
        raw = vol.read(n)
        new = {}
        for k, strings in enumerate(F.txb(raw)):
            for j, _s in enumerate(strings):
                ref = "%s:%d:%d" % (base, k, j)
                en = by_ref.get(ref)
                if en is None:
                    continue
                lines = wrap(en)
                if len(lines) > ROWS:
                    warn.append("%s: %d lines, cut to %d" % (ids[ref], len(lines), ROWS))
                    lines = lines[:ROWS]
                new[(k, j)] = encode("\n".join(lines))
        if new:
            try:
                vol.write(n, F.txb_build(raw, new))
            except ValueError:
                raise SystemExit("%s: a block past 65535 bytes with the English; shorten these strings: %s" % (
                    base, ", ".join(sorted({ids[r] for r in by_ref if r.startswith(base + ":")}))))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
