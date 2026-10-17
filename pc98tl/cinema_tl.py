"""English for Foster's CINEMA engine (pc98tl/cinema.py; Time Stripper Mako-chan): strings.json in, a
patched image out.

Strings:

* "msg": a message (op 09h; refs SCRIPT:address of the op): any length.  The window (game.json
  "window": its letters across and its rows) is filled from where the message before it left the
  cursor: a message after a speaker's name goes on along the name's row.  The patcher breaks the
  lines between words (the program's new line, \\n) and, when the window is full, ends the page
  (\\f) and waits for a key (op 3Fh) before the rest.  `\\n` in the English forces a new line.  A
  message whose Japanese starts with a full-width space (the space after the speaker's name) gets
  one space before the English when it has none.
* "name": a speaker's name (a message of its own, 【...】): one line, `max_cells` the Japanese's;
  a longer one leaves less of the row to the message after it.
* "item": a menu's item (refs SCRIPT:address of its text): one line in the menu's box, `max_cells`
  the menu's widest Japanese item (past it reported).
* "engine": TSM.COM's messages (refs TSM.COM:offset), printed by DOS: in their own bytes,
  `max_cells` the room; past it cut and reported.

English is ASCII, drawn half-width by the program (its ANK letters); another character is written
full-width in Shift-JIS when it has it, else `?`.  The scripts are game.json's "scripts" (names, `*`
for any letters).  A script with its English must end before the first file a script loads into
the buffer (op 03h: ESC.BIN at 7800h in Time Stripper Mako-chan), else before the buffer's end (the
paragraphs CINEMA.BIN gives it), a loaded file before the buffer's end: a longer build is refused
and names the script (game.json "script_room", the room the notes give, is checked against it).
A script that runs machine code from its own bytes (op 00h: AUTOEXEC.BIN) keeps its layout: a text
that fits is written in its place, a longer one after the script's end; with game.json
"relocate_code" (Zenith's ZT.BIN, its machine code after its last op) it is written again like the
others, the code moved with its own addresses (cinema.machine_code).  game.json "speaker_line"
(Zenith): a message's first line is its speaker's name, a "name" string of its own; a message the
Japanese splits around a command is a string a piece.
"""
import fnmatch
import json
import os
import re

from . import cinema
from .alice_sys2_tl import sha256
from .text import pseudo, sjis_cols

PREFIX = {"msg": "m", "name": "n", "item": "i", "engine": "e"}
ENGINE_RE = re.compile(rb"((?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+\.?)\r\n\$")
# (game.json "speaker_line", Zenith's: a speaker's name on a message's first line, the speech after it)
SPEAKER = re.compile(r"([^\n「」『』（）　]{1,8})\n(?=[「『（])")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


class Game:
    """The archive's members, CINEMA.BIN's build, the scripts (game.json "scripts": their names, `*`
    for any letters), where each runs in the buffer (a file op 03h loads, as ESC.BIN, at the address
    it gives; the others at 0) and how far it may reach (the scripts at 0: the first such file; a
    loaded one: the buffer's end)."""

    def __init__(self, vol, cfg):
        self.flags, self.mems = cinema.members(vol.read(cfg["archive"]))
        by = {m[0]: m for m in self.mems}
        self.build = cinema.Build(cinema.data(by["CINEMA.BIN"]))
        self.speaker_line = bool(cfg.get("speaker_line"))
        self.names = [m[0] for m in self.mems if any(fnmatch.fnmatchcase(m[0], p) for p in cfg["scripts"])]
        self.base = {}
        for n in self.names:
            try:
                sc = cinema.Script(cinema.data(by[n]), self.build)
            except ValueError:
                continue
            for a, (op, _e) in sc.ops.items():
                if op == 0x03:
                    f = sc.d[a + 5:sc.d.index(0, a + 5)].decode("ascii").upper()
                    self.base[f] = sc.w(a + 3)
        self.top = min(list(self.base.values()) + [self.build.buffer])

    def base_of(self, name):
        return self.base.get(name, 0)

    def limit_of(self, name):
        return self.build.buffer if name in self.base else self.top

    def script(self, name, d):
        return cinema.Script(d, self.build, self.base_of(name))


def _cells(text):
    return sjis_cols(text.encode("cp932", "replace"))


def _visible(t):
    return bool(t.strip("　 \n"))


def _is_name(t):
    return t.startswith("【") and t.endswith("】") and "\n" not in t


class Text:
    """A message (op 09h) or a menu's item: its pieces (cinema.pieces) and its strings, [(ref, kind,
    index of the piece)]: a message's text, or a speaker's name (a message of its own, or the run
    before the message's text in the same op), or an item."""

    def __init__(self, name, a, kind, s, e, d, base, menu, speaker_line=False):
        self.a, self.kind, self.s, self.e, self.menu = a, kind, s, e, menu
        self.pieces = cinema.pieces(d[s - base:e - base])
        runs = [k for k, (c, v) in enumerate(self.pieces) if c == "t" and _visible(v)]
        ref = "%s:%04x" % (name, a)
        self.strings = []
        if kind == "item":
            if len(runs) > 1:
                raise ValueError("%s: a menu's item with commands inside" % ref)
            self.strings = [(ref, "item", k) for k in runs]
            return
        ends_page = any(c == "c" and v == b"\\f" for c, v in self.pieces)
        if runs and speaker_line:
            # (Zenith's: the speaker's name on the message's first line, the speech after it: the name a
            # string of its own, the new line between them kept)
            k0 = runs[0]
            m = SPEAKER.match(self.pieces[k0][1])
            if m:
                self.pieces[k0:k0 + 1] = [("t", m.group(1)), ("c", b"\\n"), ("t", self.pieces[k0][1][m.end(1) + 1:])]
                runs = [k0] + [k + 2 for k in runs]
                self.strings = [(ref + ":name", "name", k0)]
                rest = runs[1:]
                for n, k in enumerate(rest):
                    self.strings.append((ref if n == len(rest) - 1 else "%s:%d" % (ref, n + 1), "msg", k))
                return
        if len(runs) == 1:
            t = self.pieces[runs[0]][1]
            self.strings = [(ref, "name" if _is_name(t) and not ends_page else "msg", runs[0])]
        elif len(runs) == 2 and _is_name(self.pieces[runs[0]][1]):
            self.strings = [(ref + ":name", "name", runs[0]), (ref, "msg", runs[1])]
        elif runs and speaker_line:
            # (a message with a command between its texts (Zenith's waits): a string each)
            self.strings = [(ref if n == len(runs) - 1 else "%s:%d" % (ref, n + 1), "msg", k)
                            for n, k in enumerate(runs)]
        elif runs:
            raise ValueError("%s: a message with commands between %d texts" % (ref, len(runs)))


def script_texts(game, name, d):
    """(Script, [Text]) in address order."""
    sc = game.script(name, d)
    return sc, [Text(name, a, kind, s, e, d, sc.base, sc.items.get(a), game.speaker_line)
                for a, kind, (s, e) in sorted(cinema.texts(sc), key=lambda t: t[2][0])]


def engine_runs(com):
    """[(start, end)] of TSM.COM's messages (Shift-JIS before CR LF $)."""
    return [(m.start(1), m.end(1)) for m in ENGINE_RE.finditer(com)]


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    merged, order = {}, []

    def add(kind, jp, ref, cells, note=None):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], cells)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells}
        if note:
            merged[key]["note"] = note
        order.append(key)
    game = Game(vol, cfg)
    cols = cfg["window"][0]
    for m in game.mems:
        if m[0] not in game.names:
            continue
        sc, texts = script_texts(game, m[0], cinema.data(m))
        menus = {}
        for t in texts:
            for ref, kind, k in t.strings:
                if kind == "item":
                    menus[t.menu] = max(menus.get(t.menu, 0), _cells(t.pieces[k][1]))
        after_name = False
        for t in texts:
            for ref, kind, k in t.strings:
                jp = t.pieces[k][1]
                if kind == "item":
                    add("item", jp, ref, menus[t.menu], "a menu's item: one line in its box (the menu's widest "
                        "Japanese item)")
                elif kind == "name":
                    add("name", jp, ref, _cells(jp), "a speaker's name: the message after it goes on along "
                        "its row")
                else:
                    add("msg", jp, ref, cols, "after the speaker's name, on its row" if after_name else None)
                after_name = kind == "name"
    com_path = cfg["program"]
    com = vol.read(com_path)
    for s, e in engine_runs(com):
        add("engine", com[s:e].decode("cp932"), "%s:%04x" % (com_path.rsplit("/", 1)[-1], s), e - s,
            "TSM.COM's message (printed by DOS), in its own bytes")
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


class Cursor:
    """Where the program's cursor is in the window, message after message."""

    def __init__(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.col = self.row = 0
        self.clear = True

    def suffix(self, suf):
        for m in cinema.ESCAPE.finditer(suf):
            if m.group(1) == b"n":
                self.col, self.row = 0, self.row + 1
            elif m.group(1) == b"f":
                self.clear = True

    def start(self):
        if self.clear:
            self.col = self.row = 0
            self.clear = False

    def jp(self, visible):
        self.start()
        for k, line in enumerate(visible.split("\n")):
            if k:
                self.col, self.row = 0, self.row + 1
            self.col += _cells(line)
            while self.col > self.cols:
                self.col -= self.cols
                self.row += 1

    def english(self, text):
        """[page bytes]: the English broken between words; a new page (\\f) when the window is full."""
        self.start()
        pages, cur = [], bytearray()

        def newline():
            nonlocal cur
            if self.row + 1 >= self.rows:
                pages.append(bytes(cur) + b"\\f")
                cur = bytearray()
                self.col = self.row = 0
                return
            cur += b"\\n"
            self.col, self.row = 0, self.row + 1
        for k, para in enumerate(text.split("\n")):
            if k:
                newline()
            words = para.split(" ")
            for j, word in enumerate(words):
                b = cinema.encode(word)
                width = sjis_cols(b)
                space = 1 if j and self.col else 0
                if self.col + space + width > self.cols and self.col:
                    newline()
                    space = 0
                if space:
                    cur += b" "
                    self.col += 1
                while width > self.cols - self.col:
                    # (a word longer than the window: cut at its edge)
                    take, n = b"", 0
                    for ch in word:
                        cb = cinema.encode(ch)
                        if n + len(cb) > self.cols - self.col:
                            break
                        take += cb
                        n += len(cb)
                    word = word[len(take.decode("cp932")):] if take else word
                    cur += take
                    self.col += n
                    newline()
                    b = cinema.encode(word)
                    width = sjis_cols(b)
                cur += b
                self.col += width
        pages.append(bytes(cur))
        return pages


def _pseudo(e):
    if e["kind"] in ("item", "name"):
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"]]
    if e["kind"] == "engine":
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"]]
    return pseudo(e["id"], _cells(e["jp"]))


def build_script(game, name, d, by_ref, ids, rooms, cfg, warn, ratio=1.0):
    """The script with its English (None when nothing changed)."""
    sc, texts = script_texts(game, name, d)
    cur = Cursor(*cfg["window"])
    new_text, pages = {}, {}
    for t in texts:
        mine = {k: ref for ref, kind, k in t.strings if ref in by_ref}
        if t.kind == "item":
            for k, ref in mine.items():
                en = by_ref[ref]
                if _cells(en) > rooms[ref]:
                    warn.append("%s: %d letters, past its menu's room (%d)" % (ids[ref], _cells(en), rooms[ref]))
                new_text[t.s] = b"".join(cinema.encode(en) if j == k else
                                         (v if c == "c" else v.encode("cp932")) for j, (c, v) in enumerate(t.pieces))
            continue
        out = [bytearray()]
        for k, (c, v) in enumerate(t.pieces):
            if c == "c":
                if v == b"\\n" and cur.row + 1 >= cur.rows and mine:
                    # (a new line past the window's bottom: the page ends here, a key, a new page)
                    out[-1] += b"\\f"
                    out.append(bytearray())
                    cur.clear = True
                    continue
                out[-1] += v
                cur.suffix(v)
                continue
            if k not in mine:
                out[-1] += v.encode("cp932")
                if _visible(v):
                    cur.jp(v)
                continue
            en = by_ref[mine[k]]
            if ratio < 1.0:
                en = en[:max(4, int(len(en) * ratio))]
            kind = next(kd for _r, kd, j in t.strings if j == k)
            if kind == "msg" and v.startswith("　") and not en.startswith(" "):
                en = " " + en
            ps = cur.english(en)
            out[-1] += ps[0]
            for p in ps[1:]:
                out.append(bytearray(p))
        if not mine:
            continue
        if len(out) == 1:
            new_text[t.s] = bytes(out[0])
        else:
            pages[t.a] = [bytes(p) for p in out]
    if not new_text and not pages:
        return None
    if any(op == 0x00 for op, _e in sc.ops.values()) and not cfg.get("relocate_code"):
        # (it runs machine code from its own bytes: its layout stays; with game.json "relocate_code",
        # Zenith's, the code after the last op is moved with the rest, its own addresses with it)
        return cinema.redirect(sc, new_text, pages, game.limit_of(name))
    return cinema.rebuild(sc, new_text, pages, game.limit_of(name))


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    by_ref, ids, rooms = {}, {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            rooms[r] = e["max_cells"]
            if text:
                by_ref[r] = text
    warn, done = [], 0
    game = Game(vol, cfg)
    if cfg.get("script_room") != game.top:
        raise SystemExit("game.json: script_room is %s, the program gives the scripts %d bytes" % (
            cfg.get("script_room"), game.top))
    for m in game.mems:
        if m[0] not in game.names:
            continue
        d = cinema.data(m)
        try:
            new = build_script(game, m[0], d, by_ref, ids, rooms, cfg, warn)
        except OverflowError as ex:
            if mode != "pseudo":
                raise SystemExit("%s: %d bytes with its English, it may take %d; shorten these strings: %s" % (
                    m[0], ex.args[0] - game.base_of(m[0]), game.limit_of(m[0]) - game.base_of(m[0]),
                    ", ".join(sorted({ids[r] for r in by_ref if r.startswith(m[0] + ":")}))))
            # (the --pseudo filler: every message cut in proportion until the script fits)
            ratio, new = 1.0, None
            while new is None:
                ratio *= 0.9
                try:
                    new = build_script(game, m[0], d, by_ref, ids, rooms, cfg, [], ratio)
                except OverflowError:
                    continue
            warn.append("%s: the filler was cut to %d%% to fit the script's room" % (m[0], int(ratio * 100)))
        if new is not None and new != d:
            m[1], m[2], m[3] = 0, new, len(new)
            done += 1
    if done:
        vol.write(cfg["archive"], cinema.archive(game.flags, game.mems))
    com0 = vol.read(cfg["program"])
    com = bytearray(com0)
    for s, e in engine_runs(bytes(com)):
        ref = "%s:%04x" % (cfg["program"].rsplit("/", 1)[-1], s)
        if ref not in by_ref:
            continue
        t = by_ref[ref]
        if len(cinema.encode(t)) > e - s:
            warn.append("%s: cut to its %d bytes" % (ids[ref], e - s))
            while len(cinema.encode(t)) > e - s:
                t = t[:-1]
        b = cinema.encode(t)
        com[s:e] = b + b" " * (e - s - len(b))
    if bytes(com) != com0:
        vol.write(cfg["program"], bytes(com))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
