"""English for Sogna's SGS21 (pc98tl/sgs21.py): strings.json in, a patched image out.

Strings (refs SCRIPT.WIN:offset in the unpacked script; the program's own PROGRAM:offset):

* "msg": a message (op 21h): any length.  `{N03}` is a speaker's slot (01h 03h), `{CLR}` the window's
  clear (＾), `{W}` the skipped ＄; `\\n` a new line (￥).  The program draws ASCII half-width
  itself; the patcher breaks the English between words at the window's width (op 20h's, in
  half-width cells, a line after the first starting at the indent, op 22h's), following the column
  from one message to the next as the program does, and when the window's rows are full it ends
  the message there and goes on in a new one after a key wait (op 0Eh) and a clear.  `max_cells`
  is a line's room (the width less the indent).
* "name": a slot's text (op 24h: the speakers' names, drawn where a message has `{N..}`): at most
  63 bytes (cut past it and reported); `max_cells` the Japanese's width (past it reported).
* "item": a menu's item (op 3Eh): at most 81 bytes (cut and reported); `max_cells` the menu's widest
  Japanese item (past it reported; the box grows with its longest item).
* "label": a string of the program's (its dialogs, NUL-ended): in place, `max_cells` its room in
  bytes; past it cut and reported.
* "console": a line the program prints through DOS before the game ($-ended): in place, its room
  in bytes; past it cut and reported.

English is ASCII (half-width; `\\` and `~`, which the font draws as other signs, written `/` and
`-`); another character is written full-width in Shift-JIS when it has one, else `?`.  A changed
script is laid out anew with its jumps moved, compressed again, and put at SGS.DAT's end; a script
past 65535 bytes is refused and names its strings.
"""
import json
import os
import re

from . import sgs21 as G
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "item": "i", "label": "l", "console": "c"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "\\": "/", "~": "-"}
CLEAR, NEWLINE, SKIP = b"\x81\x4f", b"\x81\x8f", b"\x81\x90"
TOKEN = re.compile(r"\{N(\d\d)\}|\{CLR\}|\{W\}|\n")
PROG_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                      rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*\x00")
CONSOLE = re.compile(rb"\$((?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])+)\r\n[\n\x07]?\$")
WORDY = re.compile(r"[ぁ-ヿ一-鿿Ａ-ｚ]")
KANA = re.compile(r"[ぁ-ヿ一-鿿]")
PAGE = b"\x00\x0e\x21" + CLEAR + b"\x00\x21"   # the message's end, a key wait, a clear, a new message


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def cells(text):
    return max((sum(1 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 2 for c in line)
                for line in text.split("\n")), default=0)


def encode(text):
    out = bytearray()
    for ch in text:
        for c in SUBST.get(ch, ch):
            if " " <= c <= "~":
                out.append(ord(c))
            else:
                try:
                    out += c.encode("cp932")
                except UnicodeEncodeError:
                    out += b"?"
    return bytes(out)


def show(b):
    """A message's bytes as strings.json shows them."""
    out, i = [], 0
    while i < len(b):
        c = b[i]
        if c == 1:
            out.append("{N%02d}" % b[i + 1])
            i += 2
        elif b[i:i + 2] == CLEAR:
            out.append("{CLR}")
            i += 2
        elif b[i:i + 2] == NEWLINE:
            out.append("\n")
            i += 2
        elif b[i:i + 2] == SKIP:
            out.append("{W}")
            i += 2
        elif 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            out.append(b[i:i + 2].decode("cp932", "replace"))
            i += 2
        else:
            out.append(chr(c) if 0x20 <= c < 0x7F else "{X%02X}" % c)
            i += 1
    return "".join(out)


def dat_path(gd):
    return gd + "/SGS.DAT"


def scripts(raw):
    return [nm for nm, *_r in G.dat(raw) if nm.upper().endswith(".WIN")]


def windows(d, ev):
    """{a message's start: (width, indent, rows)}: op 20h's and 22h's in effect, in place order."""
    width, indent, rows, out = 76, 0, 4, {}
    for e in ev:
        if e[0] == "op" and e[2] == 0x20:
            width, rows = d[e[1] + 5], d[e[1] + 6]
        elif e[0] == "op" and e[2] == 0x22:
            indent = d[e[1] + 1]
        elif e[0] == "text":
            out[e[1]] = (width, indent, rows)
    return out


def prog_strings(exe):
    """[(start, end)]: the program's NUL-ended strings, the largest run of them packed together."""
    hits = [(m.start(), m.end() - 1) for m in PROG_STR.finditer(exe)
            if WORDY.search(m.group()[:-1].decode("cp932", "replace")) and m.end() - m.start() > 4]
    groups, cur = [], []
    for s, e in hits:
        if cur and s - cur[-1][1] > 8:
            groups.append(cur)
            cur = []
        cur.append((s, e))
    if cur:
        groups.append(cur)
    return max(groups, key=len) if groups else []


def console_strings(exe):
    """[(start, end)]: the program's DOS lines with Japanese (each after the one before's "$")."""
    out, at = [], 0
    while True:
        m = CONSOLE.search(exe, at)
        if not m:
            return out
        if KANA.search(m.group(1).decode("cp932", "replace")):
            out.append((m.start(1), m.end(1)))
        at = m.end() - 1


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    gd = cfg["game_dir"]
    prog = vol.read(gd + "/" + cfg["program"])
    raw = vol.read(dat_path(gd))
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
        add("label", prog[s:e].decode("cp932", "replace"), "%s:%05x" % (cfg["program"], s), e - s,
            "a dialog's line of the program's: its room in bytes (a letter one, a full-width character two)")
    for s, e in console_strings(prog):
        add("console", prog[s:e].decode("cp932", "replace"), "%s:%05x" % (cfg["program"], s), e - s,
            "a line the program prints before the game: its room in bytes")
    for nm in scripts(raw):
        d = G.read(raw, nm)
        _p, ev = G.walk(d)
        win = windows(d, ev)
        menus = [e for e in ev if e[0] == "op" and e[2] == 0x3E]
        for e in ev:
            if e[0] == "op":
                continue
            ref = "%s:%04x" % (nm, e[1])
            jp = show(d[e[1]:e[2] - 1])
            if e[0] == "text" and jp.replace("{CLR}", "").replace("{W}", "").strip("　 \n"):
                w, ind, _rows = win[e[1]]
                add("msg", jp, ref, w - ind)
            elif e[0] == "item" and jp.replace("{W}", "").strip("　 "):
                add("name", jp, ref, cells(jp), "a slot's text (a speaker's name, `{N..}` in a message): "
                    "at most 63 bytes")
            elif e[0] == "menu":
                op = max(m for m in menus if m[1] < e[1])
                room = max(cells(show(d[x[1]:x[2] - 1])) for x in ev
                           if x[0] == "menu" and op[1] < x[1] < op[3])
                add("item", jp, ref, room, "a menu's item: the menu's widest Japanese item (at most 81 bytes)")
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
    if e["kind"] in ("label", "console"):
        return pseudo(e["id"], e["max_cells"], 1.0)[:max(1, e["max_cells"])]
    if e["kind"] in ("name", "item"):
        return pseudo(e["id"], max(2, e["max_cells"]), 1.0)[:max(2, e["max_cells"])]
    m = re.match(r"(?:\{N\d\d\}|\{CLR\})*", e["jp"])
    lead = m.group()
    return lead + pseudo(e["id"], cells(TOKEN.sub("", e["jp"])))


class Layout:
    """The program's column and row through a script's messages (see the module's docstring)."""

    def __init__(self, names):
        self.names = names              # {slot: its cells}
        self.col = self.row = 0

    def fresh(self):
        self.col = self.row = 0

    def message(self, text, width, indent, rows):
        """The English as message bytes, pages split off with PAGE."""
        out = bytearray()

        def newline():
            nonlocal out
            if self.row + 1 >= rows:
                out += PAGE
                self.row = 0
            else:
                out += NEWLINE
                self.row += 1
            self.col = 0
        pos, first = 0, True            # (a message going on from the one before on its line: a space)
        for m in list(TOKEN.finditer(text)) + [None]:
            chunk = text[pos:m.start() if m else len(text)]
            for k, word in enumerate(chunk.split(" ")):
                b = encode(word)
                w = cells(word)
                lead = 1 if (k or first) and self.col not in (0, indent) else 0
                if w:
                    first = False
                start = self.col if self.col else indent
                if w and start + lead + w > width and self.col not in (0, indent):
                    newline()
                    lead, start = 0, indent
                if lead:
                    out += b" "
                if w:
                    out += b
                    self.col = start + lead + w
                    while self.col > width:             # a word wider than a line: the program breaks it
                        self.col -= width - indent
                        self.row = min(self.row + 1, rows - 1)
            if m is None:
                break
            pos = m.end()
            tok = m.group()
            first = False
            if tok == "\n":
                newline()
            elif tok == "{CLR}":
                out += CLEAR
                self.fresh()
            elif tok == "{W}":
                out += SKIP
            else:
                slot = int(m.group(1))
                out += bytes([1, slot])
                self.col += self.names.get(slot, 0)
        return bytes(out)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"]
    prog_path = gd + "/" + cfg["program"]
    prog = vol.read(prog_path)
    by_ref, ids, rooms = {}, {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            rooms[r] = e["max_cells"]
            if text:
                by_ref[r] = text
    warn = []
    out_prog = bytearray(prog)
    for spans, fill in ((prog_strings(prog), b"\0"), (console_strings(prog), b" ")):
        for s, e in spans:
            ref = "%s:%05x" % (cfg["program"], s)
            en = by_ref.get(ref)
            if en is None:
                continue
            b = encode(en)
            if len(b) > e - s:
                warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), e - s))
                b = b[:e - s]
                while b and len(b.decode("cp932", "ignore").encode("cp932")) != len(b):
                    b = b[:-1]
            out_prog[s:e] = b.ljust(e - s, fill)
    if bytes(out_prog) != prog:
        vol.write(prog_path, bytes(out_prog))
    path = dat_path(gd)
    raw = vol.read(path)
    new = {}
    for nm in scripts(raw):
        d = G.read(raw, nm)
        _p, ev = G.walk(d)
        win = windows(d, ev)
        spans, names = {}, {}
        for e in ev:
            if e[0] == "item":
                slot = d[e[1] - 1] + 1
                ref = "%s:%04x" % (nm, e[1])
                en = by_ref.get(ref)
                b = encode(en) if en is not None else d[e[1]:e[2] - 1]
                if en is not None:
                    if len(b) > G.SLOT - 1:
                        warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), G.SLOT - 1))
                        b = b[:G.SLOT - 1]
                    elif cells(en) > rooms[ref]:
                        warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
                    spans[e[1]] = (e[2], b + b"\0")
                names[slot] = cells(show(b))
        lay = Layout(names)
        prev_op = None
        for e in ev:
            if e[0] == "op":
                if e[2] == 0x20:
                    lay.fresh()
                if e[2] == 0x21 and prev_op != 0x21:
                    lay.fresh()
                prev_op = e[2]
                continue
            ref = "%s:%04x" % (nm, e[1])
            en = by_ref.get(ref)
            if e[0] == "text":
                if en is None:
                    lay.message(show(d[e[1]:e[2] - 1]), *win[e[1]])
                    continue
                spans[e[1]] = (e[2], lay.message(en, *win[e[1]]) + b"\0")
            elif e[0] == "menu" and en is not None:
                b = encode(en)
                if len(b) > G.ITEM - 1:
                    warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), G.ITEM - 1))
                    b = b[:G.ITEM - 1]
                elif cells(en) > rooms[ref]:
                    warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
                spans[e[1]] = (e[2], b + b"\0")
        if not spans:
            continue
        out = G.rebuild(d, spans)
        if len(out) > G.ROOM:
            raise SystemExit("%s: %d bytes with its English, the program reads %d; shorten these strings: %s" % (
                nm, len(out), G.ROOM, ", ".join(sorted({ids[r] for r in by_ref if r.startswith(nm + ":")}))))
        new[nm] = out
    if new:
        vol.write(path, G.dat_build(raw, new))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), len(new)))
