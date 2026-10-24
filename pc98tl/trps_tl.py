"""English for Custom's Teen (pc98tl/trps.py): strings.json in, a patched disk out.

Strings:
* m (message): a line of a message file (DATA_00.MSG, DATA_nn.1MS, DATA_nn.2MS), any length: broken
  between words at the window's 64 letters, 4 rows a window (the program waits for a key and goes on in
  a cleared window); \\n a new row.  {Gxxxx} a character of the game's own (TEEN.GAI: hearts, dots..):
  2 letters wide.
* e (program): a string of a program (MENU.EXE, TEEN_S1.EXE, TEEN_S2.EXE, INIT.EXE, CUSTOM.EXE,
  INSTALL.EXE): menus, names, choices and messages, in place: max_cells letters; \\n a new line, %d, %s..
  where a value goes.
* h (help): a line of HELP.TXT (the operation help, shown on the text screen): one line; {ESC} the
  escape codes (colours, places) kept where they are.

English is ASCII.  A build writes the message files again (each line any length), the programs back
unpacked with their strings in place and the one-byte helper in the three that show messages, and
HELP.TXT again.
"""
import json
import os
import re

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import pklite
from . import trps as T
from .kuro import _exe
from .text import pseudo

PREFIX = {"msg": "m", "prog": "e", "help": "h"}
NOTE = {"msg": "a message: any length (broken between words at 64 letters, 4 rows a window, more windows "
               "after a key); \\n a new row; keep each {Gxxxx} (the game's own characters) where it belongs",
        "prog": "a program's string, in place: max_cells letters; \\n a new line; keep each %d, %s..",
        "help": "a line of the operation help: one line; keep each {ESC} (a colour or a place) where it is"}
PROGRAMS = ("MENU.EXE", "TEEN_S1.EXE", "TEEN_S2.EXE", "INIT.EXE", "CUSTOM.EXE", "INSTALL.EXE")
MESSAGES = re.compile(r"DATA_\d+\.(?:MSG|\dMS)$", re.I)
HELP = "HELP.TXT"
JAPANESE = re.compile(r"[ぁ-ヶ一-龥]")
FORMAT = re.compile(r"%[-+ 0#]*\d*(?:\.\d+)?l?[a-zA-Z]")
ESC = re.compile(r"\x1b\[[0-9;>?]*[A-Za-z]")


def _path(cfg, name):
    return cfg["dir"] + "/" + name


def _has(vol, path):
    try:
        return bool(vol.find(path))
    except FileNotFoundError:
        return False


def message_files(vol, cfg):
    d = vol.find(cfg["dir"])
    return sorted(e["name"] for e in vol.listdir(d["cluster"]) if MESSAGES.match(e["name"]))


def program(vol, cfg, name):
    exe = vol.read(_path(cfg, name))
    return pklite.unpack(exe) if pklite.is_packed(exe) else exe


def help_show(line):
    return ESC.sub("{ESC}", line.decode("cp932", "replace"))


def found(vol, cfg):
    """[(ref, kind, Japanese, max cells or None)]."""
    out = []
    for name in message_files(vol, cfg):
        for k, ln in enumerate(T.lines(vol.read(_path(cfg, name)))):
            t = T.show(ln)
            if JAPANESE.search(t):
                out.append(("%s:%d" % (name, k), "msg", t, None))
    for name in PROGRAMS:
        if not _has(vol, _path(cfg, name)):
            continue
        _h, _r, img, fixups = _exe(program(vol, cfg, name))
        for a, b in T.program_strings(bytes(img), fixups):
            out.append(("%s:%05x" % (name, a), "prog", bytes(img[a:b]).decode("cp932"), b - a))
    if _has(vol, _path(cfg, HELP)):
        for k, ln in enumerate(vol.read(_path(cfg, HELP)).split(b"\r\n")):
            t = help_show(ln)
            if JAPANESE.search(t):
                out.append(("%s:%d" % (HELP, k), "help", t, None))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for ref, kind, jp, room in found(vol, cfg):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            if room is not None:
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
    t = re.sub(r"\{[^{}]*\}", "", t)
    return sum(2 if ord(c) > 0x7F else 1 for c in t)


def _text(e, mode):
    if mode != "pseudo":
        return e["en"]
    t = pseudo(e["id"], _cols(e["jp"]))
    if e["kind"] == "prog" and len(t) > e["max_cells"]:
        # (a short string's filler its id's number, so that a menu's choices stay told apart)
        n = str(int(e["id"][1:]))
        t = (e["id"][0] + n if len(n) < e["max_cells"] else n[-e["max_cells"]:]) + " " + t
    if e["kind"] == "prog":
        t = " ".join([t] + FORMAT.findall(e["jp"]))[:e["max_cells"]] if FORMAT.search(e["jp"]) else t
    if e["kind"] == "help":
        t = "{ESC}" * e["jp"].count("{ESC}") + t
    return t


def one_byte(jp):
    """A string the program shows through a path that takes one-byte characters (it has ASCII letters or
    marks, or new lines: the console's messages): its English is written as it is; the others (drawn two
    bytes a character) as pairs of letters."""
    return bool(re.search(r"[!-~\n]", jp))


def _ascii(text):
    from .aypio import ascii_text
    return ascii_text(text).encode("ascii")


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    by_ref = {}
    for e in doc["strings"]:
        text = _text(e, mode)
        for r in e["refs"]:
            by_ref[r] = (e, text)
    if not any(t for _e, t in by_ref.values()):
        img.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    warn = []
    width, _rows = T.window(vol.read(_path(cfg, "TEEN.INI")))
    for name in message_files(vol, cfg):
        p = _path(cfg, name)
        ls = T.lines(vol.read(p))
        changed = False
        for k in range(len(ls)):
            e, text = by_ref.get("%s:%d" % (name, k), (None, ""))
            if text:
                ls[k] = T.layout(text, width)
                changed = True
        if changed:
            vol.write(p, T.join(ls))
    for name in PROGRAMS:
        p = _path(cfg, name)
        if not _has(vol, p):
            continue
        exe = program(vol, cfg, name)
        _h, _r, image, fixups = _exe(exe)
        places, paired = [], []
        draws = T.has_routines(exe)
        for a, b in T.program_strings(bytes(image), fixups):
            e, text = by_ref.get("%s:%05x" % (name, a), (None, ""))
            if not text:
                continue
            if FORMAT.findall(text) != FORMAT.findall(e["jp"]):
                warn.append("%s: its %%d, %%s.. differ from the Japanese's" % e["id"])
            t = _ascii(text)
            if len(t) > b - a:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(t), b - a))
                t = t[:b - a]
            if draws and e["jp"].startswith("@") and not one_byte(e["jp"][1:]):
                # (a menu's choice marked by "@": the mark kept, the text after it in pairs)
                paired.append((a + 1, b - a - 1, t.decode("ascii").lstrip("@")[:b - a - 1]))
            elif draws and not one_byte(e["jp"]):
                paired.append((a, b - a, t.decode("ascii")))
            else:
                places.append((a, t.ljust(b - a)))
        # (a choice's label: its English also in the choices' conditions that name it, written the same)
        labels = {}
        for a, b in T.program_strings(bytes(image), fixups):
            e, text = by_ref.get("%s:%05x" % (name, a), (None, ""))
            if text and draws and not one_byte(e["jp"]):
                labels[e["jp"]] = (b - a, _ascii(text)[:b - a].decode("ascii"))
        for a, b, jp in T.conditions(bytes(image)):
            if jp in labels and labels[jp][0] == b - a:
                paired.append((a, b - a, labels[jp][1]))
        if places or paired or draws:
            vol.write(p, T.patch_program(exe, places, paired, name))
    hp = _path(cfg, HELP)
    if _has(vol, hp):
        ls = vol.read(hp).split(b"\r\n")
        changed = False
        for k, ln in enumerate(ls):
            e, text = by_ref.get("%s:%d" % (HELP, k), (None, ""))
            if not text:
                continue
            if text.count("{ESC}") != e["jp"].count("{ESC}"):
                warn.append("%s: its {ESC} differ from the Japanese's" % e["id"])
            codes = ESC.findall(ln.decode("cp932", "replace"))
            parts = text.split("{ESC}")
            b = _ascii(parts[0])
            for k2, part in enumerate(parts[1:]):
                b += (codes[k2].encode("ascii") if k2 < len(codes) else b"") + _ascii(part)
            ls[k] = b
            changed = True
        if changed:
            vol.write(hp, b"\r\n".join(ls))
    vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
