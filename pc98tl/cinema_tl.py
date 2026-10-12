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
full-width in Shift-JIS when it has it, else `?`.  A script with its English must end before
ESC.BIN's place in the buffer (7800h; ESC.BIN itself before 8000h): a longer build is refused and
names the script.  AUTOEXEC.BIN runs machine code from its own bytes, so its code stays where it is:
a text that fits is written in its place, a longer one after the script's end.
"""
import json
import os
import re

from . import cinema
from .alice_sys2_tl import sha256
from .text import pseudo, sjis_cols

PREFIX = {"msg": "m", "name": "n", "item": "i", "engine": "e"}
FIXED_CODE = ("AUTOEXEC.BIN",)
ENGINE_RE = re.compile(rb"((?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+\.?)\r\n\$")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def is_script(name):
    return name.startswith("TSM_") or name in ("AUTOEXEC.BIN", "STAFF.BIN", "ESC.BIN")


def base_of(name):
    return cinema.ESC_AT if name == "ESC.BIN" else 0


def limit_of(name):
    return cinema.BUFFER_END if name == "ESC.BIN" else cinema.ESC_AT


def _cells(text):
    return sjis_cols(text.encode("cp932", "replace"))


def _is_name(visible, suffix):
    return visible.startswith("【") and visible.endswith("】") and b"\\f" not in suffix


def script_texts(name, d):
    """(Script, [(ref, kind, addr, start, end, prefix, visible, suffix, menu)]) in address order."""
    sc = cinema.Script(d, base_of(name))
    out = []
    for a, kind, (s, e) in sorted(cinema.texts(sc), key=lambda t: t[2][0]):
        parts = cinema.split_text(d[s - sc.base:e - sc.base])
        if parts is None:
            raise ValueError("%s:%04x: a command inside the text" % (name, a))
        prefix, visible, suffix = parts
        if kind == "msg" and _is_name(visible, suffix):
            kind = "name"
        out.append(("%s:%04x" % (name, a), kind, a, s, e, prefix, visible, suffix, sc.items.get(a)))
    return sc, out


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
    _flags, mems = cinema.members(vol.read(cfg["archive"]))
    cols = cfg["window"][0]
    for m in mems:
        if not is_script(m[0]):
            continue
        sc, rows = script_texts(m[0], cinema.data(m))
        menus = {}
        for ref, kind, a, s, e, prefix, visible, suffix, menu in rows:
            if kind == "item":
                menus[menu] = max(menus.get(menu, 0), _cells(visible))
        after_name = False
        for ref, kind, a, s, e, prefix, visible, suffix, menu in rows:
            if not visible.strip("　 \n"):
                after_name = False if kind != "item" else after_name
                continue
            if kind == "item":
                add("item", visible, ref, menus[menu], "a menu's item: one line in its box (the menu's widest "
                    "Japanese item)")
                continue
            if kind == "name":
                add("name", visible, ref, _cells(visible), "a speaker's name: the message after it goes on "
                    "along its row")
                after_name = True
                continue
            add("msg", visible, ref, cols, "after the speaker's name, on its row" if after_name else None)
            after_name = False
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


def build_script(name, d, by_ref, ids, rooms, cfg, warn, ratio=1.0):
    """The script with its English (None when nothing changed)."""
    sc, rows = script_texts(name, d)
    cur = Cursor(*cfg["window"])
    new_text, pages = {}, {}
    for ref, kind, a, s, e, prefix, visible, suffix, menu in rows:
        if kind == "item":
            if ref in by_ref:
                t = by_ref[ref]
                if _cells(t) > rooms[ref]:
                    warn.append("%s: %d letters, past its menu's room (%d)" % (ids[ref], _cells(t), rooms[ref]))
                new_text[s] = prefix + cinema.encode(t) + suffix
            continue
        if ref not in by_ref or not visible.strip("　 \n"):
            if visible.strip("　 \n"):
                cur.jp(visible)
            cur.suffix(suffix)
            continue
        t = by_ref[ref]
        if ratio < 1.0:
            t = t[:max(4, int(len(t) * ratio))]
        if kind == "msg" and visible.startswith("　") and not t.startswith(" "):
            t = " " + t
        ps = cur.english(t)
        if b"\\n" in suffix and b"\\f" not in suffix and cur.row + 1 >= cur.rows:
            # (the script's new line after it would go past the window's bottom: the page ends here,
            # after a key the next message starts a new one)
            ps[-1] += b"\\f"
            ps.append(b"")
            suffix = suffix.replace(b"\\n", b"", 1)
            cur.clear = True
        cur.suffix(suffix)
        ps[0] = prefix + ps[0]
        ps[-1] = ps[-1] + suffix
        if len(ps) == 1:
            new_text[s] = ps[0]
        else:
            pages[a] = ps
    if not new_text and not pages:
        return None
    if name in FIXED_CODE:
        return cinema.redirect(sc, new_text, pages, limit_of(name))
    return cinema.rebuild(sc, new_text, pages, limit_of(name))


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
    arc = vol.read(cfg["archive"])
    flags, mems = cinema.members(arc)
    for m in mems:
        if not is_script(m[0]):
            continue
        d = cinema.data(m)
        try:
            new = build_script(m[0], d, by_ref, ids, rooms, cfg, warn)
        except OverflowError as ex:
            if mode != "pseudo":
                raise SystemExit("%s: %d bytes with its English, it may take %d; shorten these strings: %s" % (
                    m[0], ex.args[0] - base_of(m[0]), limit_of(m[0]) - base_of(m[0]),
                    ", ".join(sorted({ids[r] for r in by_ref if r.startswith(m[0] + ":")}))))
            # (the --pseudo filler: every message cut in proportion until the script fits)
            ratio, new = 1.0, None
            while new is None:
                ratio *= 0.9
                try:
                    new = build_script(m[0], d, by_ref, ids, rooms, cfg, [], ratio)
                except OverflowError:
                    continue
            warn.append("%s: the filler was cut to %d%% to fit the script's room" % (m[0], int(ratio * 100)))
        if new is not None and new != d:
            m[1], m[2], m[3] = 0, new, len(new)
            done += 1
    if done:
        vol.write(cfg["archive"], cinema.archive(flags, mems))
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
