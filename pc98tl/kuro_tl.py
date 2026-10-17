"""English for Kuro no Danshou (pc98tl/kuro.py): strings.json in, a patched image out.

Strings:
* m (message): a scene's text, inside !s(...) or a label's reply.  Any length: the English is broken
  between words at 66 letters (GAME.EXE breaks at 67 at any letter) and the window pages itself after 4
  rows.  {r} (a click and a new page) and a new line restart the line.  {R1}.. is a ruby reading (shown
  over the word after it; keep it before that word's English or leave it out), {C1}.. an effect (kept;
  a missing one is put at the end).
* u (label): a menu's object or verb.  GAME.EXE copies it into a 21-byte slot and matches the menus by
  string: 20 bytes, longer is cut and reported.  The same Japanese is one string, so a label and the
  menu it is matched with stay the same.
* c (choice): an option of a choice menu, one line.
* n (caption): a caption drawn at its x and y (a name card, a notice): broken between words at the
  screen's width from its column, {n} a new line.
* e (program): GAME.EXE's own strings (the opening, the screen-mode menu, the disk prompts, the error
  messages): any length, broken between words at 64 letters.

game.json: game_dir, program; title_scene (default 0, -1 none); program_in_place (the program's strings
written in place, max_cells bytes, instead of through the helper: Es no Houteishiki's ES98.EXE copies its
strings and reaches them through tables).

The title's scene (the first, unless title_scene says otherwise) is left as it is: its menu is the title picture's buttons (English already),
the menu's own text never shown and its items found by where that text would lie.

ASCII is drawn half-width.  The script's own signs ( ) [ ] ! are written full-width, " as ', _ and ~ as
-, | and backslash as / (GAME.EXE reads them as codes or draws them as other signs).
"""
import json
import os
import re
import struct

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import kuro as K
from .text import pseudo

PREFIX = {"msg": "m", "label": "u", "choice": "c", "caption": "n", "program": "e"}
KIND = {"m": "msg", "u": "label", "c": "choice", "n": "caption"}
WIDTH = 66
LABEL = 20
EXE_WIDTH = 64
TITLE = 0           # the title's scene: its menu's items lie under the title picture's buttons, matched by place
FULL = {"(": b"\x81\x69", ")": b"\x81\x6a", "[": b"\x81\x6d", "]": b"\x81\x6e", "!": b"\x81\x49"}
SUBST = {"’": "'", "‘": "'", "“": "'", "”": "'", "—": "-", "–": "-",
         "…": "...", '"': "'", "_": "-", "~": "-", "|": "/", "\\": "/"}
NOTE = {"msg": "a message: any length, broken between words at 66 letters, paged by the game; {r} a click "
               "and a new page, \\n a new line; {R1}.. a ruby reading for the word after it (keep it before "
               "that word or leave it out), {C1}.. an effect (keep it)",
        "label": "a menu's object or verb, matched by string with the menus: up to 20 letters (max_cells)",
        "choice": "an option of a choice menu: one line",
        "caption": "a caption drawn at its place: broken between words at max_cells letters a line, {n} a new "
                   "line",
        "program": "a string of GAME.EXE's: broken between words at 64 letters, \\n a new line; {w} {s} as given",
        "program_in_place": "a string of the program's, in place: max_cells letters, \\n a new line; {w} {s} as "
                            "given"}


def _game(cfg, src):
    img = DiskImage(src)
    return img, img.volumes[0], cfg["game_dir"]


def _scene_files(vol, gd):
    """{name: decoded} of the scene files SCNDAT.TBL names."""
    tbl = K.xor(vol.read(gd + "/SCNDAT.TBL"))
    return {n: K.xor(vol.read("%s/%s" % (gd, n))) for n in sorted(set(e[0] for e in K.table(tbl)))}


def found(vol, gd, title=TITLE):
    """[(ref, kind, jp, room, rubies)] of the scenes' units, in order."""
    files = _scene_files(vol, gd)
    tbl = K.xor(vol.read(gd + "/SCNDAT.TBL"))
    out = []
    for i, name, block in K.scenes(files, tbl):
        if i == title:
            continue
        _h, offsets, s = K.parse(block)
        for kind, a, e, parts in K.units(s, offsets, K.keys(_h, offsets)):
            room = None
            if kind == "n":
                # (a caption: !p(04 00 x,y,text: the room from its column)
                head = s[:a]
                k = head.rfind(b"!p(\x04\x00")
                x = int(head[k + 5:].split(b",")[0] or 0)
                room = max(10, 79 - x)
            rubies = [K.ruby_text(s, p) for p in parts if p[0] == "ruby"]
            out.append(("%s:%d:%04x" % (name, i, a), KIND[kind], K.show(s, parts), room, rubies))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    _img, vol, gd = _game(cfg, src)
    merged, order = {}, []

    def add(kind, jp, ref, room, note):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
        order.append(key)
    exe = vol.read(gd + "/" + cfg["program"])
    for off, t in K.exe_strings(exe):
        room, note = EXE_WIDTH * 8, NOTE["program"]
        if cfg.get("program_in_place"):
            room, note = len(t), NOTE["program_in_place"]
        add("program", K.show_text(t), "%s:%04x" % (cfg["program"], off), room, note)
    for ref, kind, jp, room, rubies in found(vol, gd, cfg.get("title_scene", TITLE)):
        note = NOTE[kind]
        if rubies:
            note += "; readings: " + ", ".join("{R%d} %s" % (k + 1, r) for k, r in enumerate(rubies))
        room = {"msg": WIDTH * 4, "label": LABEL, "choice": WIDTH}.get(kind, room)
        add(kind, jp, ref, room, note)
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


# ---- English ---------------------------------------------------------------------------------------
def _char(ch, choice=False):
    ch = SUBST.get(ch, ch)
    if ch in FULL:
        return FULL[ch]
    if choice and ch == ",":
        return b"\x81\x43"
    out = b""
    for c in ch:
        out += bytes([ord(c)]) if 0x20 <= ord(c) < 0x7F else b"?"
    return out


def _cells(b):
    return len(b)


TOKEN = re.compile(r"\{(r|n|w|s|R\d+|C\d+)\}|\n")


def _pieces(text):
    """[(kind, value)]: word (a run without spaces), space, break (\\n, {r}, {n}), code ({w} {s}), ruby
    {Rk}, effect {Ck}."""
    out = []
    pos = 0
    for m in TOKEN.finditer(text):
        out += _words(text[pos:m.start()])
        t = m.group(0)
        if t == "\n":
            out.append(("break", "\n"))
        elif t in ("{r}", "{n}"):
            out.append(("break", t))
        elif t in ("{w}", "{s}"):
            out.append(("code", t))
        elif t.startswith("{R"):
            out.append(("ruby", int(t[2:-1])))
        else:
            out.append(("effect", int(t[2:-1])))
        pos = m.end()
    out += _words(text[pos:])
    return out


def _words(t):
    out = []
    for k, w in enumerate(t.split(" ")):
        if k:
            out.append(("space", " "))
        if w:
            out.append(("word", w))
    return out


def encode(text, width, newline, parts, s, choice=False):
    """The bytes for a unit's English: words broken at `width` letters (newline the bytes a break puts
    in), codes, ruby and effects from the unit's own parts."""
    rubies = [s[a:e] for k, a, e in parts if k == "ruby"]
    effects = [s[a:e] for k, a, e in parts if k == "effect"]
    used = set()
    out = bytearray()
    col = 0
    pending_space = False
    for kind, v in _pieces(text):
        if kind == "word":
            b = b"".join(_char(c, choice) for c in v)
            if width and col and col + (1 if pending_space else 0) + _cells(b) > width:
                out += newline
                col = 0
                pending_space = False
            if pending_space:
                out += b" "
                col += 1
            out += b
            col += _cells(b)
            pending_space = False
        elif kind == "space":
            pending_space = True
        elif kind == "break":
            if pending_space:
                pending_space = False
            out += {"\n": newline, "{r}": b"_r", "{n}": b"_n"}[v]
            col = 0
        elif kind == "code":
            out += {"{w}": b"_w", "{s}": b"_s"}[v]
        elif kind == "ruby":
            if 1 <= v <= len(rubies):
                out += rubies[v - 1]
        elif kind == "effect":
            if 1 <= v <= len(effects):
                out += effects[v - 1]
                used.add(v)
    if pending_space:
        out += b" "
    for k, eff in enumerate(effects, 1):
        if k not in used:
            out += eff
    return bytes(out)


def _pseudo(e):
    if e["kind"] in ("msg", "program", "caption"):
        jp = TOKEN.sub("", e["jp"])
        toks = "".join(m.group(0) for m in TOKEN.finditer(e["jp"]) if m.group(0) not in ("\n",))
        return pseudo(e["id"], 2 * len(jp)) + toks
    if e["kind"] == "label":
        return pseudo(e["id"], 2 * len(e["jp"]), 1.0)[:LABEL]
    return pseudo(e["id"], 2 * len(e["jp"]))


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img, vol, gd = _game(cfg, src)
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    # the scenes
    files = _scene_files(vol, gd)
    tbl = K.xor(vol.read(gd + "/SCNDAT.TBL"))
    blocks, changed = [], False
    for i, name, block in K.scenes(files, tbl):
        if i == cfg.get("title_scene", TITLE):
            blocks.append(block)
            continue
        _h, offsets, s = K.parse(block)
        rep = {}
        for kind, a, e, parts in K.units(s, offsets, K.keys(_h, offsets)):
            ref = "%s:%d:%04x" % (name, i, a)
            en = by_ref.get(ref)
            if en is None:
                continue
            ent = ids[ref]
            if kind == "m":
                b = encode(en, WIDTH, b"\n", parts, s)
            elif kind == "u":
                b = encode(" ".join(en.split("\n")), 0, b"", parts, s)
                if len(b) > LABEL:
                    warn.append("%s: %d letters, a label holds %d" % (ent["id"], len(b), LABEL))
                    b = b[:LABEL]
            elif kind == "c":
                b = encode(" ".join(en.split("\n")), 0, b"", parts, s, choice=True)
                if len(b) > WIDTH:
                    warn.append("%s: %d letters, a line holds %d" % (ent["id"], len(b), WIDTH))
            else:
                b = encode(en, ent["max_cells"], b"_n", parts, s)
            if not b:
                b = b" "
            rep[a] = b
        if rep:
            try:
                nb = K.build(block, rep)
            except ValueError as ex:
                raise SystemExit("%s scene %d: the English makes the block %s, more than its 16-bit places "
                                 "reach (%d); shorten it" % (name, i, ex, K.LIMIT))
            changed = changed or nb != block
            blocks.append(nb)
        else:
            blocks.append(block)
    if changed:
        new_files, new_tbl = K.rebuild(files, tbl, blocks)
        for n, data in new_files.items():
            if data != files[n]:
                vol.write("%s/%s" % (gd, n), K.xor(data))
        vol.write(gd + "/SCNDAT.TBL", K.xor(new_tbl))
    # the program
    prog = gd + "/" + cfg["program"]
    exe = vol.read(prog)
    english = {}
    for off, t in K.exe_strings(exe):
        en = by_ref.get("%s:%04x" % (cfg["program"], off))
        if en is not None:
            english[off] = encode(en, EXE_WIDTH, b"\n", [], b"")
    if english and cfg.get("program_in_place"):
        # (Es no Houteishiki's ES98.EXE: its strings copied and reached through tables, written in place)
        hdr = struct.unpack_from("<H", exe, 8)[0] * 16
        exe = bytearray(exe)
        base = hdr + K.dgroup(bytes(exe)) * 16
        room = dict((off, len(t)) for off, t in K.exe_strings(bytes(exe)))
        for off, en in english.items():
            if len(en) > room[off]:
                warn.append("%s: %d bytes, room for %d" % (ids["%s:%04x" % (cfg["program"], off)]["id"],
                                                           len(en), room[off]))
                en = en[:room[off]]
            exe[base + off:base + off + room[off]] = en.ljust(room[off], b"\0")
        vol.write(prog, bytes(exe))
    elif english:
        vol.write(prog, K.patch_program(exe, english))
    vol.create(gd + "/MTL_NOTE.TXT", MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
