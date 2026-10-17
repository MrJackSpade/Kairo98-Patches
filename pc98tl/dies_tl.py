"""English for FamilySoft's Dies Irae (pc98tl/dies.py): strings.json in, a patched disk out.

Strings:
* m (message): a script's message, any length: broken between words at 48 letters (the window's 24
  characters, two letters each), the program paging after three lines; \\n a new line; {Xn} a code of
  the script's (a colour, a face, a wait), kept where it stands.  The same Japanese is one string.
* c (choice): a line of a menu, max_cells characters (two letters each).
* e (program): the programs' DOS messages, written in place: max_cells letters.

A build with English writes the scripts again with their English (two letters a character), puts the
half-width helper into DIES01.EXE, and writes the programs' messages in place.
"""
import json
import os
import re
import unicodedata

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import dies as D
from .text import pseudo

PREFIX = {"msg": "m", "choice": "c", "prog": "e"}
NOTE = {"msg": "a message: any length (broken between words at the window's edge, paged by the program); "
               "\\n a new line; keep each {Xn} code",
        "choice": "a menu choice: one line, max_cells characters (two letters each); keep each {Xn} code",
        "prog": "a program's message (DOS), in place: max_cells letters"}
PROGRAMS = ("DIES01.EXE", "D_OP98.EXE", "DIES98.COM", "HDSTART.EXE")


def _path(cfg, name):
    return cfg["dir"] + "/" + name


def scripts(vol, cfg):
    """[(path, text)] of the CEN scripts under the game's folder."""
    out = []
    for path, e in sorted(vol.walk()):
        if e["is_dir"] or not path.upper().startswith(cfg["dir"].upper() + "/"):
            continue
        if not path.upper().endswith(".CEN"):
            continue
        data = vol.read(path)
        if data.startswith(D.HEAD):
            out.append((path, D.decode(data)))
    return out


def found(vol, cfg):
    """[(ref, kind, Japanese bytes, max cells or None)]."""
    out = []
    for path, t in scripts(vol, cfg):
        name = path[len(cfg["dir"]) + 1:]
        for s, e, kind in D.units(t):
            out.append(("%s:%05x" % (name, s), kind, t[s:e], D.CHOICE_ROOM if kind == "choice" else None))
    for prog in PROGRAMS:
        if not vol.find(_path(cfg, prog)):
            continue
        data = vol.read(_path(cfg, prog))
        for s, e in D.dos_strings(data):
            out.append(("%s:%05x" % (prog, s), "prog", data[s:e], e - s))
    return out


def show(kind, b):
    if kind == "prog":
        return b.decode("cp932", "replace")
    return D.show(b)


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for ref, kind, jp_b, room in found(vol, cfg):
        jp = show(kind, jp_b)
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room or 9999)
            continue
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room or 9999,
                       "note": NOTE[kind]}
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
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


def _pseudo(e):
    out = []
    for p in re.split(r"(\{[A-Z]{1,2}-?[0-9,]*\}|\n)", e["jp"]):
        if not p:
            continue
        if p == "\n" or p.startswith("{"):
            out.append(p)
        else:
            out.append(pseudo(e["id"], _cols(p)))
    return "".join(out)


def _ascii(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "$": "S"}
    s = "".join(subst.get(c, c) for c in text.replace("\n", " "))
    return "".join(c if 0x20 <= ord(c) < 0x7F else "?" for c in s).encode("ascii")


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    by_ref = {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            by_ref[r] = (e, text)
    warn, new, progs = [], {}, {}
    texts = dict(scripts(vol, cfg))
    for ref, kind, jp_b, room in found(vol, cfg):
        e, text = by_ref.get(ref, (None, ""))
        if not text:
            continue
        name, start = ref.rsplit(":", 1)
        start = int(start, 16)
        if kind == "prog":
            b = _ascii(text)
            if len(b) > room:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(b), room))
                b = b[:room]
            progs.setdefault(name, []).append((start, b.ljust(room, b" ")))
            continue
        known = D.codes(jp_b)
        try:
            if kind == "choice":
                b, cut = D.choice(text, known, room)
                if cut:
                    warn.append("%s: longer than its room, cut" % e["id"])
            else:
                b = D.message(text, known)
        except ValueError as err:
            raise SystemExit("%s: %s" % (e["id"], err))
        new.setdefault(_path(cfg, name), {})[start] = (start + len(jp_b), b)
    out = {p: D.rebuild(texts[p], u) for p, u in new.items()}
    common = _path(cfg, "000.CEN")
    shared = len(out.get(common, texts.get(common, b"")))
    for path, t in texts.items():
        if path != common and len(out.get(path, t)) + shared > D.SCRIPT_LIMIT:
            raise SystemExit("%s: %d bytes with 000.CEN's %d, the script buffer holds %d; shorten its English"
                             % (path, len(out.get(path, t)), shared, D.SCRIPT_LIMIT))
    for path, t in out.items():
        vol.write(path, D.encode(t))
    for name, places in progs.items():
        p = _path(cfg, name)
        data = bytearray(vol.read(p))
        for s, b in places:
            data[s:s + len(b)] = b
        vol.write(p, bytes(data))
    if new or progs:
        p = _path(cfg, cfg["engine"])
        vol.write(p, D.patch_program(vol.read(p)))
        vol.create(_path(cfg, "MTL_NOTE.TXT"),
                   MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
