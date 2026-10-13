"""English for FourNine's N.A.V.A.L system (pc98tl/diana.py: Waku Waku Mahjong Panic!): strings.json in,
a patched image out.

The programs draw text through one routine (DIANA.EXE for the scenario, SONNET.EXE and TYPHON.EXE for
the mahjong); the patch (`diana.hook`) makes it draw ASCII 21h-7Eh as half-width letters, a byte and
a cell each (a space was already a half-width blank).

Strings (refs FILE:place, the place in the script as DIANA reads it, or in the program's image):

* "msg": a script's message (SNR/*.DSD; drawn by 15h), a page of it (a page ends with a key and the
  window cleared).  `max_cells` is the window's width in letters; the patcher breaks the English
  between words and starts a new page (a key, the window cleared) when the window's lines are
  full.  A message that opens with a speaker's label ("【 ... 】" or {L}) has its later lines
  indented by the label's width, as the Japanese does.
* "item": a menu drawn by 15h in a small window: one item a line (\\n between them, as in the
  Japanese); a line past `max_cells` letters is cut and reported.
* "quip": a mahjong opponent's line (DAT/*.DAT, read by SONNET or TYPHON): broken between words
  at `max_cells` letters; the file (its lines and their table) is written anew.
* "name": an opponent's name (DAT/*.DAT's head), "label": a string in a program or in a script's
  table: in place, `max_cells` its room in bytes (a letter a byte, a full-width character two);
  padded with spaces (fixed-width fields keep their places); past it cut and reported.
* "console": a DOS message (printed with "$" at its end): in place, plain text.

Tokens: {N} the player's name, {L} the player's label (as a speaker), {K} a wait for a key, {M}
the place a later text goes on from, {W} (in a label) a key and the window cleared; {XX..} other
control codes and their operands, in hex (colours {1Dnn}, {1Enn}, the style {1Fnn}, a face {06nn},
a sound {08nn}, a pause {10nn}): keep them where the Japanese has them.

A script may take any length: its strings are laid out again in the room the Japanese leaves and
after it; one past DIANA's buffer (4268h bytes) is split into further copies of itself, each
keeping the strings its part of the code draws: the first goes on to the next with 1Fh at the
operation where the next part begins, and the next part's first operation jumps there.
"""
import json
import os
import re
import struct

from . import diana as D
from . import lzexe
from .alice_game import MTL_NOTE
from .alice_sys2_tl import sha256
from .disk import DiskImage
from .text import pseudo

PREFIX = {"msg": "m", "item": "i", "quip": "q", "name": "n", "label": "l", "console": "t"}
NAMED = {0x01: "W", 0x02: "K", 0x03: "M", 0x04: "N", 0x07: "L"}
CODE = {v: k for k, v in NAMED.items()}
TOKEN = re.compile(r"\{(N|L|K|M|W|[0-9A-F]{2}(?:[0-9A-F]{2}){0,2})\}")
TOKEN_CELLS = {"N": 12, "L": 14}            # the player's name (six characters), the label 【 name 】
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}
PROGRAMS = ("DIANA.EXE", "SONNET.EXE", "TYPHON.EXE", "NAVAL.EXE")
DRAWERS = ("DIANA.EXE", "SONNET.EXE", "TYPHON.EXE")
DAT_HEAD = 0x2E
DAT_NAME = 12
DAT_ROOM = 0x4E2                            # SONNET's and TYPHON's buffer for an opponent's file
KANA = re.compile(rb"\x82[\x9f-\xf1]|\x83[\x40-\x96]|[\x88-\x9f\xe0-\xea][\x40-\xfc]")


# ---- the text ----

def _units(b):
    return [u for _i, u in D.units(b + b"\0", 0)]


def _char(u):
    try:
        ch = u.decode("cp932")
    except UnicodeDecodeError:
        return None
    if len(ch) != 1 or 0xE000 <= ord(ch) <= 0xF8FF:
        return None
    return ch


def show(b):
    """A string (no 00h) as text: characters, a space, \\n, tokens."""
    out = ""
    for u in _units(b):
        c = u[0]
        if c >= 0x80:
            ch = _char(u)
            out += ch if ch else "{%s}" % u.hex().upper()
        elif c == 0x20:
            out += " "
        elif c == 0x0D:
            out += "\n"
        elif c in NAMED:
            out += "{%s}" % NAMED[c]
        else:
            out += "{%s}" % u.hex().upper()
    return out


def _parts(text):
    """[(kind, bytes, cells)]: "c" a letter or character, "s" a space, "n" a new line, "t" a token."""
    out, pos = [], 0
    for m in list(TOKEN.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        for ch in text[pos:end]:
            ch = SUBST.get(ch, ch)
            for c in ch:
                if c == "\n":
                    out.append(("n", b"\x0d", 0))
                elif c == " ":
                    out.append(("s", b" ", 1))
                elif "!" <= c <= "~":
                    out.append(("c", c.encode(), 1))
                else:
                    try:
                        b = c.encode("cp932")
                    except UnicodeEncodeError:
                        b = b"?"
                    out.append(("c", b, len(b)))
        if m:
            t = m.group(1)
            b = bytes([CODE[t]]) if t in CODE else bytes.fromhex(t)
            out.append(("t", b, TOKEN_CELLS.get(t, 0)))
            pos = m.end()
    return out


def encode(text):
    return b"".join(b for _k, b, _c in _parts(text))


def cells(text):
    return sum(c for _k, _b, c in _parts(text))


def _words(parts):
    """[[part, ...] a word or a space or a new line]"""
    out, cur = [], []
    for p in parts:
        if p[0] in ("s", "n"):
            if cur:
                out.append(cur)
                cur = []
            out.append([p])
        else:
            cur.append(p)
    if cur:
        out.append(cur)
    return out


def layout(text, width, lines, col=0, line=0):
    """A message's bytes: broken between words at width cells, a new page (01h) after `lines` lines;
    later lines indented by an opening speaker's label; from col on the page's line line (a string
    going on from the mark another left)."""
    parts = _parts(text)
    lead = []
    while parts and parts[0][0] == "t" and parts[0][2] == 0:
        lead.append(parts.pop(0))
    indent = 0
    if parts and (parts[0][1] == "【".encode("cp932") or (parts[0][0] == "t" and parts[0][1] == b"\x07")):
        k = 1
        if parts[0][0] != "t":
            k = next((i + 1 for i, p in enumerate(parts) if p[1] == "】".encode("cp932")), 0)
        w = sum(p[2] for p in parts[:k])
        if k and w <= width // 2:
            indent = w
    rows, cur, used = [], [], col
    pad = [("s", b" ", 1)] * indent

    def newline():
        nonlocal cur, used
        rows.append(cur)
        cur, used = list(pad), indent
    for word in _words(parts):
        if word[0][0] == "n":
            newline()
            continue
        if word[0][0] == "s":
            if used and used < width:
                cur.append(word[0])
                used += 1
            continue
        w = sum(p[2] for p in word)
        if used + w > width and used > indent:
            while cur and cur[-1][0] == "s" and len(cur) > indent:
                cur.pop()
            newline()
        for p in word:
            if used + p[2] > width and used > indent:
                newline()
            cur.append(p)
            used += p[2]
    rows.append(cur)
    out = bytearray(b"".join(p[1] for p in lead))
    for i, row in enumerate(rows):
        if i:
            line += 1
            if line >= lines:
                out += b"\x01"
                line = 0
            else:
                out += b"\x0d"
        out += b"".join(p[1] for p in row)
    return bytes(out)


def end_column(b, col=0, line=0):
    """(column, line) a string's bytes leave the drawer at (from col on line)."""
    for i, u in D.units(b + b"\0", 0):
        if u == b"\x0d":
            col, line = 0, line + 1
        elif u == b"\x01":
            col, line = 0, 0
        elif u[0] >= 0x80:
            col += 2
        elif u[0] >= 0x20:
            col += 1
        elif u[0] in (0x04, 0x07):
            col += TOKEN_CELLS["N" if u[0] == 4 else "L"]
    return col, line


def draw_order(d, ops, grps):
    """The groups in the order the code draws them."""
    group_at = {p: g for g in grps for p in g[2]}
    order = []
    for pc in sorted(ops):
        if ops[pc][0] == D.DRAW and group_at.get(D.W(d, pc + 3)) not in order:
            order.append(group_at[D.W(d, pc + 3)])
    return order


def marked(b):
    """Whether a string ends with a mark (03h): the next one goes on from there."""
    return [u for _i, u in D.units(b + b"\0", 0)][-1:] == [b"\x03"]


def page_lines(found):
    """{(window, width, height): the lines a page holds}, as the Japanese uses them (a chain of
    strings going on from marks counted together)."""
    most = {}
    for name, d, ops, grps, drawn in found:
        carry = {}
        for g in draw_order(d, ops, grps):
            key = drawn[g[0]]
            col, line = carry.get(key[0], (0, 0))
            body = b""
            for p, body, sep in pieces(d, g):
                col, line = end_column(body, col, line)
                most[key] = max(most.get(key, 0), line + 1)
                col, line = end_column(sep[:1], col, line) if sep[:1] in (b"\x01", b"\x0d") else (col, line)
            carry[key[0]] = (col, line) if marked(body) else (0, 0)
    return most


def _rows(text):
    """The widths of a text's lines (to a new line or a new page)."""
    return [cells(r) for r in re.split(r"\n|\{W\}", text)]


def lines_of(text, width, col=0):
    """A menu's bytes: its lines as given, each cut at width cells (the first from col: going on
    from a mark); a cut line keeps its codes.  (bytes, the widest line)"""
    out, widest = [], 0
    for line in text.split("\n"):
        b, used, cut = bytearray(), col, False
        for k, pb, c in _parts(line):
            if c and (cut or used + c > width):
                cut = True
                continue
            b += pb
            used += c
        widest = max(widest, cells(line) + col if cut else used)
        out.append(bytes(b))
        col = 0
    return b"\x0d".join(out), widest


def in_place(text, room):
    """A label's bytes, cut at room and padded with spaces.  (bytes, its full length)"""
    b, full = bytearray(), 0
    for k, pb, c in _parts(text):
        full += len(pb)
        if len(b) + len(pb) <= room and full == len(b) + len(pb):
            b += pb
    return bytes(b).ljust(room, b" "), full


# ---- the strings in a script ----

def groups(d, ops):
    """[(start, end, [piece starts])]: the strings 15h draws, those overlapping (one drawn from its
    middle too) together; a piece is a page (to after an 01h) or runs to the next place drawn."""
    starts = sorted(D.draws(d, ops))
    out = []
    for a in starts:
        e = D.end(d, a)
        if out and a < out[-1][1]:
            out[-1][2].append(a)
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([a, e, [a]])
    res = []
    for a, e, refs in out:
        cut = set(refs)
        for i, u in D.units(d, a):
            if u == b"\x01" and i + 1 < e - 1:
                cut.add(i + 1)
        res.append((a, e, sorted(cut)))
    return res


def pieces(d, group):
    """[(start, text bytes, separator)] of a group: the separator (01h, 0Dh or 00h) ends the piece."""
    a, e, cut = group
    out = []
    for k, p in enumerate(cut):
        q = cut[k + 1] if k + 1 < len(cut) else e
        body = d[p:q]
        if q == e:
            body, sep = body[:-1], b"\0"
            last = [u for _i, u in D.units(body + b"\0", 0)][-1:]
            if last == [b"\x01"]:
                body, sep = body[:-1], b"\x01\0"
        else:
            last = [u for _i, u in D.units(body + b"\0", 0)][-1:]
            sep = last[0] if last and last[0] in (b"\x01", b"\x0d") else b""
            body = body[:len(body) - len(sep)]
        out.append((p, body, sep))
    return out


def _defs(d, ops):
    return sorted((pc, d[pc + 2] & 7, 2 * d[pc + 7], 0 if d[pc + 2] & 8 else d[pc + 8])
                  for pc, (op, n, t) in ops.items() if op in (0x03, 0x63))     # (63h: its place from variables)


def common_windows(scripts, cfg):
    """{window: (game.json's "windows" for it or None, {(width cells, height lines): how often the
    game's scripts set it})}."""
    seen = {}
    for name, d, ops in scripts:
        for pc, w, cw, h in _defs(d, ops):
            seen.setdefault(w, {}).setdefault((cw, h), 0)
            seen[w][(cw, h)] += 1
    fixed = {int(w): tuple(v) for w, v in cfg.get("windows", {}).items()}
    return {w: (fixed.get(w), seen.get(w, {})) for w in set(seen) | set(fixed)}


def _pick(common, win, wide):
    """A window a string is drawn in when its script does not set it: game.json's, else of the
    game's settings for it (with three lines or more; of a message's width if any) the narrowest
    holding the string's widest Japanese line (the most often set first), else the most often set."""
    fixed, seen = common.get(win, (None, {}))
    if fixed:
        return fixed
    if not seen:
        return (58, 4)
    fits = [k for k in seen if k[0] >= wide and k[1] >= 3]
    pool = [k for k in fits if k[0] >= 56] or fits        # (a message's window before a menu's)
    if not pool:
        return max(seen, key=lambda k: seen[k])
    return min(pool, key=lambda k: (k[0], -seen[k]))


def window_of(d, ops, common=None):
    """{15h's offset: (window, width cells, height lines)} by the last 03h (or 63h) before it for its
    window (else `_pick`); the height 0: the window scrolls (03h's window with 8), a string going
    on where the last one stopped."""
    common = common or {}
    defs = _defs(d, ops)
    out = {}
    for pc, (op, n, t) in ops.items():
        if op != D.DRAW:
            continue
        win = d[pc + 2] & 7
        best = None
        for at, w, cw, h in defs:
            if w == win and at < pc:
                best = (cw, h)
        if best:
            out[pc] = (win,) + best
        else:
            a = D.W(d, pc + 3)
            out[pc] = (win,) + _pick(common, win, max(_rows(show(d[a:D.end(d, a) - 1]))))
    return out


def _gap_strings(d, covered, base=0):
    """[(offset, bytes)] Shift-JIS strings (ended by 00h) in d outside covered."""
    out, i = [], 0
    while i < len(d):
        if covered[i] or (i and d[i - 1] not in (0, 0x24) and d[i - 2:i] != bytes([0xF0, 0xFF])) or d[i] == 0:
            i += 1
            continue
        while 0x21 <= d[i] <= 0x7E and i + 1 < len(d) and not covered[i + 1]:
            i += 1                      # (a table's last bytes before the text)
        s = _clean(d, i)
        if s is None:
            i += 1
            continue
        if not any(covered[i:i + len(s)]):
            out.append((base + i, s))
        i += len(s) + 1
    return out


def _clean(d, i):
    """The string at i if it is all characters, spaces and control codes, ended by 00h (with two
    characters of kana or kanji), else None."""
    j, n = i, 0
    while j < len(d) and d[j]:
        c = d[j]
        if c >= 0x80:
            if j + 1 >= len(d) or not (0x40 <= d[j + 1] <= 0xFC) or d[j + 1] == 0x7F:
                return None
            if not (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF):
                return None
            if c not in (0x85, 0x86, 0xEB) and _char(d[j:j + 2]) is None:
                return None
            if KANA.match(d, j):
                n += 1
            j += 2
        elif c >= 0x20:
            if c == 0x24 or c > 0x7E:
                return None
            j += 1
        elif c in D.ONE:
            j += 1
        elif c == 0x05:
            j += 3
        elif c in (0x1D, 0x1E, 0x1F, 0x06, 0x08, 0x10):
            j += 2
        else:
            return None
    if j >= len(d) or n < 2:
        return None
    return d[i:j]


def _console(image):
    """[(offset, bytes before the $)] DOS messages: Shift-JIS text and CR LF, ended by $."""
    out = []
    for m in re.finditer(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x23\x25-\x7e]|\r\n)+\$", image):
        s = m.group()[:-1]
        if len(KANA.findall(s)) < 2:
            continue
        try:
            s.decode("cp932")
        except UnicodeDecodeError:
            continue
        out.append((m.start(), s))
    return out


def program_strings(image, data=0):
    """[(offset, bytes, kind)] a program's strings in its data (from data): "console" ($), "label"
    (drawn, ended by 00h)."""
    cons = [(at, s) for at, s in _console(image) if at >= data]
    covered = bytearray(len(image))
    covered[:data] = bytes([1]) * data
    for at, s in cons:
        covered[at:at + len(s) + 1] = b"\1" * (len(s) + 1)
    out = [(at, s, "console") for at, s in cons]
    out += [(at, s, "label") for at, s in _gap_strings(image, covered)]
    return sorted(out)


def script_tables(d, ops, grps, org=0):
    """[(offset, bytes)] strings in a script outside its code and its drawn strings (tables); from
    org (a further file's place)."""
    covered = bytearray(len(d))
    covered[:org] = bytes([1]) * org
    for pc, (op, n, t) in ops.items():
        covered[pc:pc + n] = b"\1" * n
    for a, e, cut in grps:
        covered[a:e] = b"\1" * (e - a)
    return _gap_strings(d, covered)


def dat_table(d):
    """Where an opponent's file's table of lines begins: its first entry is the line right after it
    (2Eh in the first game; 3Ah in the second's 2JC files)."""
    for p in range(0x20, 0x80, 2):
        first = D.W(d, p)
        if not (p < first < len(d)) or (first - p) % 2:
            continue
        words = struct.unpack_from("<%dH" % ((first - p) // 2), d, p)
        if all(w == 0xFFFF or first <= w <= len(d) for w in words):
            return p, first
    raise ValueError("no table of lines")


def dat_strings(d):
    """(name bytes, [(index, offset, bytes)], the table's place, the first line's) of an opponent's
    file."""
    head, first = dat_table(d)
    out = []
    for k in range((first - head) // 2):
        v = D.W(d, head + 2 * k)
        if v != 0xFFFF:
            out.append((k, v, d[v:D.end(d, v) - 1]))
    return d[:DAT_NAME], out, head, first


class Store:
    """A release's files: the first game's in its folders (scripts in SNR/, packed or not; the
    opponents' files in DAT/); the second's in the 0Dnn.DAT archives, every file scrambled, and a
    changed file written beside them under its name (the programs open that first)."""

    def __init__(self, img, cfg):
        self.img, self.gd = img, cfg["game_dir"] + "/"
        vol = self.vol
        self.v = D.V2 if cfg.get("version") == 2 else D.V1
        self.overlay = cfg.get("overlay")
        self.members, self.home, self.archives = {}, {}, {}
        self.changed, self.last = {}, None
        if self.v.scrambled:
            for p, e in sorted(vol.walk()):
                nm = p[len(self.gd):]
                if p.startswith(self.gd) and re.fullmatch(r"0D0\d\.DAT", nm.upper()):
                    d = vol.read(p)
                    self.archives[nm] = [d, [name for name, at, size in D.archive(d)]]
                    for name, at, size in D.archive(d):
                        self.members.setdefault(name.upper(), d[at:at + size])
                        self.home.setdefault(name.upper(), nm)

    def _names(self):
        if self.v.scrambled:
            return sorted(self.members)
        return sorted(p[len(self.gd):] for p, e in self.vol.walk() if p.startswith(self.gd)
                      and not e["is_dir"])

    def scripts(self):
        return [n for n in self._names() if n.upper().endswith(".DSD")]

    def dats(self):
        return [n for n in self._names() if n.upper().endswith(".DAT") and
                re.match(r"(2JC|FC4)", n.rsplit("/", 1)[-1].upper()) and
                (self.v.scrambled or n.upper().startswith("DAT/"))]

    def read(self, name):
        if self.v.scrambled:
            return D.unscramble(self.members[name.upper()])
        return D.load(self.vol.read(self.gd + name))

    def exists(self, name):
        if self.v.scrambled and (name.upper() in self.members or name.upper() in self.changed):
            return True
        try:
            self.vol.find(self.gd + name)
            return True
        except FileNotFoundError:
            return False

    @property
    def vol(self):
        return self.img.volumes[0]

    def write(self, name, data, create=True):
        """A file written (a full disk's volume grown once, then refused); in the second game a
        script or an opponent's file goes into its archive (a new one into the archive of the
        file written before it), the archives written by `flush`."""
        if self.v.scrambled and name.upper().endswith((".DSD", ".DAT")) and name not in self.archives:
            key = name.upper()
            home = self.home.get(key, self.last)
            if key not in self.home:
                self.home[key] = home
                self.archives[home][1].append(name.upper())
            self.changed[key] = D.scramble(data)
            self.last = home
            return
        put = self.vol.create if create else self.vol.write
        try:
            put(self.gd + name, data)
        except IOError:
            if not self.img.grow_volume(0):
                raise SystemExit("the disk is full: %s does not fit (%d bytes)" % (name, len(data)))
            try:
                (self.vol.create if create else self.vol.write)(self.gd + name, data)
            except IOError:
                raise SystemExit("the disk is full even grown: %s does not fit (%d bytes)" % (name, len(data)))

    def flush(self):
        """The archives with changed members written again."""
        for nm, (d, names) in sorted(self.archives.items()):
            if not any(n.upper() in self.changed for n in names):
                continue
            members = [(n, self.changed.get(n.upper(), self.members.get(n.upper()))) for n in names]
            self.write(nm, D.write_archive(d, members), create=False)

    def script(self, name, mains=None):
        """(the script as DIANA's buffer holds it from offset 0, its operations); the further file
        after zeros to its place, parsed from where the other scripts call it (mains: their
        operations)."""
        d = self.read(name)
        if self.overlay and name.upper() == self.overlay.upper():
            starts = sorted({D.W(md, pc + self.v.jump[op]) for md, mops in (mains or [])
                             for pc, (op, n, t) in mops.items() if op in self.v.jump
                             and D.W(md, pc + self.v.jump[op]) >= self.v.overlay})
            d = bytes(self.v.overlay) + d
            return d, D.parse(d, self.v, starts)
        return d, D.parse(d, self.v)

    def all_scripts(self):
        """[(name, script, operations)], the further file last."""
        out, mains = [], []
        for name in self.scripts():
            if self.overlay and name.upper() == self.overlay.upper():
                continue
            d, ops = self.script(name)
            out.append((name, d, ops))
            mains.append((d, ops))
        if self.overlay and self.overlay.upper() in [n.upper() for n in self.scripts()]:
            d, ops = self.script(self.overlay, mains)
            out.append((self.overlay, d, ops))
        return out


def program_image(raw):
    """(the program's image, a function writing a program from a changed image): LZEXE programs
    unpacked (written unpacked, asking for no more memory than before), others as they are."""
    try:
        p = lzexe.unpack(raw)
        return p["image"], lambda image: lzexe.build(p, image, keep_most=True)
    except ValueError:
        hdr = D.W(raw, 8) * 16
        return raw[hdr:], lambda image: raw[:hdr] + image


def _quip_room(dats):
    widest, most = 0, 1
    for name, d in dats:
        for k, at, s in dat_strings(d)[1]:
            for page in show(s).split("{W}"):
                rows = [cells(r) for r in page.split("\n")]
                widest = max([widest] + rows)
                most = max(most, len(rows))
    return widest, most


# ---- extraction ----

def scan(vol_img, cfg):
    """[(kind, jp, ref, room, note)] every string, in order."""
    out = []
    store = Store(vol_img, cfg)
    vol, gd = store.vol, store.gd
    scripts = store.all_scripts()
    common = common_windows(scripts, cfg)
    found, fill = [], {}
    for name, d, ops in scripts:
        grps = groups(d, ops)
        wins = window_of(d, ops, common)
        drawn = {}
        for pc, (op, n, t) in ops.items():
            if op == D.DRAW:
                drawn.setdefault(D.W(d, pc + 3), wins[pc])
        found.append((name, d, ops, grps, drawn))
        for g in grps:
            win, width, height = drawn[g[0]]
            rows = [w for _p, b, _s in pieces(d, g) for w in _rows(show(b))]
            fill[(win, width)] = max([fill.get((win, width), 0)] + rows)
    pl = page_lines(found)
    for name, d, ops, grps, drawn in found:
        for g in grps:
            win, width, height = drawn[g[0]]
            per_page = _lines(drawn[g[0]], pl)
            ps = pieces(d, g)
            texts = [show(b) for _p, b, _s in ps]
            jp_rows = [w for t in texts for w in _rows(t)]
            widest = max(jp_rows + [0])
            if width - 4 <= fill[(win, width)] < width:
                width = fill[(win, width)]  # (the Japanese's own edge: the window's frame takes the rest)
            msg = width >= 40 and (height >= 3 or height == 0)
            for (p, b, sep), jp in zip(ps, texts):
                ref = "%s:%04x" % (name, p)
                if msg and height == 0:
                    out.append(("msg", jp, ref, max(width, widest),
                                "a scrolling text (window %d): %d letters a line; broken between words; "
                                "it ends with a new line" % (win, max(width, widest))))
                elif msg:
                    out.append(("msg", jp, ref, max(width, widest),
                                "a message (window %d): %d letters a line, %d lines a page; broken between "
                                "words, a new page when the window is full" % (win, max(width, widest),
                                                                               per_page)))
                else:
                    out.append(("item", jp, ref, max(width, widest),
                                "a menu (window %d): an item a line, each up to %d letters (cut past it)"
                                % (win, max(width, widest))))
        for at, s in script_tables(d, ops, grps, store.v.overlay if name.upper() == (store.overlay or "").upper() else 0):
            out.append(("label", show(s), "%s:%04x" % (name, at), len(s),
                        "a script's table entry: in place, %d bytes (a letter a byte), padded with spaces"
                        % len(s)))
    dats = [(n, store.read(n)) for n in store.dats()]
    qw, ql = _quip_room(dats)
    for name, d in dats:
        nm, items, _h, _f = dat_strings(d)
        out.append(("name", show(nm.rstrip(b"\0")), "%s:name" % name, DAT_NAME,
                    "an opponent's name: in place, %d bytes (a letter a byte)" % DAT_NAME))
        for k, at, s in items:
            out.append(("quip", show(s), "%s:%d" % (name, k), qw,
                        "a mahjong opponent's line: %d letters a line, %d lines; broken between words"
                        % (qw, ql)))
    for prog in PROGRAMS:
        image = program_image(vol.read(gd + prog))[0]
        for at, s, kind in program_strings(image, int(cfg["data"][prog], 16)):
            if kind == "console":
                out.append(("console", s.decode("cp932").replace("\r\n", "\n"), "%s:%05x" % (prog, at),
                            len(s), "a DOS message: in place, %d bytes; plain text" % len(s)))
            elif prog in DRAWERS:
                out.append(("label", show(s), "%s:%05x" % (prog, at), len(s),
                            "the program's string: in place, %d bytes (a letter a byte), padded with "
                            "spaces" % len(s)))
    return out


def _page_lines(height):
    return max(1, height - 1)


def _lines(key, pl):
    """The lines a page of a window holds: its height but one, at most as many as the Japanese
    fills."""
    return max(1, min(_page_lines(key[2]), pl.get(key, 1 << 20)))


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    merged, order = {}, []
    for kind, jp, ref, room, note in scan(DiskImage(src), cfg):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
            continue
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
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
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


# ---- a script laid out again ----

def _place(out, free, blob):
    """blob's offset: the smallest free run it fits, else the end (from a free run ending there)."""
    best = None
    for k, (a, n) in enumerate(free):
        if n >= len(blob) and (best is None or n < free[best][1]):
            best = k
    if best is None:
        tail = next((k for k, (a, n) in enumerate(free) if n and a + n == len(out)), None)
        at = free[tail][0] if tail is not None else len(out)
        if tail is not None:
            free[tail] = (at, 0)
        out[at:] = blob
        return at
    a, n = free[best]
    out[a:a + len(blob)] = blob
    free[best] = (a + len(blob), n - len(blob))
    return a


def build(d, ops, grps, new, keep=None, cuts=None, entry=None, v=D.V1, fixed=None):
    """The script with its groups' pieces as new gives them ({piece start: bytes with the separator};
    else as they were); only the groups keep lists (None: all); cuts: {offset: a part's name},
    there a 1Fh to it; entry: the first operation a jump there; fixed: {a group's start: the place
    it is put elsewhere (the pool below a further file)}."""
    fixed = fixed or {}
    out = bytearray(d)
    free = []
    names = D.file_operands(d, ops, v)          # (a file's name is read from the byte before it, the
    for a, e, c in sorted(grps):             # 00h ending a string: those bytes stay)
        out[a:e] = bytes(e - a)
        for i in range(a, e):
            if i in names:
                continue
            if free and free[-1][0] + free[-1][1] == i:
                free[-1] = (free[-1][0], free[-1][1] + 1)
            else:
                free.append((i, 1))
    where = {}
    order = [g for g in grps if keep is None or g[0] in keep]
    blobs = []
    for g in order:
        b = bytearray()
        offs = {}
        for p, body, sep in pieces(d, g):
            offs[p] = len(b)
            b += new.get(p, body + sep)
        blobs.append((g, bytes(b), offs))
    for g, b, offs in sorted(blobs, key=lambda x: -len(x[1])):
        at = fixed[g[0]] if g[0] in fixed else _place(out, free, b)
        for p, o in offs.items():
            where[p] = at + o
    for pc, (op, n, t) in ops.items():
        if op == D.DRAW:
            a = D.W(d, pc + 3)
            struct.pack_into("<H", out, pc + 3, where.get(a, 0))
    names = {}
    for at, name in sorted((cuts or {}).items()):
        if name not in names:
            names[name] = _place(out, free, name.encode() + b"\0")
        out[at:at + 4] = struct.pack("<HH", D.GOTO, names[name])
    if entry is not None:                   # (the operations under the jump go on in a copy, and
        head, at = [], 0                    # the code going to them goes to the copy)
        while at < 4:
            head.append(at)
            at += ops[at][1]
        stub = b"".join(d[pc:pc + ops[pc][1]] for pc in head)
        if ops[head[-1]][0] not in v.end:
            stub += struct.pack("<HH", D.JMP, at)
        sat = _place(out, free, stub)
        moved = {pc: sat + pc for pc in head}
        for pc in list(ops) + [sat + pc for pc in head]:
            src = pc - sat if pc >= sat and pc - sat in moved else pc
            if src not in ops:
                continue
            op, n, t = ops[src]
            for f in target_fields(d, src, op, n, v):
                w = D.W(out, pc + f)
                if w in moved:
                    struct.pack_into("<H", out, pc + f, moved[w])
        out[0:4] = struct.pack("<HH", D.JMP, entry)
    return bytes(out)


def target_fields(d, pc, op, n, v=D.V1):
    """The places (from pc) of an operation's jump targets."""
    if op == 0x13:
        return list(range(4, n, 2))
    if op in v.jump:
        return [v.jump[op]]
    return []


def group_bytes(d, g, new):
    return b"".join(new.get(p, body + sep) for p, body, sep in pieces(d, g))


def overlay_pool(d, ops, grps, new, v, org):
    """(the further file, the pool, {group: its place in the pool}): its strings that do not fit
    its room, largest first, moved to a pool kept at the top of the buffer below it by every
    script calling it."""
    fixed, pool = {}, b""
    order = sorted(grps, key=lambda g: -len(group_bytes(d, g, new)))
    while True:
        at = org - len(pool)
        places = {g: at + o for g, o in fixed.items()}
        out = build(d, ops, grps, new, v=v, fixed=places)
        if len(out) - org <= v.overlay_room:
            return out[org:], pool, places
        g = next((g for g in order if g[0] not in fixed), None)
        if g is None:
            raise ValueError("%d bytes, its room %d" % (len(out) - org, v.overlay_room))
        fixed = {k: o + len(group_bytes(d, g, new)) for k, o in fixed.items()}
        fixed[g[0]] = 0
        pool = group_bytes(d, g, new) + pool


def split(d, ops, grps, new, name, v=D.V1, org=0, room=None):
    """[(name, bytes)] the script, in parts when one is past DIANA's buffer: each part a copy
    entered at one operation (the first part at the start, a later one through a jump put at its
    start), running the code reached from there up to another part's entry, which goes to that
    part (1Fh); each copy keeps only the strings its code draws.  A further file (org: its place
    after the script) is not split."""
    room = room or v.room
    whole = build(d, ops, grps, new, v=v)
    if org:
        if len(whole) - org > v.overlay_room:
            raise ValueError("%d bytes, its room %d" % (len(whole) - org, v.overlay_room))
        return [(name, whole[org:])]
    if len(whole) <= room:
        return [(name, whole)]
    group_of = {}
    for g in grps:
        for p in g[2]:
            group_of[p] = g[0]
    draw_at = {pc: D.W(d, pc + 3) for pc, (op, n, t) in ops.items() if op == D.DRAW}
    targets = {x for op, n, t in ops.values() for x in t}
    # (no part begins inside a routine 54h calls: its return would go on in the part's copy of
    # the caller, without the caller's strings)
    called = D.reach(ops, {t[0] for op, n, t in ops.values() if op == 0x54 and t}, v=v)
    stem, ext = name.rsplit("/", 1)[-1].rsplit(".", 1)
    folder = name.rsplit("/", 1)[0] + "/" if "/" in name else ""
    entries = [0]

    def part_name(k):
        return name if k == 0 else "%s%s%s.%s" % (folder, stem[:7], chr(ord("A") + k), ext)

    def make(k, ents):
        stop = set(ents)
        seen = D.reach(ops, {ents[k]}, stop, v)
        keep = {group_of[draw_at[pc]] for pc in seen if pc in draw_at}
        cuts = {}
        for j, e in enumerate(ents):
            if j != k and _reaches(ops, seen, e, v):
                cuts[e] = part_name(j).replace("/", "\\").lower()
        return build(d, ops, grps, new, keep, cuts, ents[k] if k else None, v), seen
    while True:
        built = [make(k, entries) for k in range(len(entries))]
        over = [k for k, (b, seen) in enumerate(built) if len(b) > room]
        if not over:
            return [(part_name(k), b) for k, (b, seen) in enumerate(built)]
        if len(entries) >= 26:
            raise ValueError("too many parts")
        k = max(over, key=lambda j: len(built[j][0]))
        seen = built[k][1]
        cands = sorted(pc for pc in seen if pc != entries[k] and pc not in entries and ops[pc][1] >= 4
                       and (pc in targets or pc in draw_at) and pc not in called)
        best = None                         # (the new part past the room, what is left, the cut)
        for c in cands:
            ents = entries + [c]
            rest, part = len(make(k, ents)[0]), len(make(len(ents) - 1, ents)[0])
            key = (max(part - room, 0), rest, c)
            if rest < len(built[k][0]) and (best is None or key < best):
                best = key
        if best is None:
            raise ValueError("no place to split it")
        entries.append(best[2])


def _reaches(ops, seen, e, v=D.V1):
    """Whether the code in seen goes on to (or jumps to) e."""
    for pc in seen:
        op, n, t = ops[pc]
        if e in t or (pc + n == e and op not in v.end):
            return True
    return False


# ---- patching ----

def _pseudo(e):
    jp = e["jp"]
    lead = re.match(r"(?:\{(?:[0-9A-F]{2,6})\})*", jp).group()
    body = TOKEN.sub("", jp)
    if e["kind"] in ("msg", "quip"):
        label = re.match(r"【[^】]*】|\{L\}", jp[len(lead):])
        head = label.group() if label else ""
        tail = re.search(r"(?:\{(?:[0-9A-F]{2,6}|W|K|M)\})*$", jp).group()
        return lead + head + pseudo(e["id"], 2 * len(body) - cells(head)) + tail
    if e["kind"] == "item":
        out = []
        for line in jp.split("\n"):         # (an item's colours and marks kept: the game goes on with them)
            lead = re.match(r"(?:\{(?:[0-9A-F]{2,6}|M)\})*", line).group()
            tail = re.search(r"(?:\{(?:[0-9A-F]{2,6}|M)\})*$", line[len(lead):]).group()
            room = e["max_cells"] - cells(lead + tail)
            out.append(lead + (pseudo(e["id"], cells(line), 1.0)[:max(room, 0)] if TOKEN.sub("", line) else "") + tail)
        return "\n".join(out)
    if e["kind"] == "console":
        return pseudo(e["id"], e["max_cells"], 1.0)[:e["max_cells"]]
    tail = re.search(r"(?:\{(?:[0-9A-F]{2,6})\})*$", jp).group()
    room = e["max_cells"] - len(encode(lead + tail))
    return lead + pseudo(e["id"], room, 1.0)[:max(room, 0)] + tail


def _program(image, data, texts, warn, ids):
    img = bytearray(image)
    for at, s, kind in program_strings(image, data):
        t = texts.get(at)
        if t is None:
            continue
        if kind == "console":
            b = t.replace("\n", "\r\n").encode("cp932", "replace").replace(b"$", b"S")
            full = len(b)
            b = b[:len(s)].ljust(len(s), b" ")
        else:
            b, full = in_place(t, len(s))
        if full > len(s):
            warn.append("%s: %d bytes, room for %d (cut)" % (ids[at]["id"], full, len(s)))
        img[at:at + len(s)] = b
    return bytes(img)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"] + "/"
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    if not by_ref:
        img.save(dst)
        print("patched %s (%s mode, 0/%d strings translated)" % (dst, mode, len(doc["strings"])))
        return
    store = Store(img, cfg)
    v = store.v
    scripts = store.all_scripts()
    common = common_windows(scripts, cfg)
    is_overlay = lambda n: n.upper() == (store.overlay or "").upper()     # noqa: E731
    callers = {name for name, d, ops in scripts if v.overlay and not is_overlay(name) and any(
        op in v.jump and D.W(d, pc + v.jump[op]) >= v.overlay for pc, (op, n, t) in ops.items())}
    pool = b""
    found = []
    for name, d, ops in scripts:
        grps = groups(d, ops)
        wins = window_of(d, ops, common)
        drawn = {}
        for pc, (op, n, t) in ops.items():
            if op == D.DRAW:
                drawn.setdefault(D.W(d, pc + 3), wins[pc])
        found.append((name, d, ops, grps, drawn))
    pl = page_lines(found)
    for name, d, ops in sorted(scripts, key=lambda x: not is_overlay(x[0])):   # (the further file first)
        org = v.overlay if is_overlay(name) else 0
        grps = groups(d, ops)
        wins = window_of(d, ops, common)
        drawn = {}
        for pc, (op, n, t) in ops.items():
            if op == D.DRAW:
                drawn.setdefault(D.W(d, pc + 3), wins[pc])
        new = {}
        carry = {}                          # (where a string ending in a mark, 03h, left the next)
        for g in draw_order(d, ops, grps):
            win, width, height = drawn[g[0]]
            per_page = _lines(drawn[g[0]], pl)
            col, line = carry.get(win, (0, 0))
            b = b""
            for p, body, sep in pieces(d, g):
                ref = "%s:%04x" % (name, p)
                b = body
                if ref in by_ref:
                    e = ids[ref]
                    if e["kind"] == "msg":
                        if height == 0:
                            b = layout(by_ref[ref], e["max_cells"], 1 << 20, col) + bytes([0x0D])
                        else:
                            b = layout(by_ref[ref], e["max_cells"], per_page, col, line)
                    else:
                        b, widest = lines_of(by_ref[ref], e["max_cells"], col)
                        if widest > e["max_cells"]:
                            warn.append("%s: %d letters, room for %d (cut)" % (e["id"], widest, e["max_cells"]))
                    new[p] = b + sep
                col, line = end_column(b, col, line)
                if line >= per_page:
                    line = per_page - 1
                col, line = end_column(sep[:1], col, line) if sep[:1] in (b"\x01", b"\x0d") else (col, line)
            carry[win] = (col, line) if marked(b) else (0, 0)
        tables = {}
        for at, s in script_tables(d, ops, grps, org):
            ref = "%s:%04x" % (name, at)
            if ref in by_ref:
                b, full = in_place(by_ref[ref], len(s))
                if full > len(s):
                    warn.append("%s: %d bytes, room for %d (cut)" % (ids[ref]["id"], full, len(s)))
                tables[at] = b
        pooled = bool(pool) and name in callers
        if not new and not tables and not pooled:
            continue
        base = bytearray(d)
        for at, b in tables.items():
            base[at:at + len(b)] = b
        try:
            if org:
                data, pool, _places = overlay_pool(bytes(base), ops, grps, new, v, org)
                parts = [(name, data)]
                if pool:
                    warn.append("%s: %d bytes of its strings in the pool below it" % (name, len(pool)))
            else:
                parts = split(bytes(base), ops, grps, new, name, v, org,
                              v.overlay - len(pool) if pooled else None)
                if pooled:                  # (the pool at its place, below the further file)
                    parts = [(p, data.ljust(v.overlay - len(pool), b"\0") + pool) for p, data in parts]
        except ValueError as ex:
            raise SystemExit("%s: %s; shorten these strings: %s" % (name, ex, ", ".join(
                sorted({ids[r]["id"] for r in ids if r.startswith(name + ":")}))))
        if len(parts) > 1:
            warn.append("%s: split into %s" % (name, ", ".join(p for p, _d in parts)))
        for p, data in parts:               # (as it is: the game's resident expander does not read
            if p != name and store.exists(p):   # every stream pc98tl/sys98.py packs as the program does)
                raise SystemExit("%s: its part's name %s is taken" % (name, p))
            store.write(p, data)
    for name in store.dats():
        d = store.read(name)
        nm, items, head, first = dat_strings(d)
        ref = "%s:name" % name
        out = bytearray(d)
        if ref in by_ref:
            b, full = in_place(by_ref[ref], DAT_NAME)
            if full > DAT_NAME:
                warn.append("%s: %d bytes, room for %d (cut)" % (ids[ref]["id"], full, DAT_NAME))
            out[:DAT_NAME] = b
        if any("%s:%d" % (name, k) in by_ref for k, at, s in items):
            body = bytearray()
            table = bytearray(out[head:first])
            placed = {}                     # (entries with the same line share it, as they did)
            for k, at, s in items:
                r = "%s:%d" % (name, k)
                b = layout(by_ref[r], ids[r]["max_cells"], 99) if r in by_ref else s
                if b not in placed:
                    placed[b] = first + len(body)
                    body += b + b"\0"
                struct.pack_into("<H", table, 2 * k, placed[b])
            out = out[:head] + table + body + b"\0"
            room = cfg.get("dat_room", {}).get(name.rsplit("/", 1)[-1][:3].upper(), DAT_ROOM)
            if len(out) > room:
                raise SystemExit("%s: %d bytes, the programs read %d; shorten these strings: %s" % (
                    name, len(out), room, ", ".join(sorted({ids[r]["id"] for r in ids
                                                                if r.startswith(name + ":")}))))
        if bytes(out) != d:
            store.write(name, bytes(out))
    store.flush()
    for prog in PROGRAMS:
        texts = {int(r.split(":")[1], 16): t for r, t in by_ref.items() if r.startswith(prog + ":")}
        image, rebuild = program_image(store.vol.read(gd + prog))
        if prog in DRAWERS:
            image = D.hook(image)[0]
        elif not texts:
            continue
        pid = {int(r.split(":")[1], 16): e for r, e in ids.items() if r.startswith(prog + ":")}
        image = _program(image, int(cfg["data"][prog], 16), texts, warn, pid)
        store.write(prog, rebuild(image), create=False)
    store.write("MTL_NOTE.TXT", MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
