"""English for ZyX's engine (pc98tl/zyx.py; Ikazuchi no Senshi Raidy 2, Ring Out!!): strings.json in,
a patched image out.

Strings:

* "msg": a text run of a script (refs SCRIPT.ZSD:offset, the run's first byte, after the FF): any
  length.  The window breaks its lines between words at its edge and, when full, waits for a key
  and starts a new page.  A run's line breaks and pages are the script's commands around it, so a
  `\\n` in the English is a space.  A run the script follows with an inserted name or number (its
  note says so) is drawn on directly before it.
* "item": a choice menu's item (a run between op 72h n and 72h 00, refs as a message's): one line
  in the menu's box, `max_cells` the widest Japanese item of the menu (its box's room); past it
  the line breaks inside the box (reported).
* "label": a run of op 71h, drawn at the place the op gives, one line without breaks: `max_cells`
  the Japanese's (past it the letters run on over what is beside it, reported).
* "name": a speaker's name (refs NAME.ZSD:index, the table op 19h n loads): `max_cells` its bytes,
  2n for the least n the scripts load it with (one a letter, two for the half-width letters'
  start and end, two for a full-width character); past it the English is cut and reported.
* "command": a command of the game's menus (refs KOM_F0.ZSS:index, the table op 18h n loads): as a
  name.
* "engine": a message in the program's data (refs PROGRAM:offset), written in its own bytes:
  `max_cells` its room (one a letter, two for a full-width character); past it the English is cut
  and reported.

English is ASCII, drawn half-width; another character is written in Shift-JIS when it has it (two
bytes, full-width), else as `?`.  A script with its English may take 65535 bytes; a build past it is
refused and names the script.
"""
import json
import os
import re
import struct

from . import zyx
from .alice_sys2_tl import sha256
from .text import pseudo, sjis_cols

PREFIX = {"msg": "m", "item": "i", "label": "l", "name": "n", "command": "c", "engine": "e"}
INSERT = {9: "a name", 0xA: "a number", 0xC: "a name"}


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def _path(cfg, name):
    return cfg["game_dir"] + "/" + name if cfg["game_dir"] else name


def program_runs(exe):
    """[(start, end)] (file offsets) of the message runs in ZVA98.EXE's data: FF, Shift-JIS, NUL, two
    characters at least; a run the program writes into (a drive's letter, a disk's number) left out."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 0x18)[0]
    segs = sorted({struct.unpack_from("<H", exe, hdr + struct.unpack_from("<H", exe, rel_at + 4 * k)[0] +
                                      16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0])[0]
                   for k in range(nrel)})
    ds = min(s for s in segs if s > 0) * 16
    code = exe[hdr:hdr + ds]
    out = []
    for m in re.finditer(rb"\xff((?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){2,})\x00", exe[hdr + ds:hdr + ds + 0x10000]):
        a, b = m.start(1), m.end(1)
        written = any(re.search(rb"(?:\xa2|\x88[\x06\x16\x0e\x1e\x26\x36]|\xc6\x06)" + re.escape(struct.pack("<H", p)), code)
                      for p in range(a, b))
        if not written:
            out.append((hdr + ds + a, hdr + ds + b))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    exe = vol.read(_path(cfg, cfg["program"]))
    prog = zyx.Program(exe)
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
    members = zyx.members(vol.read(_path(cfg, cfg["archive"])))
    tables = zyx.name_tables(members)
    for name, m in members:
        if name in tables:
            op, n = tables[name]
            room = 2 * n
            kind = "name" if op == 0x19 else "command"
            for k, raw in enumerate(zyx.names(m)[0]):
                add(kind, prog.decode(raw), "%s:%d" % (name, k), room,
                    "%s: %d bytes (a letter one, and two for the half-width letters' start and end)" % (
                        "a speaker's name" if kind == "name" else "a command of the game's menus", room))
            continue
        try:
            d = zyx.script_data(m)
        except ValueError:
            continue
        if not zyx.is_script(d):
            continue
        rs = zyx.runs(prog, d)
        item_cells = {}
        for a, b in zyx.menus(prog, d):
            inside = [(x, y) for x, y in rs if a < x < b]
            width = max([_cells(prog.decode(d[x:y])) for x, y in inside] or [0])
            for x, y in inside:
                item_cells[x] = width
        fixed = zyx.placed(prog, d)
        for s, e in rs:
            jp = prog.decode(d[s:e])
            if not jp.strip("　 "):
                continue
            if s in fixed:
                add("label", jp, "%s:%04x" % (name, s), _cells(jp),
                    "drawn at a fixed place without line breaks: its room the Japanese's")
                continue
            if s in item_cells:
                add("item", jp, "%s:%04x" % (name, s), item_cells[s],
                    "a choice menu's item: one line in its box (the menu's widest Japanese item)")
                continue
            nxt = d[e + 1] if e + 1 < len(d) else 0
            note = "followed by %s the script draws" % INSERT[nxt] if nxt in INSERT else None
            add("msg", jp, "%s:%04x" % (name, s), cfg["window_cells"], note)
    for s, e in program_runs(exe):
        add("engine", prog.decode(exe[s:e]), "%s:%04x" % (cfg["program"], s), e - s,
            "ZVA98.EXE's message, in its own bytes")
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


def _cells(text):
    return sjis_cols(text.encode("cp932", "replace"))


def _pseudo(e):
    if e["kind"] in ("item", "label"):
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"]]
    if e["kind"] in ("engine", "name", "command"):
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"] - 2]
    return pseudo(e["id"], sjis_cols(e["jp"].encode("cp932", "replace")))


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
            rooms[r] = (e["kind"], e["max_cells"])
            if text:
                by_ref[r] = text
    warn, done = [], 0
    exe_path = _path(cfg, cfg["program"])
    exe = bytearray(vol.read(exe_path))
    prog = zyx.Program(bytes(exe))
    arc_items = []
    members = zyx.members(vol.read(_path(cfg, cfg["archive"])))
    tables = zyx.name_tables(members)
    for name, m in members:
        if name in tables:
            room = 2 * tables[name][1]
            plates, tail, head = zyx.names(m)
            changed = False
            for k in range(len(plates)):
                ref = "%s:%d" % (name, k)
                if ref not in by_ref:
                    continue
                t = by_ref[ref]
                if len(zyx.encode(t)) > room:
                    warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(zyx.encode(t)), room))
                    while len(zyx.encode(t)) > room:
                        t = t[:-1]
                plates[k] = zyx.encode(t)
                changed = True
            new = zyx.names_file(plates, tail, head) if changed else m
            done += new != m
            arc_items.append((name, new))
            continue
        try:
            d = zyx.script_data(m)
        except ValueError:
            arc_items.append((name, m))
            continue
        values = {}
        if zyx.is_script(d):
            for s, e in zyx.runs(prog, d):
                ref = "%s:%04x" % (name, s)
                if ref in by_ref:
                    values[s] = zyx.encode(by_ref[ref])
                    kind, cells = rooms[ref]
                    if kind in ("item", "label") and _cells(by_ref[ref]) > cells:
                        warn.append("%s: %d letters, past its room (%d)" % (ids[ref], _cells(by_ref[ref]), cells))
        try:
            new = zyx.rebuild(d, values, prog) if values else m
        except OverflowError:
            new = bytes(zyx.SCRIPT_MAX + 1)
        if len(new) > zyx.SCRIPT_MAX:
            if mode != "pseudo":
                raise SystemExit("%s: %d bytes with its English, a script may take %d; shorten these strings: %s" % (
                    name, len(new), zyx.SCRIPT_MAX, ", ".join(sorted({ids["%s:%04x" % (name, s)] for s in values}))))
            # (the --pseudo filler: every run cut in proportion until the script fits)
            ratio = 1.0
            while len(new) > zyx.SCRIPT_MAX:
                ratio *= 0.9
                cut = {s: zyx.encode(by_ref["%s:%04x" % (name, s)][:max(4, int(len(by_ref["%s:%04x" % (name, s)]) * ratio))])
                       for s in values}
                try:
                    new = zyx.rebuild(d, cut, prog)
                except OverflowError:
                    continue
            warn.append("%s: the filler was cut to %d%% to fit the script's 64 KB" % (name, int(ratio * 100)))
        if new != m:
            done += 1
        arc_items.append((name, new))
    vol.write(_path(cfg, cfg["archive"]), zyx.archive(arc_items))
    for s, e in program_runs(bytes(exe)):
        ref = "%s:%04x" % (cfg["program"], s)
        if ref not in by_ref:
            continue
        b = zyx.encode(by_ref[ref])
        room = e - s
        if len(b) > room:
            warn.append("%s: cut to its %d bytes" % (ids[ref], room))
            b = zyx.encode(by_ref[ref][:room - 2])
            while len(b) > room:
                b = b[:-2] + b"\x80" if b.endswith(b"\x80") else b[:-1]
        exe[s:e] = b + b" " * (room - len(b))
    vol.write(exe_path, zyx.patch_exe(bytes(exe)))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
