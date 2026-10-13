"""English for Ace of Spades (pc98tl/ace.py): strings.json in, a patched image out.

Strings:
* m (message): a paragraph of a *.S script: a line starting with a full-width space (or a script's
  first line) and the lines going on from it.  The English is broken between words at the line's
  36 cells (72 half-width letters); the script is written again with as many lines as it needs.
* n (name): a speaker's line (【...】), one line.
* u (menu): ACE.EXE's strings, written in place: their bytes the room (two letters a word).
"""
import json
import os

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import ace as A
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "menu": "u"}


def _vol(src):
    return DiskImage(src)


def scripts(vol, gd):
    return sorted(p for p, e in vol.walk() if not e["is_dir"] and p.upper().startswith(gd.upper() + "/")
                  and p.upper().endswith(".S"))


def units(lines):
    """[(first line, end line, kind)] of a script's lines."""
    out = []
    for k, line in enumerate(lines):
        t = A.show(line)
        if t.startswith("【"):
            out.append([k, k + 1, "name"])
        elif t.startswith("　") or not out or out[-1][2] == "name":
            out.append([k, k + 1, "msg"])
        else:
            out[-1][1] = k + 1
    return [tuple(u) for u in out]


def wrap(text, width=A.LINE_CELLS):
    """[line] of the English broken between words at `width` cells; \\n a forced break."""
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = word if not line else line + " " + word
            if A.cells(cand) <= width or not line:
                line = cand
                while A.cells(line) > width:
                    cut = len(line)
                    while A.cells(line[:cut]) > width:
                        cut -= 1
                    out.append(line[:cut])
                    line = line[cut:]
                continue
            out.append(line)
            line = word
        out.append(line)
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _vol(src).volumes[0]
    gd = cfg["game_dir"]
    merged, order = {}, []

    def add(kind, jp, ref, room, note):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
        order.append(key)

    for path in scripts(vol, gd):
        name = path.split("/")[-1]
        lines = A.read_script(vol.read(path))
        for s, e, kind in units(lines):
            jp = "\n".join(A.show(lines[k]) for k in range(s, e))
            if kind == "name":
                add("name", jp, "%s:%d" % (name, s), A.LINE_CELLS * 2,
                    "a speaker's name line: one line, up to %d half-width letters" % (A.LINE_CELLS * 2))
            else:
                add("msg", jp, "%s:%d" % (name, s), A.LINE_CELLS * 2 * (e - s),
                    "a paragraph: broken between words at %d half-width letters a line; \\n a new line"
                    % (A.LINE_CELLS * 2))
    exe = vol.read(gd + "/" + cfg["program"])
    for s, e in A.program_strings(exe):
        add("menu", A.show(exe[s:e]), "%s:%05x" % (cfg["program"], s), e - s,
            "a string of the program's (its menus): written in place, max_cells half-width letters")
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


def _pseudo(e):
    if e["kind"] == "msg":
        return pseudo(e["id"], 2 * len(e["jp"].replace("\n", "")))
    return pseudo(e["id"], e["max_cells"], 1.0)[:e["max_cells"]]


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _vol(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    changed = False
    for path in scripts(vol, gd):
        name = path.split("/")[-1]
        lines = A.read_script(vol.read(path))
        out = []
        for s, e, kind in units(lines):
            en = by_ref.get("%s:%d" % (name, s))
            if en is None:
                out += lines[s:e]
                continue
            if kind == "name":
                one = " ".join(en.split("\n"))
                if A.cells(one) > A.LINE_CELLS:
                    warn.append("%s: %d letters, the line holds %d" % (ids["%s:%d" % (name, s)]["id"],
                                                                      len(one), 2 * A.LINE_CELLS))
                out.append(A.encode(wrap(one)[0]))
            else:
                out += [A.encode(x) for x in wrap(en)]
        if out != lines:
            vol.write(path, A.write_script(out))
            changed = True
    prog = gd + "/" + cfg["program"]
    exe = vol.read(prog)
    new = bytearray(exe)
    for s, e in A.program_strings(exe):
        ref = "%s:%05x" % (cfg["program"], s)
        en = by_ref.get(ref)
        if en is None:
            continue
        b = A.encode(" ".join(en.split("\n")))
        if len(b) > e - s:
            warn.append("%s: %d letters, room for %d" % (ids[ref]["id"], len(b), e - s))
            b = b[:(e - s) // 2 * 2]
        new[s:e] = b.ljust(e - s, b"\0")
    if changed or bytes(new) != exe:
        vol.write(prog, A.patch_program(bytes(new)))
    vol.create(gd + "/MTL_NOTE.TXT", MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
