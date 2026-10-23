"""English for TechnoGrard's Minimum Guynarock (pc98tl/qbasic.py): strings.json in, a patched floppy out.

Strings:
* m (message): a story text, any length: {S1}-{S8} a speaker's line (the speaker's name from the speakers'
  column, {S0} a line without one), \\n a new line, {W} a key and the window cleared; each speaker's text is
  broken between words at 26 letters, a window holding 5 lines (more go on after a key).  Keep the {S..}
  and {W} where they are.
* l (line): a line of the opening, PRINTed whole at its place: max_cells letters on one line.
* n (name): a speaker's name in the window's column: up to 8 letters.
* e (program): MG.EXE's own DOS message (E:), and the lines of the installer's messages (I:, INSTALL.EXE,
  which puts MS-DOS on the game's floppy), in place: max_cells letters.

English is ASCII (the names written as two-byte half-width characters).  A build gives the changed strings
their English after the program's data (any length) and writes MG.EXE back unpacked; the installer's
English is written over its Japanese.
"""
import json
import os
import re

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import qbasic as Q
from .text import pseudo

PREFIX = {"msg": "m", "line": "l", "name": "n", "prog": "e"}
NOTE = {"msg": "a story text: any length (broken between words at 26 letters, 5 lines a window, more "
               "after a key); {S1}-{S8} a speaker's line, {S0} a line without a name, \\n a new line, {W} a key "
               "and the window cleared: keep each {S..} and {W} where it belongs",
        "line": "a line of the opening, drawn at its place: max_cells letters, one line",
        "name": "a speaker's name in the window's column: up to 8 letters",
        "prog": "a program's message, in place: max_cells letters"}
JAPANESE = re.compile(r"[ぁ-ヶ一-鿿]")
NAME = re.compile(rb"((?:[\x81-\x9f\xe0-\xef][\x40-\xfc]){8})\x81\x46(?:\x81\x40)?$")   # 8 cells, ：, a space
NAME_ROOM = 8                # letters: the 16 bytes of 8 full-width cells
DOS_MESSAGE = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]){4,}\r\n\$")
ESCAPE = re.compile(rb"\x1b\[[0-9;>?]*[A-Za-z]")
# a line of the installer's messages: after a new line, a "$" (the one before) or an escape sequence, up to
# the next CR, "$" or escape sequence
INSTALL_LINE = re.compile(rb"(?<=[\n$\0])(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|[\x20-\x23\x25-\x7e])+"
                          rb"(?=[\r$\0])")


def _path(cfg, name):
    return cfg["dir"] + "/" + name if cfg.get("dir") else name


def program(vol, cfg):
    return Q.Program(vol.read(_path(cfg, cfg["engine"])))


def installer(vol, cfg):
    """[(offset, length)] of the installer's message lines with Japanese."""
    d = vol.read(_path(cfg, cfg["installer"]))
    z = ESCAPE.sub(lambda m: b"\0" * len(m.group()), d)
    return [(m.start(), m.group().decode("cp932")) for m in INSTALL_LINE.finditer(z)
            if JAPANESE.search(m.group().decode("cp932", "replace"))]


def found(prog, vol, cfg):
    out = []
    lines = prog.lines()
    for k, ln in prog.descriptors():
        b = prog.text(k)
        t = Q.show(b)
        if not JAPANESE.search(t):
            continue
        ref = "S:%04x" % k
        m = NAME.match(b)
        if k in lines:
            out.append((ref, "line", t, len(b)))
        elif m:
            out.append((ref, "name", m.group(1).decode("cp932").replace("　", ""), NAME_ROOM))
        else:
            out.append((ref, "msg", t, Q.LINE_CELLS))
    code = bytes(prog.exe[prog.hb:prog.ds])
    for m in DOS_MESSAGE.finditer(code):
        out.append(("E:%05x" % m.start(), "prog", m.group()[:-3].decode("cp932"), m.end() - m.start() - 3))
    for at, t in installer(vol, cfg):
        out.append(("I:%04x" % at, "prog", t, len(t.encode("cp932"))))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    prog = program(vol, cfg)
    merged, order = {}, []
    for ref, kind, jp, room in found(prog, vol, cfg):
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
    t = re.sub(r"\{[^{}]*\}", "", t).replace("\n", "")
    return sum(2 if ord(c) > 0x7F else 1 for c in t)


def _pseudo(e):
    if e["kind"] != "msg":
        return pseudo(e["id"], _cols(e["jp"]))[:e["max_cells"]]
    # the filler in each of the Japanese's parts, its marks kept
    parts = re.split(r"(\{S\d\}|\{W\}|\n)", e["jp"])
    return "".join(p if re.fullmatch(r"\{S\d\}|\{W\}|\n", p) or not p else pseudo(e["id"], _cols(p))
                   for p in parts)


def run_patch(here, src, dst, mode="en"):
    from .aypio import ascii_text
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    prog = program(vol, cfg)
    install = bytearray(vol.read(_path(cfg, cfg["installer"])))
    warn, new = [], {}
    by_ref = {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            by_ref[r] = (e, text)
    for ref, (e, text) in by_ref.items():
        if not text:
            continue
        if ref.startswith("S:"):
            k = int(ref[2:], 16)
            if e["kind"] == "name":
                t = ascii_text(text).replace("\n", " ")
                if len(t) > NAME_ROOM:
                    warn.append("%s: %d letters, the column holds %d" % (e["id"], len(t), NAME_ROOM))
                old = prog.text(k)
                new[k] = Q.name(t, NAME_ROOM) + old[2 * NAME_ROOM:]
            elif e["kind"] == "line":
                t = ascii_text(text).replace("\n", " ")
                if len(t) > e["max_cells"]:
                    warn.append("%s: %d letters, the line holds %d" % (e["id"], len(t), e["max_cells"]))
                new[k] = t.encode("ascii")
            else:
                if re.findall(r"\{S\d\}|\{W\}", text) != re.findall(r"\{S\d\}|\{W\}", e["jp"]):
                    warn.append("%s: its {S..} and {W} differ from the Japanese's" % e["id"])
                new[k] = Q.encode(text)
        else:
            at = int(ref[2:], 16)
            b = ascii_text(text).replace("\n", " ").encode("ascii")
            if len(b) > e["max_cells"]:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(b), e["max_cells"]))
                b = b[:e["max_cells"]]
            if ref.startswith("I:"):
                install[at:at + e["max_cells"]] = b.ljust(e["max_cells"])
            else:
                o = prog.hb + at
                prog.exe[o:o + e["max_cells"]] = b.ljust(e["max_cells"])
    if not new and not any(t for _e, t in by_ref.values()):
        img.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    try:
        exe = Q.patch(prog, new)
    except ValueError as err:
        raise SystemExit(str(err))
    vol.write(_path(cfg, cfg["engine"]), exe)
    vol.write(_path(cfg, cfg["installer"]), bytes(install))
    vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
