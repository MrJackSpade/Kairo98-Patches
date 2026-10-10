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
    # (03 alone is an empty expression; no statement starts with it)
    return b in (3, 7, 8, 9) or 0x20 <= b <= 0x5a


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
    any other statement (extra: its first byte), "struct" 00/01/02, and
    "tail": bytes after the script's last block that are not a script
    (some files carry left-over data after their end; the engine never
    runs into it)."""
    out = []
    try:
        _tokens(d, out)
    except (Bad, IndexError, ValueError):
        depth, cut = 0, None
        for n, t in enumerate(out):
            if t[0] == "struct" and t[3] == 1:
                depth += 1
            elif t[0] == "struct" and t[3] == 0:
                depth = max(0, depth - 1)
                if depth == 0:
                    cut = n + 1
        if cut is None:
            raise
        del out[cut:]
        out.append(("tail", out[-1][2], len(d), None))
    return out


def _tokens(d, out):
    i = struct.unpack_from("<H", d, 0)[0]
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
        elif b >= 0x60 and _two_byte(b):
            i += 2
            out.append(("ch", s, i, None))
            continue
        elif b >= 0x80:
            i += 1
            out.append(("ch", s, i, None))
            continue
        elif 0x30 <= b <= 0x5A or b in (7, 8, 9):
            # (an expression standing alone where a statement would be: data the engine never
            # runs, between a menu's item texts in a few scripts)
            i = _expr(d, i)[0]
        else:
            raise Bad("statement %02x at %x" % (b, i))
        out.append(("op", s, i, b))


def char(d, a):
    """The character at a (a dictionary code or a two-byte one)."""
    b = d[a]
    pair = bytes([b + 0x20, d[a + 1]]) if _two_byte(b) else d[2 + 2 * (b - DICT):4 + 2 * (b - DICT)]
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
    return _number(d, tok[1] + 1)


def _number(d, i):
    """The value of the expression at i, None where it is not one."""
    try:
        return _expr(d, i)[1]
    except (Bad, IndexError):
        return None


# the engine's variables at @ (DS:E256h in AI5, C256h in AI4) as word indexes, by engine version
ENGINES = {
    "ai5": {"window": (13, 14, 15, 16), "cursor": 17, "font": 21, "ank": True},
    # (Silky's later SIL.EXE, Mobius Roid: dictionary characters from D0h, and C0h-CFh xx a
    # two-byte character too, its lead E0h-EFh)
    "sil2": {"window": (13, 14, 15, 16), "cursor": 17, "font": 21, "ank": True, "dict": 0xD0, "kanji": True},
    # (AI4, Shangrlia: no half-width strings; 06 ... 06 is skipped)
    "ai4": {"window": (24, 25, 26, 27), "cursor": 28, "font": 12, "ank": False},
}
WINDOW = (13, 14, 15, 16)       # the poke indexes of the window's left, top, right, bottom
CURSOR = 17                     # the cursor's column and line
FONT = 21                       # line height | character width << 8
ANK = True                      # the engine draws half-width strings (06 ... 06)
DICT = 0x80                     # the first dictionary character
KANJI = False                   # C0h-CFh xx is a two-byte character (lead E0h-EFh) too


def set_engine(cfg):
    global WINDOW, CURSOR, FONT, ANK, DICT, KANJI
    e = ENGINES[cfg.get("version", "ai5")]
    WINDOW, CURSOR, FONT, ANK = e["window"], e["cursor"], e["font"], e["ank"]
    DICT, KANJI = e.get("dict", 0x80), e.get("kanji", False)


def _two_byte(b):
    """Whether the text byte b starts a two-byte character (its lead b + 20h)."""
    return 0x60 <= b < 0x80 or KANJI and 0xC0 <= b <= 0xCF


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


def _assign(d, s):
    """(variable, value) of a statement "0A var value 03" with numbers
    for both (the script picking one of a subroutine's text windows),
    else None."""
    try:
        i, var = _num(d, s + 1)
        i, val = _num(d, i)
    except (Bad, IndexError):
        return None
    return (var, val) if var is not None and val is not None and d[i] == 3 else None


def _test(d, s):
    """(variable, value) of an if "0F 2D var value 27 03" (the variable
    equals the number), else None."""
    if d[s + 1] != 0x2D:
        return None
    try:
        i, var = _num(d, s + 2)
        i, val = _num(d, i)
    except (Bad, IndexError):
        return None
    return (var, val) if var is not None and val is not None and d[i:i + 2] == b"\x27\x03" else None


def subroutines(d, toks):
    """({number: [(condition, poke)]}, [(body start, end)]) of the
    subroutines a script defines (12 n, the block after it): their pokes,
    each with the (variable, value) its "if variable = value" block asks
    for, or None."""
    subs, bodies = {}, []
    for n, (kind, s, e, extra) in enumerate(toks):
        if kind == "op" and extra == 0x12 and n + 1 < len(toks) and toks[n + 1][0] == "struct":
            start = toks[n + 1][1]
            end = _block_end(d, start)
            bodies.append((start, end))
            conds = []
            for x in range(n + 1, len(toks)):
                k2, s2, _e2, _x2 = toks[x]
                if s2 >= end:
                    break
                if k2 == "op" and d[s2] == 0x0F:
                    c = _test(d, s2)
                    blk = next((t[1] for t in toks[x + 1:x + 3] if t[0] == "struct" and d[t[1]] == 1), None)
                    if c is not None and blk is not None:
                        conds.append((blk, _block_end(d, blk), c))
            subs[_number(d, s + 1)] = [
                (next((c for a, b, c in conds if a <= t[1] < b), None), t[3])
                for t in toks if t[0] == "poke" and start <= t[1] < end]
    return subs, bodies


# subroutines the start script defines, in force in the scripts loaded after it ({number: pokes})
SHARED = {}


def _width(poke):
    idx, vals = poke
    if idx == WINDOW[0] and len(vals) >= 3 and None not in (vals[0], vals[2]):
        return vals[2] - vals[0]
    return None


def windows(d, toks):
    """{token index of each character: (left, top, right, bottom, line
    height)} of the text window it is drawn in: the pokes before it in the
    file, with a subroutine's (12 n defines it, the block after it; or the
    start script's, SHARED) where 13 n calls it, and a subroutine's own kept
    to its body (None where a value is not known).  A subroutine that picks
    its window by a variable (if variable = value) takes the window the
    caller's last "0A variable value" picks, or, the value not known, the
    narrowest of them."""
    own, bodies = subroutines(d, toks)
    subs = {**SHARED, **own}
    state = {k: None for k in WINDOW + (FONT,)}
    saved, body_end = None, None
    assigned = {}
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
        elif kind == "op" and d[s] == 0x0A:
            a = _assign(d, s)
            if a is not None:
                assigned[a[0]] = a[1]
        elif kind == "op" and extra == 0x13:
            pokes = subs.get(_number(d, s + 1), ())
            pick = {}
            for var in {c[0] for c, _p in pokes if c is not None}:
                if var in assigned:
                    pick[var] = assigned[var]
                else:
                    known = [(c[1], _width(p)) for c, p in pokes
                             if c is not None and c[0] == var and _width(p) is not None]
                    if known:
                        pick[var] = min(known, key=lambda x: x[1])[0]
            for c, p in pokes:
                if c is None or pick.get(c[0]) == c[1]:
                    _apply(state, p)
        elif kind == "ch":
            out[n] = tuple(state[k] for k in WINDOW) + ((state[FONT] or 0x210) & 0xFF,)
    return out


def set_shared(store):
    """SHARED from the start script of the game's scripts (a Scripts)."""
    SHARED.clear()
    for name, path in store.items:
        if name.split("/")[-1].upper() == "START.MES":
            d = store.read(path)
            SHARED.update(subroutines(d, tokenize(d))[0])


# ---- English

def half_glyph(c):
    """The Shift-JIS code of the PC-98's half-width glyph for an ASCII
    character (row 9, 85 40-9E; the space 86 40)."""
    if c == " ":
        return b"\x86\x40"
    t = ord(c) - 0x21
    return bytes([0x85, t + 0x40 if t + 0x40 < 0x7F else t + 0x41])


def redict(d):
    """The script with its dictionary laid out again: the 128 characters
    that save the most bytes (each use of a dictionary character is one
    byte where it would be two), the text re-encoded with it."""
    toks = tokenize(d)
    start = struct.unpack_from("<H", d, 0)[0]
    old = {0x80 + k: d[2 + 2 * k:4 + 2 * k] for k in range((start - 2) // 2)}

    def pair(t):
        b = d[t[1]]
        return old[b] if b >= 0x80 else bytes([b + 0x20, d[t[1] + 1]])
    counts = {}
    for t in toks:
        if t[0] == "ch":
            p = pair(t)
            counts[p] = counts.get(p, 0) + 1
    # (a character with a lead byte from A0h has no two-byte form: it must be in the dictionary)
    must = [p for p in counts if p[0] >= 0xA0]
    if len(must) > 128:
        raise SystemExit("%d characters need the dictionary, which holds 128" % len(must))
    chosen = must + [p for p, n in sorted(counts.items(), key=lambda x: -x[1])
                     if n > 1 and p not in must][:128 - len(must)]
    code = {p: 0x80 + k for k, p in enumerate(chosen)}
    out = bytearray(struct.pack("<H", 2 + 2 * len(chosen)) + b"".join(chosen))
    for t in toks:
        if t[0] == "ch":
            p = pair(t)
            out += bytes([code[p]]) if p in code else bytes([p[0] - 0x20, p[1]])
        else:
            out += d[t[1]:t[2]]
    return bytes(out)


def font_poke(width, height):
    """0D 40 FONT (width << 8) + height: 08 (w << 4 | 3) (h << 2) 03 (the value in the 08 form:
    ((x >> 2) << 8 | y) >> 2; the index 30h + n below 16, else 07 (n << 2 | 3))."""
    if not 2 <= height <= 0x3F:
        raise SystemExit("a line height of %d" % height)
    idx = bytes([0x30 + FONT]) if FONT < 16 else bytes([0x07, FONT << 2 | 3])
    return bytes([0x0D, 0x40]) + idx + bytes([0x03, 0x08, width << 4 | 3, height << 2, 0x03])
NAME_CELLS = 8          # the hero's name a subroutine prints (four full-width letters)
# the subroutine calls messages hold ({Xn}): {n: (cells drawn, a page break: a key wait and a clear)};
# game.json "calls": {"n": {"cells": .., "page": .., "note": ..}}
CALLS = {}
# commands that print a value on the text cursor between messages ({opcode: cells}: 14 a string
# from memory, 15 a number; game.json "inserts"), counted on the line of the text after them
INSERTS = {}


def set_calls(cfg):
    CALLS.clear()
    INSERTS.clear()
    INSERTS.update({int(op, 16): cells for op, cells in cfg.get("inserts", {}).items()})
    for n, c in cfg.get("calls", {"26": {"cells": NAME_CELLS, "note": "the hero's name"}}).items():
        CALLS[int(n)] = (c.get("cells", 0), bool(c.get("page")))


def _call_cells(n):
    return CALLS.get(n, (NAME_CELLS, False))[0]
_TOKEN = re.compile(r"\{([XU])([0-9A-Fa-f]+)\}")
_SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}


def _dict(d):
    start = struct.unpack_from("<H", d, 0)[0]
    return {d[2 + 2 * k:4 + 2 * k]: DICT + k for k in range((start - 2) // 2)}


def _wide(pair, dic):
    """The script bytes of a two-byte character (None where it has none)."""
    if pair in dic:
        return bytes([dic[pair]])
    if 0x81 <= pair[0] <= 0x9F or KANJI and 0xE0 <= pair[0] <= 0xEF:
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
            n = int(m.group(2))
            out.append(("page" if CALLS.get(n, (0, False))[1] else "call", calls[n], _call_cells(n)))
        else:
            b = _wide(bytes.fromhex(m.group(2)), dic)
            out.append(("wide", b, 2) if b else ("word", "?", 1))
        pos = m.end()
    return out


class Writer:
    """The bytes of English in a window: ASCII in half-width strings with
    the character width switched around them, lines wrapped between words,
    a new page (11: a key wait and a clear) where the window is full."""

    def __init__(self, dic, width, lines, state, height=16, half=False, restore=True, guard=False):
        """half: the width is 1 already (the message before set it and nothing
        between draws); restore: the width goes back to 2 at the end; guard:
        the statement before takes arguments a string would join."""
        self.dic, self.width, self.lines, self.st = dic, width, lines, state
        self.half_poke, self.full_poke = font_poke(1, height), font_poke(2, height)
        self.out = bytearray()
        self.open = False
        self.half, self.guard, self.restore = half, guard, restore

    def _close(self):
        if self.open:
            self.out.append(6)
            self.open = False

    def ascii(self, s):
        if not ANK:
            # (an engine without half-width strings: the PC-98's half-width two-byte glyphs,
            # 85 40-9E for ! to ~ and 86 40 for the space, at width 1; the file's dictionary
            # is laid out again afterwards, see redict)
            if not self.half:
                self.out += self.half_poke
                self.half = True
            for c in s:
                self.out += _wide(half_glyph(c), self.dic)
            self.st["col"] += len(s)
            return
        if not self.half or self.guard:
            # (after 11 the width command comes first: a string right after it would be
            # taken for its argument)
            self._close()
            self.out += self.half_poke
            self.half, self.guard = True, False
        if not self.open:
            self.out.append(6)
            self.open = True
        self.out += s.encode("ascii")
        self.st["col"] += len(s)

    def wide(self, b, cells):
        self._close()
        if self.half:
            self.out += self.full_poke
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
        if self.half and self.restore:
            self.out += self.full_poke
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
            elif kind in ("call", "page"):
                # (a string right after a call would be read as its argument: the width command
                # comes first again)
                self.wide(val, cells)
                self.guard = True
                if kind == "page":
                    self.st["line"] = self.st["col"] = 0
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


def _cells_jp(toks, k, j, d=None):
    return sum((_call_cells(call_number(d, t)) if d is not None else NAME_CELLS) if t[0] == "op" else 2
               for t in toks[k:j])


def _lines(top, bottom, h):
    """The lines the window holds: the engine starts over at the top when
    a new line's bottom (less two) would reach the window's bottom."""
    n = 1
    while top + n * h + h - 2 < bottom:
        n += 1
    return n


# statements that may stand between two messages without drawing: the key wait, the speaker
# command, pokes other than the font's
_QUIET_OPS = (0x10, 0x11)


def _links(d, toks, us, values):
    """{token index of a translated message whose width need not go back to
    two: the next statement that draws is another translated message, in
    the same block (no structure byte between, so nothing branches in)}."""
    out = set()
    msgs = [(k, j) for k, j, kind, _jp in us if kind == "msg" and toks[k][1] in values]
    for (k, j), (k2, _j2) in zip(msgs, msgs[1:]):
        between = toks[j:k2]
        if all(t[0] == "op" and (t[3] in _QUIET_OPS or t[3] == 0x13 and
                                 CALLS.get(call_number(d, t), (0, False))[1])
               or t[0] == "poke" and t[3][0] is not None and t[3][0] != FONT for t in between):
            out.add(k)
    return out


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
    linked = _links(d, toks, us, values)
    carry = False
    out = bytearray(d[:toks[0][1]])
    st = {"line": 0, "col": 0}
    n = 0
    while n < len(toks):
        kind, s, e, extra = toks[n]
        if kind == "op" and extra in (0x11, 0x17) or kind == "poke" and extra[0] in WINDOW:
            st = {"line": 0, "col": 0}
        elif kind == "op" and d[s] in INSERTS:
            st["col"] += INSERTS[d[s]]
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
                    room = _cells_jp(toks, n, j, d)
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
                    room = _cells_jp(toks, n, j, d)
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
                    w = Writer(dic, room, 1, {"line": 0, "col": 0}, h or 16)
                    w.text(ps)
                    out += w.finish()
                    n = j
                    continue
                prev = toks[n - 1] if n else None
                w = Writer(dic, width, lines, st, h or 16, half=carry, restore=n not in linked,
                           guard=bool(prev and prev[0] == "op" and prev[2] - prev[1] == 1))
                w.text(ps)
                out += w.finish()
                carry = n in linked and w.half
                n = j
                continue
            # (Japanese kept: the window's cursor moves on as it would)
            for t in toks[n:j]:
                if t[0] == "ch" and char(d, t[1]) == "\n":
                    st["line"] = min(st["line"] + 1, lines - 1)
                    st["col"] = 0
                else:
                    if t[0] == "op" and CALLS.get(call_number(d, t), (0, False))[1]:
                        st["line"] = st["col"] = 0
                    else:
                        st["col"] += _call_cells(call_number(d, t)) if t[0] == "op" else 2
        out += d[s:e]
        n += 1
    return bytes(out) if ANK else redict(bytes(out))


# ---- the game

def _install(cfg, src):
    """(the image to patch, its config): the game's own hard-disk image, or
    its floppies laid out on one (cfg "hdd", see illusion_game)."""
    if not cfg.get("hdd"):
        from .disk import DiskImage
        return DiskImage(src), cfg
    from .illusion_game import _hdd_install
    return _hdd_install(cfg, src)


# a script is loaded at DS:0000 and runs there; the engine's variables start at DS:E000h
SCRIPT_ROOM = 0xE000


class Scripts:
    """The game's MES files: loose in the game folder, or in Elf's archives
    (game.json "archives": [archive file names in the game folder]; the
    scripts in one are found from start.mes through the script names the
    scripts give, as the archive holds hashes only), or in Silky's data
    archives (game.json "archive_format": "silkdat" or "silkdisk",
    pc98tl/silkdat.py: the scripts by their names in it).  Names are as the refs give them:
    "FILE.MES", or "ARCHIVE/file.mes"."""

    def __init__(self, vol, cfg):
        self.vol, self.cfg = vol, cfg
        self.arcs, self.changed = {}, {}
        d = cfg["game_dir"]
        if not cfg.get("archives"):
            self.items = [(p.split("/")[-1], p) for p, *_ in vol.walk()
                          if p.upper().startswith(d.upper() + "/") and p.upper().endswith(".MES")]
            return
        self.items = []
        if cfg.get("archive_format") in ("silkdat", "silkdisk"):
            from . import silkdat
            kind = silkdat.Archive if cfg["archive_format"] == "silkdat" else silkdat.DiskArchive
            for name in cfg["archives"]:
                self.arcs[name] = kind(vol.read(d + "/" + name))
            # (the script names the scripts give, for the one archive member whose first letter
            # takes the directory's key)
            known = {"MAIN.MES", "START.MES"}
            for arc in self.arcs.values():
                for f in arc.names():
                    if f.upper().endswith(".MES"):
                        known |= {m.decode("ascii").upper() for m in
                                  re.findall(rb"([!-~]{1,12}\.mes)", arc.read(f), re.I)}
            for name, arc in self.arcs.items():
                arc.name_first(known)
                self.items += [("%s/%s" % (name, f), (name, f)) for f in arc.names() if f.upper().endswith(".MES")]
            return
        from . import elfarc
        for name in cfg["archives"]:
            arc = elfarc.Archive(vol.read(d + "/" + name))
            self.arcs[name] = arc
            todo, seen = ["start.mes"], set()
            while todo:
                f = todo.pop()
                if f in seen or arc.index(f) is None:
                    continue
                seen.add(f)
                self.items.append(("%s/%s" % (name, f), (name, f)))
                for m in re.findall(rb"\x06([!-~]{1,12}\.mes)\x06", arc.read(f), re.I):
                    todo.append(m.decode("ascii").lower())
            self.items.sort()

    def read(self, where):
        if isinstance(where, tuple):
            return self.arcs[where[0]].read(where[1])
        return self.vol.read(where)

    def write(self, where, data):
        if isinstance(where, tuple):
            self.changed.setdefault(where[0], {})[where[1]] = data
        else:
            self.vol.write(where, data)

    def commit(self):
        d = self.cfg["game_dir"]
        for name, files in self.changed.items():
            self.vol.write(d + "/" + name, self.arcs[name].rebuilt(files))


PREFIX = {"msg": "m", "item": "i", "label": "l", "record": "r"}


def records(data, spec):
    """[(start, size, text)] of the names in a data file of fixed records
    (game.json "records": [{"file", "first", "stride", "size"}]: a table
    the engine reads names from, such as the monsters of a battle module):
    each record's name field (size bytes from first + n * stride) that holds
    Shift-JIS text ended by a NUL."""
    out = []
    at = spec["first"]
    while at + spec["size"] <= len(data):
        field = data[at:at + spec["size"]]
        end = field.find(b"\0")
        if end > 0:
            try:
                text = field[:end].decode("cp932")
            except UnicodeDecodeError:
                text = ""
            if text and all(ord(c) > 0x7F for c in text):
                out.append((at, spec["size"], text))
        at += spec["stride"]
    return out


def record_bytes(text, size):
    """A record's name field: the English in full-width letters (the
    engine draws these names from Shift-JIS), cut to whole letters with
    room for its NUL, NULs after it."""
    from .adv98v_tl import _fullwidth
    enc = _fullwidth(" ".join(text.split("\n")), None)[:(size - 1) // 2 * 2]
    return enc.ljust(size, b"\0")


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    set_calls(cfg)
    set_engine(cfg)
    notes = {int(n): c.get("note", "") for n, c in
             cfg.get("calls", {"26": {"note": "the hero's name"}}).items()}
    img, cfg2 = _install(cfg, src)
    vol = img.volumes[0]
    merged, order = {}, []
    store = Scripts(vol, cfg2)
    set_shared(store)
    for name, path in store.items:
        d = store.read(path)
        toks = tokenize(d)
        win = windows(d, toks)
        for k, j, kind, jp in units(d, toks):
            if not jp.strip("　 \n") or is_grid(jp):
                continue
            left, top, right, bottom, h = _win(win[k])
            cellsn = _cells_jp(toks, k, j, d) if kind in ("item", "label") else max(8, right - left - 1)
            key = (kind, jp)
            ref = "%s:%04x" % (name, toks[k][1])
            if key in merged:
                merged[key]["refs"].append(ref)
                continue
            e = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cellsn}
            used = sorted({int(x) for x in re.findall(r"\{X(\d+)\}", jp)})
            if used:
                e["note"] = "; ".join("{X%d}: %s (the script's subroutine %d)" % (x, notes.get(x) or "a subroutine call", x)
                                      for x in used)
            merged[key] = e
            order.append(key)
    for spec in cfg.get("records", []):
        for at, size, text in records(vol.read(cfg2["game_dir"] + "/" + spec["file"]), spec):
            key = ("record", text)
            ref = "%s:%04x" % (spec["file"], at)
            if key in merged:
                merged[key]["refs"].append(ref)
                merged[key]["max_cells"] = min(merged[key]["max_cells"], (size - 1) // 2)
                continue
            merged[key] = {"kind": "record", "jp": text, "en": "", "refs": [ref],
                           "max_cells": (size - 1) // 2, "note": spec.get("note", "")}
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


_SPEAKER = re.compile(r"【[^】]{0,12}】")
_BLANK = "　 " + chr(10)


def pseudo_text(e):
    """The --pseudo filler for a string: a part between page-break calls
    each gets filler, its speaker's bracket (and name call) kept."""
    from .text import pseudo
    out = ""
    for part in re.split(r"(\{X\d+\})", e["jp"]):
        m = re.fullmatch(r"\{X(\d+)\}", part)
        if m:
            out += part
            continue
        if not part.strip(_BLANK):
            out += part if part.startswith("】") else ""
            continue
        head = ""
        if part.startswith("】"):
            head, part = "】", part[1:]
        sp = _SPEAKER.match(part)
        if sp:
            head, part = head + sp.group(), part[sp.end():]
        if part.startswith("【") and "】" not in part[:12]:
            head, part = head + "【", part[1:]
        out += head + (pseudo(e["id"], 2 * len(part)) if part.strip(_BLANK) else part)
    return out


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    set_calls(cfg)
    set_engine(cfg)
    img, cfg2 = _install(cfg, src)
    vol = img.volumes[0]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        if mode == "pseudo":
            text = pseudo_text(e) if e["kind"] != "record" else pseudo(e["id"], e["max_cells"])[:e["max_cells"]]
        else:
            text = e["en"]
        for r in e["refs"]:
            f, a = r.rsplit(":", 1)
            ids[(f, int(a, 16))] = e["id"]
            if text:
                by_ref[(f, int(a, 16))] = text
    warn, done = [], 0
    store = Scripts(vol, cfg2)
    set_shared(store)
    for name, path in store.items:
        d = store.read(path)
        values = {a: t for (f, a), t in by_ref.items() if f == name}
        new = rebuild(d, values, warn, ids, name)
        room = cfg.get("script_room", SCRIPT_ROOM)
        if len(new) > room and mode != "pseudo":
            raise SystemExit("%s: %d bytes, the script buffer holds %d; shorten these strings: %s" % (
                name, len(new), room, ", ".join(sorted({ids[(name, a)] for a in values}))))
        cut = 0
        while len(new) > room:
            # (the --pseudo filler: every string cut in proportion until the script fits)
            total = sum(len(v) for v in values.values())
            ratio = max(0.0, 1 - (len(new) - room) * 1.1 / max(1, total))
            before = total
            for a in values:
                v = values[a]
                keep = max(min(len(v), 4), int(len(v) * ratio))
                # (a token is not cut through)
                while keep < len(v) and "{" in v[:keep] and "}" not in v[v.rindex("{", 0, keep):keep]:
                    keep += 1
                values[a] = v[:keep]
            after = sum(len(v) for v in values.values())
            if after == before:
                raise SystemExit("%s: the script does not fit its buffer even with its filler cut" % name)
            cut += before - after
            new = rebuild(d, values, [], ids, name)
        if cut:
            warn.append("%s: the filler was cut by %d letters to fit the script buffer" % (name, cut))
        if new != d:
            tokenize(new)
            store.write(path, new)
            done += 1
    store.commit()
    for spec in cfg.get("records", []):
        path = cfg2["game_dir"] + "/" + spec["file"]
        data = bytearray(vol.read(path))
        for at, size, _text in records(bytes(data), spec):
            text = by_ref.get((spec["file"], at))
            if text:
                if len(text) > (size - 1) // 2:
                    warn.append("%s: %d letters, the field has room for %d" % (
                        ids[(spec["file"], at)], len(text), (size - 1) // 2))
                data[at:at + size] = record_bytes(text, size)
        if bytes(data) != vol.read(path):
            vol.write(path, bytes(data))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
