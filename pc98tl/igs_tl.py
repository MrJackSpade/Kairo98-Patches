"""Strings and English for Silky's Image Gaming System (IGS.EXE: Koihime), its DIA scripts (pc98tl/igs.py).

The game is on floppies (game.json "disks", beside the first): every DIA file on them.  Strings
(refs FILE.DIA:address, the string's address in the script's data):

* "msg": a message, drawn by the script's routine for its window.  A window is vertical (its flags'
  bit 1: columns from the right, each a line read downwards; the program draws a half-width letter
  turned on its side, half a character's height) or horizontal; the script's last definition of it
  (system function 00) gives its size, at a script's start the usual one.  `max_cells` is the
  letters a line (a column) holds; the note gives the lines.  The patcher breaks the English between
  words, ending a line with "\\n", and when the window is full ends the message there and goes on
  after the script's own wait (the routines it calls after its messages in that window).  The
  message box at the right (window 0 and the other windows defined at x 530) is given six columns
  18 dots apart instead of four 27 apart (the same box: a turned letter is 16 dots across).
* "item": a choice's item (the script's menu routine; the menu is sized to its longest item, the
  scripts' width routine made to count a letter as 1, not 0); `max_cells` letters, past it reported.
* "label": another string the scripts draw (a page's title, a name entry's caption); `max_cells`
  the Japanese's width in half-width cells, past it reported.

Tokens: {N} / {M} the hero's names (%n, %m); {DF0}... a number the program fills in ($dF0...);
{S0} / {S1} the program's text style ($m0 / $m1).  A reading over kanji ($r reading $ kanji) shows as
kanji《reading》.  The English is ASCII; "$" and "%" (the program's codes) are written full-width.
"""
import bisect
import collections
import json
import os
import re
import struct

from . import igs as G
from .alice_sys2_tl import sha256
from .disk import DiskImage
from .text import pseudo

PREFIX = {"msg": "m", "item": "i", "label": "l"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "$": "＄", "%": "％"}
TOKEN = re.compile(r"\{N\}|\{M\}|\{DF\d+\}|\{S\d\}")
KANJI = re.compile(rb"[\x81-\x9f\xe0-\xef]")
FILE = re.compile(rb"\.(BPS|S4|DIA|M|EFC|DAT)", re.I)
ITEM = re.compile(rb"\x24\xf4\x85\xe7\x12\x04\x0c\x10\x1f\x00\xf1\x1b")    # (a menu's item routine)
# (the scripts' width routine, a menu's: a kanji 2 half-width cells, a name its name's, any other byte 0;
# the jump past a byte that is not "%" is sent to an added "width + 1")
WIDTH = re.compile(rb"\x09\x06\xf7\x12\xfe\x0c\xf7\x12\xfc\x0c\x0e\x7a\x00", re.S)
WIDTH_OTHER = re.compile(rb"\xe7\x12\xfa\x0e\x25\x11(..)", re.S)
ONE = bytes.fromhex("c712fc0e01")                     # (width += 1, as "c7 12 fc 0e 02" adds a kanji's 2)
ENTRY_VAR = 0x0700      # (a byte of the saved state no script uses: the body entry a part's file goes on at)
ITEM_ROOM = 40                                         # (a menu's column, within the screen's height)
NAME_CELLS = 10                                        # (a name as entered: five characters)
BOX_X = 530                                            # (the message box's left edge)
BOX = {"cols": 6, "pitch": 18}
DEFAULT = {0: (True, 44, BOX["cols"]), 3: (True, 20, 4), 4: (False, 16, 4), 5: (False, 42, 4)}


def _images(cfg, src):
    here = os.path.dirname(os.path.abspath(src))
    return [src] + [os.path.join(here, n) for n in cfg["disks"]]


def scripts(vols):
    """[(disk index, path, bytes)]: every DIA file."""
    out = []
    for k, v in enumerate(vols):
        for n, _e in v.walk():
            if n.upper().endswith(".DIA"):
                out.append((k, n, v.read(n)))
    return out


def show(s):
    """A string as it looks: the program's codes as tokens, a reading after its kanji."""
    out, i = "", 0
    while i < len(s):
        c = s[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF:
            out += s[i:i + 2].decode("cp932", "replace")
            i += 2
            continue
        if c == 0x25 and i + 1 < len(s) and s[i + 1] in b"nmaNMA":
            out += "{%s}" % chr(s[i + 1]).upper()
            i += 2
            continue
        if c == 0x24 and i + 1 < len(s):
            nx = s[i + 1]
            if nx == 0x72:                                   # $r reading $ kanji
                j = s.find(b"$", i + 2)
                if j > 0:
                    raw = s[i + 2:j]
                    reading = raw.replace(b"+", b"").replace(b">", b"").decode("cp932", "replace")
                    k = j + 1
                    base = ""
                    for _n in range(max(1, raw.count(b"+") + raw.count(b">"))):   # (a "+" or ">" a kanji)
                        if k < len(s) and (0x81 <= s[k] <= 0x9F or 0xE0 <= s[k] <= 0xEF):
                            base += s[k:k + 2].decode("cp932", "replace")
                            k += 2
                    out += base + "《%s》" % reading
                    i = k
                    continue
            m = re.match(rb"\$dF(\d+)", s[i:])
            if m:
                out += "{DF%s}" % m.group(1).decode()
                i += m.end()
                continue
            m = re.match(rb"\$m(\d)", s[i:])
            if m:
                out += "{S%s}" % m.group(1).decode()
                i += m.end()
                continue
        out += chr(c) if c < 0x80 else bytes([c]).decode("cp932", "replace")
        i += 1
    return out


def _defs(ops):
    """[(place, window, args)]: the script's window definitions (system function 00, its twelve
    arguments: the pushes before it, the last the first; None for one not an immediate)."""
    out = []
    for k, (a, op, b) in enumerate(ops):
        if op == 0x0D and b[1] == 0 and b[2] == 12 and k >= 12:
            args = []
            for a2, o2, b2 in ops[k - 12:k][::-1]:
                if b2[:2] == b"\x27\x0c":
                    args.append((a2, 0, 0))
                elif b2[:2] == b"\x27\x0e":
                    args.append((a2, struct.unpack_from("<b", b2, 2)[0], 1))
                elif b2[:2] == b"\x27\x0f":
                    args.append((a2, struct.unpack_from("<h", b2, 2)[0], 2))
                else:
                    args.append((a2, None, None))
            if args[0][1] is not None:
                out.append((a, args[0][1], args))
    return out


def _window(args):
    """(vertical, a line's letters, lines) of a window definition, None when not immediates."""
    vals = [v for _a, v, _n in args]
    if any(v is None for v in vals[1:10]):
        return None
    flags, width, rows = vals[1], vals[6], vals[7]
    if flags & 2:
        cols = BOX["cols"] if vals[4] == BOX_X else width
        return True, rows, cols
    return False, width, rows


def texts(code, data):
    """[(address, bytes, kind, window (vertical, letters, lines), start column, op index)]: the
    script's strings, in the order the code pushes them (a string the code pushes twice once)."""
    st = G.strings(data)
    ops = G.parse(code)
    dr = G.draws(code)
    items = {m.start() for m in ITEM.finditer(code)}
    other = set()                                   # (addresses the code uses but as pushes)
    for a, op, b in ops:
        if G.pushed(b) is None and op >= 0x20:
            for v in re.findall(rb"(?=(..))", b[1:], re.S):
                other.add(struct.unpack("<H", v)[0])
    refs = sorted({w for _a, _op, b in ops for w in G.words(b)})
    for at, s in st.items():                        # (a place inside a string the code uses: a table)
        k = bisect.bisect_right(refs, at)
        if k < len(refs) and refs[k] < at + len(s) + 1:
            other.add(at)
    defs = {a: (w, args) for a, w, args in _defs(ops)}
    win = {w: (g[0], g[1], g[2]) for w, g in DEFAULT.items()}
    out, seen, last = [], set(), {}
    for k, (a, op, b) in enumerate(ops):
        if a in defs:
            w, args = defs[a]
            g = _window(args)
            if g:
                win[w] = g
        v = G.pushed(b)
        if v is None or v not in st or v in seen or v in other:
            continue
        s = st[v]
        if not KANJI.search(s) or FILE.search(s):
            continue
        nx = ops[k + 1] if k + 1 < len(ops) else None
        kind, w = "label", None
        if nx and nx[1] == 0x0C:
            t = G.target(nx[0], nx[2])
            if t in dr:
                kind, w = "msg", dr[t]
            elif t in items:
                kind = "item"
        elif nx and nx[1] == 0x0E:
            kind, w = "msg", 0
        start = 0
        if kind == "msg":
            start = last.get(w, 0)                  # (after a label ending in a new line: its lines)
            last[w] = _columns(s, win[w]) if s.endswith(b"\n") else 0
        seen.add(v)
        out.append((v, s, kind, win.get(w) if w is not None else None, start, k))
    return out


def _columns(s, g):
    """The lines a Japanese string takes in a window."""
    n = 0
    for line in s.split(b"\n")[:-1] if s.endswith(b"\n") else s.split(b"\n"):
        h, i = 0, 0
        while i < len(line):
            if 0x81 <= line[i] <= 0x9F or 0xE0 <= line[i] <= 0xEF:
                h, i = h + 2, i + 2
            else:
                h, i = h + 1, i + 1
        n += max(1, -(-h // g[1]))
    return n


def _cells(s):
    h, i = 0, 0
    while i < len(s):
        if 0x81 <= s[i] <= 0x9F or 0xE0 <= s[i] <= 0xEF:
            h, i = h + 2, i + 2
        else:
            h, i = h + 1, i + 1
    return h


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vols = [DiskImage(p).volumes[0] for p in _images(cfg, src)]
    merged, order = {}, []

    def add(kind, jp, ref, room, note):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
        order.append(key)
    for _k, path, d in sorted(scripts(vols), key=lambda t: t[1]):
        data, code = G.load(d)
        name = path.rsplit("/", 1)[-1]
        for at, s, kind, g, start, _k2 in texts(code, data):
            ref = "%s:%04x" % (name, at)
            jp = show(s)
            if kind == "msg":
                room = g[1] - 3
                add("msg", jp, ref, room, "a message: %s, %d letters a line, %d lines a window; broken between "
                    "words, a new page after a click when the window is full" % (
                        "vertical (a line a column, the letters on their sides)" if g[0] else "horizontal",
                        room, g[2]))
            elif kind == "item":
                add("item", jp, ref, ITEM_ROOM, "a choice's item: a column of the menu (the program sizes the "
                    "menu to its longest item), %d letters at most" % ITEM_ROOM)
            else:
                add("label", jp, ref, _cells(s), "a string the script draws: one line, the Japanese's width "
                    "in letters")
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


# ---- English

def _units(text):
    """[(bytes, cells)]: a letter one cell, a full-width character two, a name token NAME_CELLS."""
    out, pos = [], 0
    for m in list(TOKEN.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        for ch in text[pos:end]:
            for c in SUBST.get(ch, ch):
                if " " <= c <= "~":
                    out.append((c.encode("ascii"), 1))
                else:
                    try:
                        b = c.encode("cp932")
                        out.append((b, len(b)))
                    except UnicodeEncodeError:
                        out.append((b"?", 1))
        if m:
            t = m.group()
            if t in ("{N}", "{M}"):
                out.append((b"%" + t[1].lower().encode(), NAME_CELLS))
            elif t.startswith("{DF"):
                out.append((b"$dF" + t[3:-1].encode(), 6))
            else:
                out.append((b"$m" + t[2:-1].encode(), 0))
            pos = m.end()
    return out


def layout(text, letters, lines, at=(0, 0)):
    """(pages, a click first, where it ends): a string drawn from `at` (the window's line and the
    letters on it), broken between words at `letters` cells, a line ended by "\\n"; when the window's
    `lines` are full, a new page (the script's click and a cleared window between).  A string ending
    in "\\n" leaves the next one at a new line."""
    pages, cur = [], b""
    row, col = at
    first = row >= lines
    if first:
        row, col = 0, 0

    def brk():                                  # (the next line; a new page past the window's last)
        nonlocal row, col, cur
        if row + 1 >= lines:
            pages.append(cur)
            cur, row, col = b"", 0, 0
        else:
            cur += b"\n"
            row, col = row + 1, 0
    paras = text.split("\n")
    end_nl = len(paras) > 1 and paras[-1] == ""
    if end_nl:
        paras = paras[:-1]
    for para_n, para in enumerate(paras):
        if para_n:
            brk()
        for w_n, word in enumerate(para.split(" ")):
            us = _units(word)
            n = sum(c for _b, c in us)
            sep = 1 if w_n and col else 0
            if col and col + sep + n > letters:
                brk()
                sep = 0
            if sep:
                cur += b" "
                col += 1
            for b, c in us:
                if col and col + c > letters:
                    brk()
                cur += b
                col += c
    if end_nl:                                  # (the next string at a new line: maybe past the last)
        cur += b"\n"
        row, col = row + 1, 0
    pages.append(cur)
    if len(pages) > 1 and not first and at != (0, 0):
        return layout(text, letters, lines, (lines, 0))     # (not room for it all: from a new page)
    return pages, first, (row, col)


def jp_layout(s, letters, lines, at=(0, 0)):
    """Where a Japanese string drawn from `at` ends (the program's own breaks: a character two cells)."""
    row, col = at
    if row >= lines:
        row, col = 0, 0
    parts = s.split(b"\n")
    for n, part in enumerate(parts):
        if n:
            row, col = row + 1, 0
        i = 0
        while i < len(part):
            c = 2 if (0x81 <= part[i] <= 0x9F or 0xE0 <= part[i] <= 0xEF) else 1
            if col + c > letters + 1:
                row, col = row + 1, 0
            col += c
            i += c
    return row, col


def encode_line(text):
    return b"".join(b for b, _c in _units(text.replace("\n", " "))) or b" "


# ---- the patch

def _push(v):
    return b"\x27\x0c" if v == 0 else b"\x27\x0e" + bytes([v]) if v < 0x80 else b"\x27\x0f" + struct.pack("<H", v)


def _wait_clear(w):
    """A click in window w and the window cleared (system functions 0B and 03, as the scripts' own
    routine after a message does)."""
    return _push(w) + b"\x0d\x0b\x01\x32" + _push(w) + b"\x0d\x03\x01\x32"


def _routine(moved_pages, draw, w, first, at):
    """A routine at `at` drawing the pages in window w through its message routine `draw`, a click
    and a cleared window between them (and before the first when `first`)."""
    out = bytearray()
    for n, p in enumerate(moved_pages):
        if n or first:
            out += _wait_clear(w)
        out += b"\x27\x0f" + struct.pack("<H", p)
        out += b"\x0c" + struct.pack("<h", draw - (at + len(out) + 3))
        out += b"\x32"
    out += b"\x04"
    return bytes(out)


def _clears(ops):
    """{routine: windows}: the routines that clear or open windows (system functions 01-03 with a
    window pushed), and {op index: window} for such a call made directly."""
    starts = G.regions(ops)
    size = collections.Counter(G._owner(starts, a) for a, _op, _b in ops)
    direct, by = {}, {}
    for k, (a, op, b) in enumerate(ops):
        if op == 0x0D and b[1] in (1, 2, 3) and b[2] == 1 and k:
            pb = ops[k - 1][2]
            w = 0 if pb[:2] == b"\x27\x0c" else pb[2] if pb[:2] == b"\x27\x0e" else None
            if w is not None:
                direct[k] = w
                r = G._owner(starts, a)
                if size[r] < 20:                    # (a small routine: a clear)
                    by.setdefault(r, set()).add(w)
    return by, direct, starts


def _events(code, ops):
    """[(op index, "draw", window, string address, call index) or (op index, "clear", window, None,
    None) or (op index, "window", window, args, None)]: in the code's order."""
    dr = G.draws(code)
    by, direct, starts = _clears(ops)
    defs = {a: (w, args) for a, w, args in _defs(ops)}
    out = []
    for k, (a, op, b) in enumerate(ops):
        if a in defs:
            out.append((k, "window", defs[a][0], defs[a][1], None))
        if op == 0x0C:
            t = G.target(a, b)
            if t in dr and k and G.pushed(ops[k - 1][2]) is not None:
                out.append((k - 1, "draw", dr[t], G.pushed(ops[k - 1][2]), k))
            elif t in by and t not in dr:
                for w in sorted(by[t]):
                    out.append((k, "clear", w, None, None))
        elif k in direct and G._owner(starts, a) not in by:
            out.append((k, "clear", direct[k], None, None))
    return out


def _box(code, ops):
    """The code with the message box's windows given BOX's columns: their width and pitch pushes."""
    out = bytearray(code)
    for a, w, args in _defs(ops):
        g = [v for _a, v, _n in args]
        if g[4] != BOX_X or g[1] is None or not g[1] & 2:
            continue
        for idx, val in ((6, BOX["cols"]), (8, BOX["pitch"])):
            pa, v, n = args[idx]
            if n == 1:
                out[pa + 2] = val
            elif n == 2:
                struct.pack_into("<h", out, pa + 2, val)
            else:
                raise ValueError("the box's window at %X: argument %d not an immediate" % (a, idx))
    return bytes(out)


def _pseudo(e):
    jp = e["jp"]
    lead = "".join(re.findall(r"^(?:\{[A-Z]+\d*\})+", jp)) if jp.startswith("{") else ""
    body = re.sub(r"《[^》]*》", "", TOKEN.sub("", jp)).replace("\n", "")
    if e["kind"] == "msg":
        n = 2 * len(body)
        tail = "\n" if jp.endswith("\n") else ""
        return lead + pseudo(e["id"], n) + tail
    return pseudo(e["id"], 2 * len(body))


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    paths = _images(cfg, src)
    imgs = [DiskImage(p) for p in paths]
    vols = [i.volumes[0] for i in imgs]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn, writes = [], {}
    for k, path, d in scripts(vols):
        name = path.rsplit("/", 1)[-1]
        data, code = G.load(d)
        ops = G.parse(code)
        found = texts(code, data)
        if not any("%s:%04x" % (name, at) in by_ref for at, *_r in found):
            continue
        kinds = {at: (kind, s) for at, s, kind, _g, _st, _i in found}
        text = {}
        for at, (kind, s) in kinds.items():
            ref = "%s:%04x" % (name, at)
            if ref in by_ref:
                t = by_ref[ref]
                if kind == "msg" and s.endswith(b"\n") and not t.endswith("\n"):
                    t += "\n"                       # (the next string at a new line, as the Japanese)
                text[at] = t
        new, paging = {}, []
        win = {w: g for w, g in DEFAULT.items()}
        at_ = {w: (0, 0) for w in DEFAULT}
        drawn = set()
        for k2, ev, w, arg, call in _events(code, ops):
            if ev == "window":
                g = _window(arg)
                if g:
                    win[w] = g
                continue
            if ev == "clear":
                at_[w] = (0, 0)
                continue
            if w not in win:
                continue
            g = win[w]
            letters, lines = g[1] - 3, g[2]
            if arg not in kinds or kinds[arg][0] != "msg":
                s = data[arg - G.DATA_AT:].split(b"\0", 1)[0] if G.DATA_AT <= arg < G.DATA_AT + len(data) else b""
                at_[w] = jp_layout(s, letters, lines, at_[w])
                continue
            if arg not in text:
                at_[w] = jp_layout(kinds[arg][1], letters, lines, at_[w])
                continue
            pages, first, end = layout(text[arg], letters, lines, at_[w])
            at_[w] = end
            drawn.add(arg)
            if arg not in new and len(pages) == 1 and not first:
                new[arg] = pages[0]
            elif not (len(pages) == 1 and not first and new.get(arg) == pages[0]):
                new.setdefault(arg, pages[0])
                paging.append((arg, ops[call][0], G.target(ops[call][0], ops[call][2]), w, first, pages))
        for at, (kind, s) in kinds.items():
            if at not in text or at in new:
                continue
            e = ids["%s:%04x" % (name, at)]
            if kind == "msg":                       # (a message the code draws another way: one page)
                g = win.get(0)
                pages, _f, _e = layout(text[at], g[1] - 3, g[2])
                if len(pages) > 1:
                    warn.append("%s: %d pages, one shown (drawn outside the message routines)" % (
                        e["id"], len(pages)))
                new[at] = pages[0]
            else:
                b = encode_line(text[at])
                if _cells(b) > e["max_cells"]:
                    warn.append("%s: %d letters, room for %d" % (e["id"], _cells(b), e["max_cells"]))
                new[at] = b
        stem = name.rsplit(".", 1)[0]
        try:
            parts = _parts(d, ops, new, paging, {at for at, *_r in found},
                           lambda i: name if i == 0 else "%s_%d.DIA" % (stem[:6], i + 1))
        except ValueError as ex:
            raise SystemExit("%s: %s; shorten its strings" % (name, ex))
        if len(parts) > 1:
            warn.append("%s: split into %s" % (name, ", ".join(p for p, _d in parts)))
        folder = path.rsplit("/", 1)[0] + "/" if "/" in path else ""
        taken = {n.upper() for _k, n, _d in scripts(vols)}
        for p, out in parts:
            if p != name and (folder + p).upper() in taken:
                raise SystemExit("%s: its part's name %s is taken" % (name, p))
            writes.setdefault(k, []).append((folder + p, out, p == name))
    for k, files in writes.items():                 # (IGS-DOS reads a file as one run of clusters: the
        for path, _out, old in files:               # changed files freed first, then each written
            if old:                                 # into a run, the longest first)
                vols[k].release(path)
        for path, out, old in sorted(files, key=lambda f: -len(f[1])):
            try:
                if old:
                    vols[k].write_run(path, out)
                else:
                    vols[k].create(path, out, contiguous=True)
            except IOError as ex:
                raise SystemExit("disk %d: %s" % (k + 1, ex))
    stem = os.path.splitext(dst)[0]
    for n, (p, img) in enumerate(zip(paths, imgs)):
        img.save(dst if n == 0 else "%s - %s" % (stem, os.path.basename(p)))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))


def _reach(ops, roots, main, others):
    """The routines the roots reach through calls, the main routine's calls of `others` not followed."""
    starts = G.regions(ops)
    calls = {}
    for a, op, b in ops:
        if op == 0x0C:
            calls.setdefault(G._owner(starts, a), set()).add(G.target(a, b))
    seen, todo = set(), list(roots)
    while todo:
        r = todo.pop()
        if r in seen:
            continue
        seen.add(r)
        todo.extend(t for t in calls.get(r, ()) if not (r == main and t in others))
    return seen


def _parts(d, ops, new, paging, texts_at, name):
    """[(file name, bytes)]: the script with its new strings (the box widened, long messages paged
    through routines added after the code); when past its segment, in parts (pc98tl/igs.py: the main
    routine's parts, each part's file with the strings its routines use, the main routine's calls of
    another part's routine going to that part's file)."""
    starts = G.regions(ops)
    data, code = G.load(d)
    d2 = G.save(data, _box(code, ops))

    def one(live, chains, enters=(), inline=(), leaves=(), dispatch=()):
        real = {a: s for a, s in new.items() if live is None or a in live}
        drop = set() if live is None else {a for a in texts_at if a not in live}
        poked = [(c, c + n) for c, n, _p in inline] + [(c, c + n) for c, n, _i, _p in leaves]
        pg = [p for p in paging if (live is None or p[0] in live)
              and not any(lo <= p[1] < hi for lo, hi in poked)]
        after = [p for p in pg if len(p[5]) == 1 and p[4] and new.get(p[0]) == p[5][0]]
        pg = [p for p in pg if p not in after]              # (a click first, then the string as it is)
        more, keys = {}, {}
        for n, (_at, _site, _draw, _w, _first, pages) in enumerate(pg):
            keys[n] = []
            for p in pages:
                key = 0x10000 + len(more)                   # (a page's string: no old place)
                more[key] = p
                keys[n].append(key)
        for j, (_site, pname) in enumerate(chains):
            more[0x20000 + j] = pname.encode("ascii")
        for j, (_cut, _n, pname) in enumerate(inline):
            more[0x30000 + j] = pname.encode("ascii")
        for j, (_c, _n, _i, pname) in enumerate(leaves):
            more[0x40000 + j] = pname.encode("ascii")
        calls, stubs = {}, {}

        def pokes(moved):                                   # (go on in another part's file: function 0F,
            out = {c: b"\x27\x0f" + struct.pack("<H", moved[0x30000 + j]) + b"\x0d\x0f\x01\x32"
                   + b"\x02" * (n - 8) for j, (c, n, _p) in enumerate(inline)}    # whole ops padded)
            for c, n, _i, _p in leaves:                     # (a body another part has: through a stub)
                out[c] = b"\x0e" + struct.pack("<h", stubs[c] - (c + 3)) + b"\x02" * (n - 3)
            return out

        def extra(moved, place):
            out = bytearray()
            for n, (_at, site, draw, w, first, _pages) in enumerate(pg):
                calls[site] = place + len(out)
                out += _routine([moved[kk] for kk in keys[n]], draw, w, first, place + len(out))
            shared = {}
            for _at, site, draw, w, _first, _pages in after:
                if (draw, w) not in shared:                 # (one per window: its draw after a click)
                    shared[(draw, w)] = place + len(out)
                    out += b"\x24\xf4\x85" + _wait_clear(w) + b"\x27\x12\x04"
                    out += b"\x0c" + struct.pack("<h", draw - (place + len(out) + 3))
                    out += b"\x32\x34\x04"
                calls[site] = shared[(draw, w)]
            for j, (site, _pname) in enumerate(chains):
                calls[site] = place + len(out)             # (go to the part's file: function 0F)
                out += b"\x27\x0f" + struct.pack("<H", moved[0x20000 + j]) + b"\x0d\x0f\x01\x04"
            for site, prologue, cut in enters:
                calls[site] = place + len(out)             # (the routine entered at a cut)
                out += prologue
                out += b"\x0e" + struct.pack("<h", cut - (place + len(out) + 3))
            for j, (c, _n, i, _p) in enumerate(leaves):    # (the entry's number kept, the part's file)
                stubs[c] = place + len(out)
                out += b"\xf7\x0b" + struct.pack("<H", ENTRY_VAR) + b"\x0e" + bytes([i])
                out += b"\x27\x0f" + struct.pack("<H", moved[0x40000 + j]) + b"\x0d\x0f\x01\x04"
            for site, r_at, prologue, entries in dispatch:  # (the routine called: at the entry kept,
                calls[site] = place + len(out)             # if one of this part's, else from its start)
                for i, at in entries:
                    out += b"\xe7\x0b" + struct.pack("<H", ENTRY_VAR) + b"\x0e" + bytes([i])
                    skip = len(out)
                    out += b"\x11\x00\x00"
                    out += b"\xf7\x0b" + struct.pack("<H", ENTRY_VAR) + b"\x0c"
                    out += prologue
                    out += b"\x0e" + struct.pack("<h", at - (place + len(out) + 3))
                    struct.pack_into("<h", out, skip + 1, len(out) - (skip + 3))
                out += b"\x0e" + struct.pack("<h", r_at - (place + len(out) + 3))
            for site, back in widths:
                calls[site] = place + len(out)             # (a letter's width: 1)
                out += ONE
                out += b"\x0e" + struct.pack("<h", back - (place + len(out) + 3))
            return bytes(out)
        return G.build(d2, real, extra, calls, more, drop, pokes)[0]
    widths = []
    for m in WIDTH.finditer(code):
        w = WIDTH_OTHER.search(code, m.start(), m.start() + 0x60)
        if w:
            site = w.start() + 5
            widths.append((site, G.target(site, code[site:site + 3])))
    try:
        return [(name(0), one(None, []))]
    except ValueError as ex:
        whole = ex
    main, routines = G.layout(ops)
    if not routines:
        raise whole
    sites = [(a, G.target(a, b)) for a, op, b in ops if op == 0x0C and G._owner(starts, a) == main]
    index = {a: k for k, (a, _op, _b) in enumerate(ops)}
    places = [a for a, _op, _b in ops] + [len(code)]

    ends = {}
    for r in routines:
        ends[r] = next((k for k in range(index[r] + 1, len(ops)) if G._owner(starts, ops[k][0]) != r), len(ops))
    split = {}                                  # (a looping routine in bodies: {routine: [(first, last,
    groups, part_of, cut_of, owner = [[]], {}, {}, {}  # entries)]}; owner {(routine, body): part})

    def attempt(group, part_of, cut_of, owner):
        """A part: `group` its units, each a routine (whole), ("p", routine, first op, past last op)
        a piece, or ("b", routine, body) a body of a looping routine (its head in every part); the
        other parts' units reached through their files: `part_of` the part of each routine's first
        unit, `cut_of` {routine: [(op, part)]} the parts its later pieces are in, `owner` the bodies'."""
        whole = [u for u in group if not isinstance(u, tuple)]
        pieces = [u[1:] for u in group if isinstance(u, tuple) and u[0] == "p"]
        mine_b = {(u[1], u[2]) for u in group if isinstance(u, tuple) and u[0] == "b"}
        others = set(routines) - set(whole) - set(split)
        roots = [0, main] + whole
        flows = {}
        for r, lo, hi in pieces:                            # (a piece: the ops control reaches in it)
            flows[(r, lo)] = _flow(ops, index, lo, hi if hi < ends[r] else None, ends[r])
        inline, leaves, kept = [], [], {}
        for r, bodies in split.items():                     # (a looping routine: but other parts' bodies)
            foreign = set()
            i = 0
            for n, (b0, e, entries) in enumerate(bodies):
                pname = name(owner.get((r, n), len(part_of) + 1))
                for m, en in enumerate(entries):
                    i += 1
                    if (r, n) in mine_b:
                        kept.setdefault(r, []).append((i, places[en]))
                        continue
                    nxt = entries[m + 1] if m + 1 < len(entries) else e + 1
                    k, size = en, 0
                    while size < 3 and k < nxt:
                        size += len(ops[k][2])
                        k += 1
                    leaves.append((places[en], size, i, pname))
                if (r, n) not in mine_b:
                    foreign |= set(range(b0, e + 1))
            flows[(r, index[r])] = set(range(index[r], ends[r])) - foreign
        for ks in flows.values():
            roots += [G.target(ops[k][0], ops[k][2]) for k in ks if ops[k][1] == 0x0C]
        cut_r = {r for r, _lo, _hi in pieces} | set(split)
        roots = [t for t in roots if t not in cut_r]
        reach = _reach(ops, roots, main, others)
        live = G.pushes_in(ops, reach - cut_r)
        for ks in flows.values():
            live |= {G.pushed(ops[k][2]) for k in ks if G.pushed(ops[k][2]) is not None}
        chains, enters, dispatch = [], [], []
        mine = {r: (lo, hi) for r, lo, hi in pieces}
        for a, t in sites:
            if t in split:
                dispatch.append((a, t, _prologue(ops, index[t]), kept.get(t, [])))
                continue
            if t in whole or t not in routines:
                continue
            if t in mine and mine[t][0] == index[t]:
                continue                                    # (its first piece here: called as it is)
            if t in mine:
                enters.append((a, _prologue(ops, index[t]), places[mine[t][0]]))
            else:
                chains.append((a, name(part_of.get(t, len(part_of) + 1))))
        for r, lo, hi in pieces:
            nxt = [(c, p) for c, p in cut_of.get(r, []) if c == hi]
            if nxt:
                inline.append((places[hi], 8, name(nxt[0][1])))
        return one(live, chains, enters, inline, leaves, dispatch)

    def fits(group):
        trial = {r: list(c) for r, c in cut_of.items()}
        for u in group:
            if isinstance(u, tuple) and u[0] == "p" and u[3] < ends[u[1]]:   # (the next part goes on there)
                trial.setdefault(u[1], []).append((u[3], len(groups)))
        own = dict(owner)
        for u in group:
            if isinstance(u, tuple) and u[0] == "b":
                own[(u[1], u[2])] = len(groups) - 1
        try:
            attempt(group, dict(part_of), trial, own)
            return True
        except ValueError:
            return False
    for r in routines:
        part_of[r] = len(groups) - 1
        if fits(groups[-1] + [r]):
            groups[-1].append(r)
            continue
        if groups[-1]:
            groups.append([])
            part_of[r] = len(groups) - 1
            if fits([r]):
                groups[-1].append(r)
                continue
        lay = _bodies(ops, r, index, starts)                # (the routine alone too long: its bodies
        if lay:                                             # in parts, its head in every part)
            split[r] = lay[1]
            for n in range(len(lay[1])):
                if not fits(groups[-1] + [("b", r, n)]):
                    if not groups[-1]:
                        raise ValueError("a part of the scene alone past its segment")
                    groups.append([])
                    if not fits([("b", r, n)]):
                        raise ValueError("a part of the scene alone past its segment")
                groups[-1].append(("b", r, n))
                owner[(r, n)] = len(groups) - 1
            continue
        cuts = _cuts(ops, r, index, starts)                 # (else in pieces, at its messages)
        lo, end = index[r], ends[r]
        while lo < end:
            best = None
            for c in [c for c in cuts if c > lo] + [end]:
                if fits([("p", r, lo, c)]):
                    best = c
                elif best is not None:
                    break
            if best is None:
                raise ValueError("a part of the scene alone past its segment, with nowhere to cut it")
            groups[-1].append(("p", r, lo, best))
            if best < end:
                cut_of.setdefault(r, []).append((best, len(groups)))
                groups.append([])
            lo = best
    if not all(groups):
        raise ValueError("a part of the scene with nothing in it")
    return [(name(n), attempt(g, part_of, cut_of, owner)) for n, g in enumerate(groups)]


def _flow(ops, index, start, stop, end):
    """The op indices control reaches in a routine (ops up to `end`) from `start`, `stop` ending it
    (the part goes on in another file there)."""
    seen, todo = set(), [start]
    while todo:
        k = todo.pop()
        while k < end and k not in seen and k != stop:
            seen.add(k)
            a, op, b = ops[k]
            if op in G.BRANCH and op != 0x0C:
                t = index.get(G.target(a, b))
                if t is not None:
                    todo.append(t)
                if op in (0x0E, 0x0F):          # (a jump: no way on)
                    break
            if op == 0x04:
                break
            k += 1
    return seen


def _bodies(ops, r, index, starts):
    """A routine that loops through a head (most of its jumps back to one place), its blocks each a
    guard (a jump past the block) and a body ending in a jump back to the head: [(body's first op,
    its jump back, [its entry ops: its first and the places jumped to in it from outside])], the
    bodies with room at each entry for a jump (3 bytes of whole ops), the routine with no
    frame-relative variables; None when it is not so laid out."""
    lo = index[r]
    body = []
    for k in range(lo, len(ops)):
        if G._owner(starts, ops[k][0]) != r:
            break
        body.append(k)
    for k in body:                              # (no frame-relative variables: a part enters a body
        for at, m, v, n in _operands(ops[k][2]):  # after the routine's prologue)
            if not m & 0x80 and (m & 0x0C) == 0 and n and k > lo + 2:
                return None
    jumps = [(k, index.get(G.target(ops[k][0], ops[k][2]))) for k in body
             if ops[k][1] in G.BRANCH and ops[k][1] != 0x0C]
    if any(t is None for _k, t in jumps):
        return None
    back = collections.Counter(t for k, t in jumps if t < k)
    if not back:
        return None
    head = back.most_common(1)[0][0]
    ends = [k for k, t in jumps if t == head and ops[k][1] in (0x0E, 0x0F)]
    out, prev = [], head
    for e in ends:
        guard = next((k for k, t in jumps if prev <= k < e and t == e + 1), None)
        if guard is None:
            prev = e + 1
            continue
        b0 = guard + 1
        inside = range(b0, e + 1)
        entries = sorted({b0} | {t for k, t in jumps if t in inside and k not in inside})
        ok = True
        for n, en in enumerate(entries):
            nxt = entries[n + 1] if n + 1 < len(entries) else e + 1
            k, size = en, 0
            while size < 3 and k < nxt:
                size += len(ops[k][2])
                k += 1
            if size < 3:
                ok = False
        if ok and all(b0 <= x <= e for x in entries):
            out.append((b0, e, entries))
        prev = e + 1
    return (head, out) if len(out) >= 2 else None


def _sections(ops, r, index, starts):
    """A routine that dispatches to its sections from its head (jumps from its start to places after
    it, a state variable choosing): ([section start's op index], [(the head jump's op index, the
    section's)]); None when a jump between sections does not go from the head or back to it."""
    lo = index[r]
    body = []
    for k in range(lo, len(ops)):
        if G._owner(starts, ops[k][0]) != r:
            break
        body.append(k)
    jumps = [(k, index.get(G.target(ops[k][0], ops[k][2]))) for k in body
             if ops[k][1] in G.BRANCH and ops[k][1] != 0x0C]
    if any(t is None for _k, t in jumps):
        return None
    for head_end in sorted({t for k, t in jumps if t > k}):     # (the head: the shortest that works)
        secs = sorted({t for k, t in jumps if k < head_end and t >= head_end})
        if len(secs) < 2 or secs[0] != head_end:
            continue
        bounds = secs + [body[-1] + 1]

        def sec(k):
            return max((n for n, s in enumerate(secs) if s <= k), default=None)
        if all(k < head_end or t < head_end or sec(k) == sec(t) for k, t in jumps):
            heads = [(k, secs.index(t)) for k, t in jumps if k < head_end and t in secs]
            return secs, bounds, heads
    return None


def _prologue(ops, k):
    """A routine's prologue (from op k: the frame's push and move, and its locals)."""
    out = b""
    while k < len(ops) and (ops[k][2] in (b"\x24", b"\xf4\x85") or ops[k][1] in (0x09, 0x0A)):
        out += ops[k][2]
        k += 1
    return out


def _cuts(ops, r, index, starts):
    """The op indices a routine may be cut before: a message drawn (a push, a call, a pop), the
    routine with no frame-relative variables (the next part enters it there, after its prologue;
    each part keeps the strings control reaches in it, `_flow`)."""
    lo = index[r]
    body = []
    for k in range(lo, len(ops)):
        if G._owner(starts, ops[k][0]) != r:
            break
        body.append(k)
    for k in body:
        for at, m, v, n in _operands(ops[k][2]):
            if not m & 0x80 and (m & 0x0C) == 0 and n and k > lo + 2:
                return []
    out = []
    for k in body[3:]:
        if (G.pushed(ops[k][2]) is not None and k + 2 < len(ops) and ops[k + 1][1] == 0x0C
                and ops[k + 2][2] == b"\x32"):
            out.append(k)
    return out


def _operands(b):
    """[(offset, mode, value's offset, value size)] of an operation's operands."""
    op, out = b[0], []

    def one(i):
        m = b[i]
        if m & 0x80:
            out.append((i, m, None, 0))
            return i + 1
        n = {0: 0, 1: 2, 2: 1, 3: 2}[m & 3]
        out.append((i, m, i + 1 if n else None, n))
        return i + 1 + n
    if 0x05 <= op <= 0x08:
        one(1)
    elif op == 0x0B:
        one(one(1))
    elif op >= 0x20:
        i = 1
        if op & 0x0F == 7:
            i = one(i)
        if op >= 0x60:
            one(i)
    return out
