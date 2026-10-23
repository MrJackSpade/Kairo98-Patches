"""English for Cocktail Soft's Can Can Bunny (pc98tl/cocktail.py): strings.json in, a patched floppy out.

Strings:
* m (message): what the message box shows together (a record a line; \\n between the Japanese lines),
  any length: broken between words at 50 letters, the box scrolling for more lines; {N0}-{N6} an entry
  the player made (the name, the age, the job, the blood type, the personality, the hobby, the type
  liked), put where it belongs (the program puts it there; one a message, where the Japanese has it).
* c (command): a row of the command panel: max_cells letters (12 or 14).
* w (word): a choice of the player's entries, or the disk's own entries (the name...): up to 14 letters.
* p (page): a text of the opening or the ending (a profile, a line of the story, the staff): broken
  between words at its width (max_cells letters), its rows a page (more shown in turn); \\n a new line,
  {C1}-{C7} a colour (kept where they are wanted).

English is ASCII, drawn two letters a character.  A translated text's first two bytes become a mark of
its English, kept in a store on the disk's free tracks that the program loads at its start.
"""
import json
import os
import re
import unicodedata

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from . import cocktail as C
from .text import pseudo

PREFIX = {"msg": "m", "cmd": "c", "word": "w", "page": "p"}
NOTE = {"msg": "the message box: any length (broken between words at 50 letters, the box scrolls for "
               "more); \\n a new line; keep each {N0}-{N6} (an entry the player made: the name...) once",
        "cmd": "a row of the command panel: max_cells letters",
        "word": "a choice of the player's entries (a job, a blood type, a hobby...) or a default one: "
                "up to 14 letters",
        "page": "the opening's or the ending's text: broken between words at max_cells letters, more "
                "lines shown in turn; \\n a new line; {C1}-{C7} colours"}
SOURCES = ("D",) + tuple("K%d" % (k + 1) for k in range(len(C.TALKS)))


class Game:
    def __init__(self, raw):
        self.disk = C.Disk(raw)
        self.prog = C.Program(self.disk)
        self.files = self.prog.files()

    def image(self, src):
        """(bytes of a main-part source, its 8080 address)"""
        if src == "D":
            return bytes(self.prog.ds_image()), 0
        a, n = self.files[C.TALKS[int(src[1:]) - 1]]
        return bytes(self.disk.raw[a:a + n]), C.TALK_BASE

    def units(self, src):
        b, base = self.image(src)
        return b, C.units(C.box_records(b, base))

    def module(self):
        b = bytes(self.prog.module_image())
        return b, C.module_records(b)

    def entries(self):
        """{label: (disk offset, [16-byte slots])}: the player's entries in the saved games and in USER.COM
        (the defaults), each a block of 7 slots (Shift-JIS, then 0) and one of FFh."""
        user = self.files["USER.COM"][0]
        out = {}
        for label, at in (("S0", C.Disk.at(*C.SAVE)), ("S1", C.Disk.at(*C.SAVE) + 0x100),
                          ("U0", user), ("U1", user + 0x100)):
            slots = [bytes(self.disk.raw[at + 16 * k:at + 16 * k + 16]) for k in range(C.ENTRIES + 1)]
            if slots[-1][3:] == b"\xff" * 13 and all(not s.strip(b"\0") or C._text_end(s, 0) > 0
                                                       for s in slots[:-1]):
                out[label] = (at, slots[:-1])
        return out


def unit_kind(unit):
    r = unit[0]
    if r.mode is None:
        return "word"
    return "msg" if r.slot in (7, 8) else "cmd"


def unit_jp(b, unit):
    out = ""
    for i, r in enumerate(unit):
        t = C.show(b[r.text:r.end])
        if r.mode == 0xD:
            out += "{N%d}" % r.slot + t
        else:
            out += ("\n" if i else "") + t
    return out


def _centred(rec, b):
    lines = C.module_show(b[rec.text:rec.end]).split("\n")
    widest = max(len(re.sub(r"\{C\d\}", "", ln)) for ln in lines)
    return abs(rec.x - (C.MODULE_COLUMNS - widest) // 2) <= 1 and len(lines) == 1


def found(game):
    """[(ref, kind, Japanese, max cells)]."""
    out = []
    for src in SOURCES:
        b, us = game.units(src)
        for u in us:
            kind = unit_kind(u)
            room = {"msg": C.BOX_WIDTH, "cmd": C.MENU_CELLS, "word": C.NAME_CELLS}[kind]
            if kind == "cmd" and u[0].mode == 0xF:
                room -= 2           # (a command's row starts 2 cells in: the program's own)
            out.append(("%s:%04x" % (src, u[0].at), kind, unit_jp(b, u), room))
    b, recs = game.module()
    for r in recs:
        out.append(("M:%04x" % r.at, "page", C.module_show(b[r.text:r.end]), r.cells()))
    for label, (_at, slots) in game.entries().items():
        for k, slot in enumerate(slots):
            e = C._text_end(slot, 0)
            if e > 0 and C.JAPANESE.search(C.show(slot[:e])):
                out.append(("%s:%d" % (label, k), "word", C.show(slot[:e]), C.NAME_CELLS))
    return out


def run_extract(here, src):
    game = Game(open(src, "rb").read())
    merged, order = {}, []
    for ref, kind, jp, room in found(game):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
            continue
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": NOTE[kind]}
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
    t = re.sub(r"\{[^{}]*\}", "", t).replace("\n", "")
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


def _pseudo(e):
    text = pseudo(e["id"], _cols(e["jp"]))
    if e["kind"] in ("cmd", "word"):            # (a row of fixed room: filled to it)
        return text[:e["max_cells"]]
    tokens = re.findall(r"\{N\d\}", e["jp"])
    if tokens:
        head, _sp, rest = text.partition(" ")
        text = head + " " + " ".join(tokens) + " " + rest
    return text


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    raw = open(src, "rb").read()
    game = Game(raw)
    by_ref = {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            by_ref[r] = (e, text)
    translated = sum(1 for e in doc["strings"] if e["en"])
    warn, store, index = [], [], {}

    def idx(eng):
        if eng not in index:
            index[eng] = len(store)
            store.append(eng)
        return index[eng]

    prog, disk = game.prog, game.disk
    marks = []                  # (where: "P" program / "R" disk, place, the original record's bytes, new bytes)
    for src_name in SOURCES:
        b, us = game.units(src_name)
        place = prog.ds_at if src_name == "D" else game.files[C.TALKS[int(src_name[1:]) - 1]][0]
        where = "P" if src_name == "D" else "R"
        for u in us:
            e, text = by_ref.get("%s:%04x" % (src_name, u[0].at), (None, ""))
            if not text:
                continue
            kind = unit_kind(u)
            if kind == "msg":
                eng = C.box_english(u, text, e["id"], warn)
            else:
                eng = {u[0].at: C.line_english(text, e["max_cells"], e["id"], warn)}
            for r in u:
                marks.append((where, place + r.at, b[r.at:r.end + 1], r.text - r.at, C.mark(idx(eng[r.at]))))
    b, recs = game.module()
    for r in recs:
        e, text = by_ref.get("M:%04x" % r.at, (None, ""))
        if not text:
            continue
        rows = C.module_show(b[r.text:r.end]).count("\n") + 1
        eng, x, y = C.page_english(r, text, _centred(r, b), rows, e["id"], warn)
        head = bytes([x, y]) + b[r.at + 2:r.text]
        marks.append(("P", prog.module_ds_at + r.at, b[r.at:r.end + 2], 0, head + C.mark(idx(eng))))
    for label, (at, slots) in game.entries().items():
        for k, slot in enumerate(slots):
            e, text = by_ref.get("%s:%d" % (label, k), (None, ""))
            if text:
                eng = C.line_english(text, e["max_cells"], e["id"], warn)
                marks.append(("R", at + 16 * k, slot[:C._text_end(slot, 0) + 1], 0, C.mark(idx(eng))))
    if not store:
        open(dst, "wb").write(raw)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    out = bytearray(disk.raw)
    pd = prog.d
    copies = [game.files[n] for n in C.COPIES]
    for where, at, old, skip, new in marks:
        target = pd if where == "P" else out
        target[at + skip:at + skip + len(new)] = new
        # the PC-8801 files' copies of the program's texts
        if where == "P":
            for a, n in copies:
                k = bytes(disk.raw[a:a + n]).find(old)
                while k >= 0:
                    out[a + k + skip:a + k + skip + len(new)] = new
                    k = bytes(disk.raw[a:a + n]).find(old, k + 1)
    body = C.patch_program(prog, store)
    out[prog.at:prog.at + prog.size] = prog.encoded()
    at = C.Disk.at(C.STORE_TRACK, 1)
    if any(b != 0xE5 for b in disk.raw[at:at + len(body)]):
        raise SystemExit("the tracks from %d are not free" % C.STORE_TRACK)
    out[at:at + len(body)] = body
    with open(dst, "wb") as f:
        f.write(out)
    with open(os.path.join(os.path.dirname(os.path.abspath(dst)), "MTL_NOTE.TXT"), "w", encoding="ascii",
              newline="\r\n") as f:
        f.write(MTL_NOTE.format(title=cfg["title"]))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    print("patched %s (%s mode, %d/%d strings translated, %d English texts, store %d bytes)" % (
        dst, mode, translated, len(doc["strings"]), len(store), len(body)))
