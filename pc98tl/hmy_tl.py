"""English for Himeya Soft's Bacta (pc98tl/hmy.py): strings.json in, patched floppies out.

Strings:
* m (message): a message of the window (3 lines of 68 letters), any length: broken between words, more
  than 3 lines shown a window at a time (the engine waits for a key); \\n a new line.  The speaker's name
  (【...】 at its start) is a string of its own.
* n (name): a speaker's name, put before each of their messages: up to 16 letters.
* c (choice): a menu's choice: up to 12 letters (the menu's boxes).

English is ASCII (the engine draws it half-width itself).  A build writes the scripts again with their
texts at any length (every address moved) and packs the floppies' files again.
"""
import json
import os
import re

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from . import hmy as H
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "item": "c"}
NOTE = {"msg": "a message: any length (broken between words at 68 letters, 3 lines a window, more windows "
               "for the rest); \\n a new line; the speaker's name is a string of its own",
        "name": "a speaker's name, put before their messages: up to 16 letters",
        "item": "a menu's choice: up to 12 letters"}
NAME_ROOM = 16


def _images(cfg, src):
    base = os.path.dirname(src)
    return [src] + [os.path.join(base, n) for _t, n in sorted(cfg.get("floppies", {}).items())]


class Game:
    def __init__(self, paths):
        self.paths = paths
        self.disks = [H.Mako(H.D88(open(p, "rb").read())) for p in paths]
        self.engine = H.engine(self.disks[0].read("HMY.BIN"))

    def scripts(self):
        """[(disk letter, name, Script)]."""
        out = []
        for k, m in enumerate(self.disks):
            for n in m.names():
                if n.endswith(".COM") and n != "AUTOEXEC.COM":
                    out.append(("AB"[k], n, H.Script(m.read(n))))
        return out


def split(jp):
    m = H.SPEAKER.match(jp)
    return (m.group(1), jp[m.end():]) if m else ("", jp)


def found(game):
    """[(ref, kind, Japanese, max cells)]."""
    width = game.engine["msg"][0]
    out = []
    for disk, name, sc in game.scripts():
        for kind, s, e in sc.messages() + sc.items():
            ref = "%s:%s:%04x" % (disk, name, s)
            if kind == "item":
                out.append((ref, "item", H.show(sc.d[s:e], 9999), game.engine["item"]))
                continue
            jp = H.show(sc.d[s:e], width)
            who, rest = split(jp)
            if who:
                out.append((ref, "name", who, NAME_ROOM))
            out.append((ref, "msg", rest, width))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    game = Game(_images(cfg, src))
    merged, order = {}, []
    for ref, kind, jp, room in found(game):
        if not jp.strip("　\n"):
            continue
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
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
    return sum(H._cells(c) for c in t.replace("\n", ""))


def run_patch(here, src, dst, mode="en"):
    from .aypio import ascii_text
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    paths = _images(cfg, src)
    game = Game(paths)
    width = game.engine["msg"][0]
    by_ref = {}
    for e in doc["strings"]:
        text = e["en"]
        if mode == "pseudo":
            text = pseudo(e["id"], _cols(e["jp"]))
            if e["kind"] != "msg":
                text = text[:e["max_cells"]]
        for r in e["refs"]:
            by_ref[(r, e["kind"])] = (e, text)
    warn, changed = [], [dict() for _ in game.disks]
    for disk, name, sc in game.scripts():
        new = {}
        for kind, s, e in sc.messages() + sc.items():
            ref = "%s:%s:%04x" % (disk, name, s)
            if kind == "item":
                ent, text = by_ref.get((ref, "item"), (None, ""))
                if text:
                    b = ascii_text(text).replace("\n", " ").encode("ascii")
                    if len(b) > ent["max_cells"]:
                        warn.append("%s: %d letters, the choice's box holds %d" % (ent["id"], len(b), ent["max_cells"]))
                    new[s] = b
                continue
            ent, text = by_ref.get((ref, "msg"), (None, ""))
            nent, name_en = by_ref.get((ref, "name"), (None, ""))
            if not text and not name_en:
                continue
            who, rest = split(H.show(sc.d[s:e], width))
            if name_en:
                head = ascii_text(name_en).replace("\n", " ").encode("ascii")
                if len(head) > NAME_ROOM:
                    warn.append("%s: %d letters, room for %d" % (nent["id"], len(head), NAME_ROOM))
            else:
                head = who.encode("cp932")
            if text:
                body = H.layout(text, width, first=len(head) + (1 if name_en else 0))
                head = head + (b" " if name_en else b"")
            else:
                j = sc.d[s:e]
                body = j[len(who.encode("cp932")):]
            new[s] = head + body
        if new:
            try:
                changed["AB".index(disk)][name] = H.rebuild(sc, new)
            except H.ScriptError as err:
                raise SystemExit("%s: %s; shorten its English" % (name, err))
    if not any(changed):
        for p, out in zip(paths, _outputs(dst, paths)):
            open(out, "wb").write(open(p, "rb").read())
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    for m, files in zip(game.disks, changed):
        if "MAKOBIOS.BIN" in m.names():
            files["MAKOBIOS.BIN"] = H.patch_bios(m.read("MAKOBIOS.BIN"))
        if files:
            try:
                m.write_all(files)
            except ValueError as err:
                raise SystemExit(str(err))
    for m, out in zip(game.disks, _outputs(dst, paths)):
        with open(out, "wb") as f:
            f.write(m.d.raw)
    with open(os.path.join(os.path.dirname(os.path.abspath(dst)), "MTL_NOTE.TXT"), "w", encoding="ascii",
              newline="\r\n") as f:
        f.write(MTL_NOTE.format(title=cfg["title"]))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))


def _outputs(dst, paths):
    stem = os.path.splitext(dst)[0]
    return [dst] + ["%s - %s" % (stem, os.path.basename(p)) for p in paths[1:]]
