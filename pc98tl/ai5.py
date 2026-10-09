"""Elf's AI5 (PC-98: Dragon Knight III and the AI5 games after it): the
MES scripts.

A MES file starts with a word, the offset of its bytecode; the bytes
before it are the file's dictionary: two-byte Shift-JIS characters, the
most frequent of its text.  The bytecode (run by AI5.EXE from the start)
is, per statement:

* 00, 01, 02: block structure (a block opens with 01, sometimes 00, and
  ends with 00; 02 separates the parts of an if and the items of a menu).
  The engine finds a block's end by counting 01 and 00 bytes, so no other
  byte of a script is 00 or 01; nothing in a script is an address, so a
  script may grow and shrink freely.
* 80h-FFh: a dictionary character (80h + its index); 60h-7Fh xx: the
  character (60h-7Fh + 20h) xx; the character "％" (81 93) starts a new line.
* 06 ... 06: a string of single-byte characters drawn with the character
  ROM's half-width glyphs (a status line's "HP:"); the cursor moves on by
  the character width the script set (DS:E281h).
* 04 xx: a system call; 0A-1F: a command.  Their arguments are
  expressions (RPN, ended by 03: 30h-3Fh a small number, 07 x / 08 x y /
  09 x y z a larger one, 40h-5Ah a variable, 20h-2Fh an operator, 2Dh and
  2Fh with a number after them), strings (06 ... 06) and blocks, joined by
  02; 0F (if) takes an expression and blocks; 0F with an expression and no
  block is a menu item's condition.  Bytes 20h-5Fh and 03 never start a
  statement.
* 11 waits for a key and clears the text window; 13 n calls subroutine n
  (the hero's name in a message is such a call); 10 n sets the speaker.
* 0D 40 i v...: the words from DS:(E256h + 2i) get the values v (the
  script sets the text window this way: i = 13-16 its left column, top,
  right column and bottom line in pixels; i = 21 the line height and the
  character width).

English is written as half-width strings (06 ... 06) between a command
that sets the character width to 1 and one that sets it back to 2, the
lines wrapped between words to the text window and a new page (11) begun
before a line would run past its bottom (the window starts over at its top
line, over the text, otherwise).
"""
import json
import os
import re
import struct

from . import elfdos
from .alice_sys2_tl import sha256


class Bad(Exception):
    pass


def _num(d, i):
    b = d[i]
    if 0x30 <= b < 0x40:
        return i + 1, b - 0x30
    if b == 7:
        return i + 2, d[i + 1] >> 2
    if b == 8:
        return i + 3, (((d[i + 1] >> 2) << 8) | d[i + 2]) >> 2
    if b == 9:
        ax = (((d[i + 1] >> 2) << 8) | d[i + 2]) >> 2
        bl = d[i + 3]
        for _ in range(2):
            bl = ((ax & 1) << 7) | (bl >> 1)
            ax >>= 1
        return i + 4, ((ax & 0xFF) << 8) | bl
    raise Bad("number %02x at %x" % (b, i))


def _expr(d, i):
    """(the offset after the expression's 03, its value or None)"""
    stack = []
    while True:
        b = d[i]
        if b == 3:
            return i + 1, (stack[-1] if len(stack) == 1 else None)
        if 0x30 <= b < 0x40 or b in (7, 8, 9):
            i, v = _num(d, i)
            stack.append(v)
        elif 0x40 <= b <= 0x5a:
            i += 1
            stack.append(None)
        elif b in (0x2d, 0x2f):
            i, _v = _num(d, i + 1)
            stack.append(None)
        elif 0x20 <= b < 0x30:
            i += 1
            y = stack.pop() if stack else None
            x = stack.pop() if stack else None
            if x is None or y is None or b > 0x24:
                stack.append(None)
            else:
                stack.append([x + y, max(0, x - y), x * y, x // y if y else 0, x % y if y else 0][b - 0x20])
        else:
            raise Bad("expression byte %02x at %x" % (b, i))


def _is_expr(b):
    return b in (7, 8, 9) or 0x20 <= b <= 0x5a


def _string(d, i):
    return d.index(6, i + 1) + 1


def _args(d, i, values=None):
    while True:
        b = d[i]
        if b == 6:
            i = _string(d, i)
        elif _is_expr(b):
            i, v = _expr(d, i)
            if values is not None:
                values.append(v)
        else:
            return i
        if d[i] == 2 and (d[i + 1] == 6 or _is_expr(d[i + 1])):
            i += 1
            continue
        return i


def tokenize(d):
    """[(kind, start, end, extra)]: "ch" a text character, "ank" a string
    drawn as text, "poke" a 0D 40 command (extra: (index, [values])), "op"
    any other statement (extra: its first byte), "struct" 00/01/02."""
    i = struct.unpack_from("<H", d, 0)[0]
    out = []
    while i < len(d):
        b, s = d[i], i
        if b in (0, 1, 2):
            i += 1
            if b == 2 and i < len(d) and (d[i] == 6 or _is_expr(d[i])):
                # (an argument list going on past a block item: no statement starts so)
                i = _args(d, i)
                out.append(("op", s, i, b))
                continue
            out.append(("struct", s, i, b))
            continue
        if b == 4:
            i = _args(d, i + 2)
        elif b == 6:
            i = _string(d, i)
            out.append(("ank", s, i, None))
            continue
        elif b == 0x0a:
            i = _expr(d, _num(d, i + 1)[0])[0]
        elif b == 0x0b:
            i = _expr(d, _expr(d, i + 1)[0])[0]
        elif b == 0x0c:
            i = _expr(d, i + 2)[0]
        elif b in (0x0d, 0x0e):
            i, idx = _expr(d, i + 2)
            vals = []
            i, v = _expr(d, i)
            vals.append(v)
            while d[i] == 2 and _is_expr(d[i + 1]):
                i, v = _expr(d, i + 1)
                vals.append(v)
            if b == 0x0d and d[s + 1] == 0x40:
                out.append(("poke", s, i, (idx, vals)))
                continue
        elif b == 0x0f:
            i = _expr(d, i + 1)[0]
        elif 0x10 <= b <= 0x1a or b == 0x1f:
            i = _args(d, i + 1)
        elif b == 0x1b:
            i = _expr(d, i + 2)[0]
        elif b in (0x1c, 0x1d, 0x1e):
            i += 1
        elif b >= 0x80:
            i += 1
            out.append(("ch", s, i, None))
            continue
        elif 0x60 <= b < 0x80:
            i += 2
            out.append(("ch", s, i, None))
            continue
        else:
            raise Bad("statement %02x at %x" % (b, i))
        out.append(("op", s, i, b))
    return out


def char(d, a):
    """The character at a (a dictionary code or a two-byte one)."""
    b = d[a]
    pair = d[2 + 2 * (b - 0x80):4 + 2 * (b - 0x80)] if b >= 0x80 else bytes([b + 0x20, d[a + 1]])
    if pair == b"\x81\x93":
        return "\n"
    try:
        return pair.decode("cp932")
    except UnicodeDecodeError:
        return "{U%s}" % pair.hex()


def _is_name_call(d, tok):
    return tok[0] == "op" and tok[3] == 0x13


def units(d, toks=None):
    """[(first token, last token + 1, kind, jp)]: runs of text characters
    with the subroutine calls inside them ({Xn}, 13 n: the hero's name);
    kind "item" for a run a menu item's separator (00 or 02) ends."""
    toks = toks if toks is not None else tokenize(d)
    out = []
    k = 0
    while k < len(toks):
        if toks[k][0] != "ch":
            k += 1
            continue
        j = k
        while j < len(toks) and (toks[j][0] == "ch" or _is_name_call(d, toks[j]) and j + 1 < len(toks)
                                 and toks[j + 1][0] == "ch"):
            j += 1
        jp = ""
        for t in toks[k:j]:
            jp += char(d, t[1]) if t[0] == "ch" else "{X%d}" % call_number(d, t)
        kind = "item" if j < len(toks) and toks[j][0] == "struct" and toks[j][3] in (0, 2) else "msg"
        if kind == "msg" and k and toks[k - 1][0] == "poke" and toks[k - 1][3][0] == CURSOR:
            # (text the script puts at a place of its own: a label in a fixed slot)
            kind = "label"
        out.append((k, j, kind, jp))
        k = j
    return out


def call_number(d, tok):
    return _expr(d, tok[1] + 1)[1]


WINDOW = (13, 14, 15, 16)       # the poke indexes of the window's left, top, right, bottom
CURSOR = 17                     # the cursor's column and line
FONT = 21                       # line height | character width << 8


def _block_end(d, i):
    """The offset after the block opening at i (01 ... 00, counted as the
    engine counts them)."""
    depth = 0
    while i < len(d):
        if d[i] == 1:
            depth += 1
        elif d[i] == 0:
            depth -= 1
            if depth <= 0:
                return i + 1
        i += 1
    return i


def _apply(state, extra):
    idx, vals = extra
    if idx is not None:
        for k, v in enumerate(vals):
            if idx + k in state:
                state[idx + k] = v


def windows(d, toks):
    """{token index of each character: (left, top, right, bottom, line
    height)} of the text window it is drawn in: the pokes before it in the
    file, with a subroutine's (12 n defines it, the block after it) where
    13 n calls it, and a subroutine's own kept to its body (None where a
    value is not known)."""
    subs, bodies = {}, []
    for n, (kind, s, e, extra) in enumerate(toks):
        if kind == "op" and extra == 0x12 and n + 1 < len(toks) and toks[n + 1][0] == "struct":
            start = toks[n + 1][1]
            end = _block_end(d, start)
            bodies.append((start, end))
            subs[_expr(d, s + 1)[1]] = [t[3] for t in toks if t[0] == "poke" and start <= t[1] < end]
    state = {13: None, 14: None, 15: None, 16: None, 21: None}
    saved, body_end = None, None
    out = {}
    for n, (kind, s, e, extra) in enumerate(toks):
        if body_end is not None and s >= body_end:
            state, saved, body_end = saved, None, None
        if body_end is None:
            for a, b in bodies:
                if a <= s < b:
                    saved, body_end = dict(state), b
                    break
        if kind == "poke":
            _apply(state, extra)
        elif kind == "op" and extra == 0x13:
            for p in subs.get(_expr(d, s + 1)[1], ()):
                _apply(state, p)
        elif kind == "ch":
            out[n] = (state[13], state[14], state[15], state[16], (state[21] or 0x210) & 0xFF)
    return out


# ---- English

POKE_HALF = bytes.fromhex("0d 40 07 57 03 08 13 03 07 43 20 03")   # line height 16, character width 1
POKE_FULL = bytes.fromhex("0d 40 07 57 03 08 23 03 07 43 20 03")   # line height 16, character width 2
NAME_CELLS = 8          # the hero's name a subroutine prints (four full-width letters)
_TOKEN = re.compile(r"\{([XU])([0-9A-Fa-f]+)\}")
_SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}


def _dict(d):
    start = struct.unpack_from("<H", d, 0)[0]
    return {d[2 + 2 * k:4 + 2 * k]: 0x80 + k for k in range((start - 2) // 2)}


def _wide(pair, dic):
    """The script bytes of a two-byte character (None where it has none)."""
    if pair in dic:
        return bytes([dic[pair]])
    if 0x81 <= pair[0] <= 0x9F:
        return bytes([pair[0] - 0x20, pair[1]])
    return None


def pieces(text, calls, dic):
    """English as [(kind, value, cells)]: "word" ASCII text (no spaces),
    "space", "wide" a two-byte character's script bytes, "call" a
    subroutine call's bytes, "nl" a forced new line."""
    out = []
    pos = 0
    text = "".join(_SUBST.get(c, c) for c in text)
    for m in list(_TOKEN.finditer(text)) + [None]:
        seg = text[pos:m.start() if m else len(text)]
        word = ""
        for c in seg:
            if 0x21 <= ord(c) < 0x7F:
                word += c
                continue
            if word:
                out.append(("word", word, len(word)))
                word = ""
            if c == " ":
                out.append(("space", " ", 1))
            elif c == "\n":
                out.append(("nl", None, 0))
            else:
                b = _wide(c.encode("cp932", "replace"), dic)
                if b is None:
                    out.append(("word", "?", 1))
                else:
                    out.append(("wide", b, 2))
        if word:
            out.append(("word", word, len(word)))
        if m is None:
            break
        if m.group(1) == "X":
            out.append(("call", calls[int(m.group(2))], NAME_CELLS))
        else:
            b = _wide(bytes.fromhex(m.group(2)), dic)
            out.append(("wide", b, 2) if b else ("word", "?", 1))
        pos = m.end()
    return out


class Writer:
    """The bytes of English in a window: ASCII in half-width strings with
    the character width switched around them, lines wrapped between words,
    a new page (11: a key wait and a clear) where the window is full."""

    def __init__(self, dic, width, lines, state):
        self.dic, self.width, self.lines, self.st = dic, width, lines, state
        self.out = bytearray()
        self.open = self.half = self.guard = False

    def _close(self):
        if self.open:
            self.out.append(6)
            self.open = False

    def ascii(self, s):
        if not self.half or self.guard:
            # (after 11 the width command comes first: a string right after it would be
            # taken for its argument)
            self._close()
            self.out += POKE_HALF
            self.half, self.guard = True, False
        if not self.open:
            self.out.append(6)
            self.open = True
        self.out += s.encode("ascii")
        self.st["col"] += len(s)

    def wide(self, b, cells):
        self._close()
        if self.half:
            self.out += POKE_FULL
            self.half = False
        self.out += b
        self.guard = False
        self.st["col"] += cells

    def newline(self):
        self._close()
        if self.st["line"] + 1 >= self.lines:
            self.out.append(0x11)
            self.guard = True
            self.st["line"] = 0
        else:
            self.out += _wide(b"\x81\x93", self.dic)
            self.st["line"] += 1
        self.st["col"] = 0

    def finish(self):
        self._close()
        if self.half:
            self.out += POKE_FULL
            self.half = False
        return bytes(self.out)

    def text(self, ps):
        for kind, val, cells in ps:
            if kind == "nl":
                self.newline()
                continue
            if kind == "space":
                if self.st["col"] and self.st["col"] + 1 <= self.width:
                    self.ascii(" ")
                continue
            if self.st["col"] and self.st["col"] + cells > self.width:
                self.newline()
            while kind == "word" and cells > self.width:
                k = self.width - self.st["col"]
                self.ascii(val[:k])
                self.newline()
                val, cells = val[k:], cells - k
            if kind == "word":
                self.ascii(val)
            else:
                self.wide(val, cells)


def item_bytes(text, calls, dic):
    """A menu item's English as [script bytes of each character]: letters
    full-width, subroutine calls as they are."""
    from .text import encode_fullwidth
    out = []
    pos = 0
    text = "".join(_SUBST.get(c, c) for c in text).replace("\n", " ")
    for m in list(_TOKEN.finditer(text)) + [None]:
        for c in text[pos:m.start() if m else len(text)]:
            b = _wide(encode_fullwidth(c), dic)
            if b:
                out.append(b)
        if m is None:
            break
        if m.group(1) == "X":
            out.append(calls[int(m.group(2))])
        else:
            b = _wide(bytes.fromhex(m.group(2)), dic)
            if b:
                out.append(b)
        pos = m.end()
    return out


def is_grid(jp):
    """A row of the name entry's character grid (kana in groups set apart
    by full-width spaces): the entry picks characters by position, so the
    grid stays Japanese."""
    body = jp.replace("\n", "")
    return body.count("　") >= 3 and all("ぁ" <= c <= "ヶ" or c == "　" for c in body)


DEFAULT_WINDOW = (4, 312, 75, 376, 16)      # the message window at the bottom of the screen


def _win(w):
    return tuple(DEFAULT_WINDOW[k] if v is None else v for k, v in enumerate(w))


def _cells_jp(toks, k, j):
    return sum(NAME_CELLS if t[0] == "op" else 2 for t in toks[k:j])


def _lines(top, bottom, h):
    """The lines the window holds: the engine starts over at the top when
    a new line's bottom (less two) would reach the window's bottom."""
    n = 1
    while top + n * h + h - 2 < bottom:
        n += 1
    return n


def rebuild(d, values, warn, ids, name):
    """The script with the English in values ({offset of a unit's first
    character: text}) written over its units."""
    toks = tokenize(d)
    us = units(d, toks)
    if not any(toks[k][1] in values for k, _j, _kind, _jp in us):
        return d
    win = windows(d, toks)
    dic = _dict(d)
    by_start = {k: (j, kind) for k, j, kind, _jp in us}
    out = bytearray(d[:toks[0][1]])
    st = {"line": 0, "col": 0}
    n = 0
    while n < len(toks):
        kind, s, e, extra = toks[n]
        if kind == "op" and extra in (0x11, 0x17) or kind == "poke" and extra[0] in WINDOW:
            st = {"line": 0, "col": 0}
        if n in by_start:
            j, ukind = by_start[n]
            left, top, right, bottom, h = _win(win[n])
            width = max(8, right - left - 1)
            lines = _lines(top, bottom, h or 16)
            calls = {call_number(d, t): d[t[1]:t[2]] for t in toks[n:j] if t[0] == "op"}
            if s in values:
                ps = pieces(values[s], calls, dic)
                if ukind == "item":
                    # (a menu draws its items' characters itself: full-width letters, within the
                    # Japanese item's width)
                    room = _cells_jp(toks, n, j)
                    b = item_bytes(values[s], calls, dic)
                    used = sum(NAME_CELLS if c[:1] == b"\x13" else 2 for c in b)
                    if used > room:
                        warn.append("%s: %d cells, the menu item has %d" % (ids.get((name, s), hex(s)), used, room))
                        while b and sum(NAME_CELLS if c[:1] == b"\x13" else 2 for c in b) > room:
                            b.pop()
                    out += b"".join(b)
                    n = j
                    continue
                if ukind == "label":
                    # (one line in the Japanese label's slot: half-width letters, as many as its cells)
                    room = _cells_jp(toks, n, j)
                    ps = [p for p in ps if p[0] != "nl"]
                    used = sum(c for _k, _v, c in ps)
                    if used > room:
                        warn.append("%s: %d cells, the label has %d" % (ids.get((name, s), hex(s)), used, room))
                        keep, total = [], 0
                        for p in ps:
                            if p[0] == "word" and total + p[2] > room:
                                p = ("word", p[1][:room - total], room - total)
                            if not p[2] or total + p[2] > room:
                                break
                            keep.append(p)
                            total += p[2]
                        ps = keep
                    w = Writer(dic, room, 1, {"line": 0, "col": 0})
                    w.text(ps)
                    out += w.finish()
                    n = j
                    continue
                w = Writer(dic, width, lines, st)
                w.text(ps)
                out += w.finish()
                n = j
                continue
            # (Japanese kept: the window's cursor moves on as it would)
            for t in toks[n:j]:
                if t[0] == "ch" and char(d, t[1]) == "\n":
                    st["line"] = min(st["line"] + 1, lines - 1)
                    st["col"] = 0
                else:
                    st["col"] += NAME_CELLS if t[0] == "op" else 2
        out += d[s:e]
        n += 1
    return bytes(out)


# ---- the game

def _install(cfg, src):
    """(the image to patch, its config): the game's own hard-disk image, or
    its floppies laid out on one (cfg "hdd", see illusion_game)."""
    if not cfg.get("hdd"):
        from .disk import DiskImage
        return DiskImage(src), cfg
    from .illusion_game import _hdd_install
    return _hdd_install(cfg, src)


def _scripts(vol, cfg):
    d = cfg["game_dir"]
    return [(p.split("/")[-1], p) for p, *_ in vol.walk()
            if p.upper().startswith(d.upper() + "/") and p.upper().endswith(".MES")]


PREFIX = {"msg": "m", "item": "i", "label": "l"}


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    img, cfg2 = _install(cfg, src)
    vol = img.volumes[0]
    merged, order = {}, []
    for name, path in _scripts(vol, cfg2):
        d = vol.read(path)
        toks = tokenize(d)
        win = windows(d, toks)
        for k, j, kind, jp in units(d, toks):
            if not jp.strip("　 \n") or is_grid(jp):
                continue
            left, top, right, bottom, h = _win(win[k])
            cellsn = _cells_jp(toks, k, j) if kind in ("item", "label") else max(8, right - left - 1)
            key = (kind, jp)
            ref = "%s:%04x" % (name, toks[k][1])
            if key in merged:
                merged[key]["refs"].append(ref)
                continue
            e = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cellsn}
            if "{X26}" in jp:
                e["note"] = "{X26}: the hero's name (the script's subroutine 26 prints it)"
            merged[key] = e
            order.append(key)
    counts, strings = {}, []
    for key in order:
        e = merged[key]
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        strings.append({"id": "%s%05d" % (PREFIX[e["kind"]], counts[e["kind"]]), **e})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):     # keep translations
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev and prev.get("en"):
                e["en"] = prev["en"]
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
    img, cfg2 = _install(cfg, src)
    vol = img.volumes[0]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        if mode == "pseudo":
            body = pseudo(e["id"], 2 * len(e["jp"].replace("{X26}", "")))
            text = ("【{X26}】" + body) if e["jp"].startswith("【{X26}】") else body
        else:
            text = e["en"]
        for r in e["refs"]:
            f, a = r.rsplit(":", 1)
            ids[(f, int(a, 16))] = e["id"]
            if text:
                by_ref[(f, int(a, 16))] = text
    warn, done = [], 0
    for name, path in _scripts(vol, cfg2):
        d = vol.read(path)
        values = {a: t for (f, a), t in by_ref.items() if f == name}
        new = rebuild(d, values, warn, ids, name)
        if new != d:
            tokenize(new)
            vol.write(path, new)
            done += 1
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
