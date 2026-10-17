"""English for Melody's MAX engine (Kurayami; pc98tl/maxadv.py): strings.json in, a patched disk out.

Strings:
* m (message), d (dialogue line), n (speaker name), t (chapter title), c (menu choice), r (staff
  roll): script text, any length; the engine breaks lines at the window's edge, \\n a new line;
  {@xx} codes (colour, speed, {@m0} the hero's name) kept.  The same Japanese is one string.
* l (launcher): the launcher's menu, DOS text written in place: max_cells bytes (\\n, a new line,
  takes two).
* e (engine): the engine's, the installer check's and the system file's own strings: written in
  place, max_cells letters, padded with spaces.

A build with English rewrites the scripts (pc98tl/maxadv.py `rewrite`) into MDR.PCK (packed
anew), writes the launcher's strings in place, and writes the engine unpacked when its strings
change.
"""
import json
import os
import re
import unicodedata

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import maxadv as M
from . import maxpck as K
from .text import pseudo

PREFIX = {"msg": "m", "dlg": "d", "name": "n", "ttl": "t", "cho": "c", "roll": "r", "set": "v",
          "launch": "l", "engine": "e"}
NOTE = {"msg": "a message: any length (lines broken at the window's edge); \\n a new line; keep {@xx}",
        "dlg": "a line of dialogue: any length (lines broken at the window's edge); \\n a new line; keep "
               "{@xx}",
        "name": "a speaker's name, shown before the line ({@m0} the hero's name)",
        "ttl": "a chapter title",
        "cho": "a menu choice: one line",
        "roll": "the staff roll: lines as they are (\\n between them)",
        "set": "a word the script keeps and shows elsewhere ({@mN} in a line)",
        "launch": "the launcher's text (DOS, 80 columns), in place: max_cells bytes (\\n takes two)",
        "engine": "a string in a program: written in place, max_cells letters"}


def _path(cfg, name):
    return cfg["dir"] + "/" + name


def found(vol, cfg):
    """[(ref, kind, Japanese bytes, max cells or None)]."""
    out = []
    arc = vol.read(_path(cfg, cfg["pck"]))
    for name, blob in sorted(K.files(arc).items()):
        if not name.upper().endswith(".MDR") or not K.is_packed(blob):
            continue
        x = M.xor(K.unpack(blob))
        stem = name.rsplit(".", 1)[0]
        for r in M.records(x):
            kind, start, parts = r[0], r[1], r[3]
            for k, (a, b) in enumerate(parts):
                sub = kind
                if kind == "dlg":
                    sub = "name" if k == 0 else "dlg"
                if a == b:
                    continue
                out.append(("%s:%05x:%d" % (stem, start, k), sub, x[a:b], None))
    com = vol.read(_path(cfg, cfg["launcher"]))
    for s, e in M.com_strings(com):
        out.append(("L:%04x" % s, "launch", com[s:e], e - s))
    p = M.engine(vol.read(_path(cfg, cfg["engine"])))
    for fname, tag in ((cfg["starter"], "S"), (cfg["system"], "Y")):
        img = vol.read(_path(cfg, fname))
        for s, e in M.program_strings(img):
            out.append(("%s:%05x" % (tag, s), "engine", img[s:e], e - s))
    for s, e in M.program_strings(p["image"]):
        out.append(("E:%05x" % s, "engine", p["image"][s:e], e - s))
    return out


def show(kind, b):
    if kind == "launch":
        return b.decode("cp932", "replace").replace("\r\n", "\n")
    if kind == "engine":
        return M.show(b).replace("\n", "\\r")
    return M.show(b)


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
    if e["kind"] == "engine":
        codes = "".join(re.findall(r"\{@[a-z0-9]{2}\}", e["jp"]))
        room = e["max_cells"] - 3 * len(codes) // 5
        return codes[:5] + pseudo(e["id"], 2 * room, 1.0)[:max(1, room)] + codes[5:]
    out = []
    for p in re.split(r"(\{@[a-z0-9]{2}\}|\n|\x1b.)", e["jp"]):
        if not p:
            continue
        if p == "\n" or p.startswith("{@") or p.startswith("\x1b"):
            out.append(p)
        elif e["kind"] == "launch":
            out.append(pseudo(e["id"], _cols(p))[:len(p.encode("cp932", "replace"))])
        else:
            out.append(pseudo(e["id"], _cols(p)))
    return "".join(out)


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
    warn = []
    scripts, com_en, progs = {}, {}, {}
    for ref, kind, jp_b, room in found(vol, cfg):
        e, text = by_ref.get(ref, (None, ""))
        if not text:
            continue
        if kind == "engine":
            b = M.encode(text.replace("\\r", "\n"))
            if len(b) > room:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(b), room))
                b = b[:room]
            progs.setdefault(ref.split(":")[0], []).append((int(ref.split(":")[1], 16), room, b))
            continue
        if kind == "launch":
            b = text.replace("\n", "\r\n").encode("cp932", "replace").replace(b"$", b"S")
            if len(b) > room:
                warn.append("%s: %d bytes, room for %d" % (e["id"], len(b), room))
                b = b[:room]
            com_en[int(ref[2:], 16)] = (room, b)
            continue
        if M.tokens(text) != M.tokens(e["jp"]):
            warn.append("%s: the {@xx} codes differ from the Japanese's" % e["id"])
        stem, start, part = ref.split(":")
        scripts.setdefault(stem, {})[(int(start, 16), int(part))] = M.encode(text)
    if scripts:
        arc = vol.read(_path(cfg, cfg["pck"]))
        new = {}
        for name, blob in K.files(arc).items():
            stem = name.rsplit(".", 1)[0]
            if stem not in scripts:
                continue
            x = M.xor(K.unpack(blob))
            try:
                y = M.rewrite(x, scripts[stem])
            except ValueError as err:
                raise SystemExit("%s: %s; shorten its English" % (name, err))
            new[name] = K.pack(M.xor(y))
        vol.write(_path(cfg, cfg["pck"]), K.rebuild(arc, new))
    if com_en:
        p = _path(cfg, cfg["launcher"])
        data = vol.read(p)
        for s, (room, b) in com_en.items():
            data = M.in_place(data, s, s + room, b)
        vol.write(p, data)
    for tag, fname in (("S", cfg["starter"]), ("Y", cfg["system"])):
        if tag in progs:
            p = _path(cfg, fname)
            data = vol.read(p)
            for s, room, b in progs[tag]:
                data = M.in_place(data, s, s + room, b)
            vol.write(p, data)
    if "E" in progs:
        p = _path(cfg, cfg["engine"])
        eng = M.engine(vol.read(p))
        image = eng["image"]
        for s, room, b in progs["E"]:
            image = M.in_place(image, s, s + room, b)
        vol.write(p, M.engine_exe(eng, image))
        # the system file holds the settings' values as the menu shows them: they follow the menu's
        # English (its @cX dropped), cut to their room
        sysp = _path(cfg, cfg["system"])
        data = vol.read(sysp)
        vals = M.value_texts(eng["image"])
        for s, room, b in progs["E"]:
            if s not in vals:
                continue
            new = b[3:] if b[:1] == b"@" else b
            for vs, ve in M.values(data, eng["image"]):
                if data[vs:ve] == vals[s]:
                    data = M.in_place(data, vs, ve, new[:ve - vs])
        vol.write(sysp, data)
    vol.create(_path(cfg, "MTL_NOTE.TXT"),
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
