"""English for Arigata-ya's Choreographer engine (pc98tl/choreo.py: Tenkousei): strings.json in, a patched
image out.

Strings (refs FILE.SCE:place, the place of the string's operation in the original file):

* "msg": text added to a text box (the message window): a speaker's name, a paragraph; a box takes
  several, each going on where the last ended (`\\n` a new line).  The program draws ASCII half-width,
  breaks a line at the box's edge (36 half-width cells, mid-word) and pages a full box; the patcher
  breaks the English between words at `line_cells` (game.json: 35, as a full line's new line would
  leave an empty one) half-width cells (`max_cells`), going on from the column the box's last piece
  ended at.
* "date": a piece of the date line (month, day, weekday) in its small box: on one line, `max_cells`
  its share of the line's 12 cells (the box first shows a longer line's last 12); past it reported.
* "choice": a choice's text (a button's); "menu": a menu's title.  On one line, `max_cells` the room
  for it (game.json "rooms": by the box, [window, type] as `choreo.strings` gives it, the choices'
  box when none; else the Japanese's width); past it reported.

English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else `?`.
A string may take any length: the scenario is written again with its jumps and calls moved.
"""
import json
import os

from . import choreo as C
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "date": "d", "choice": "c", "menu": "u"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def cells(text):
    return max((sum(1 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 2 for c in line)
                for line in text.split("\n")), default=0)


def show(b):
    return b.decode("cp932", "replace")


def encode(text):
    out = bytearray()
    for ch in text:
        for c in SUBST.get(ch, ch):
            if c == "\n":
                out += b"\n"
            elif " " <= c <= "~":
                out.append(ord(c))
            else:
                try:
                    out += c.encode("cp932")
                except UnicodeEncodeError:
                    out += b"?"
    return bytes(out)


def wrap(text, width, col=0):
    """(text with new lines between words at `width` cells, the column it ends at); the first line
    goes on from column `col` (a box's earlier piece), a new line put first when its first word
    doesn't fit there."""
    out = []
    for n, para in enumerate(text.split("\n")):
        line, c = "", (col if n == 0 else 0)
        for word in para.split(" "):
            w = cells(word)
            sep = 1 if line else 0
            if c and c + sep + w > width:
                out.append(line)
                line, c = word, w
            else:
                line += " " * sep + word
                c += sep + w
        out.append(line)
    return "\n".join(out), c


def scenarios(vol, cfg):
    gd = cfg["game_dir"]
    names = C.files(vol.read(gd + "/" + cfg["ini"]))
    out = {}
    for n, f in sorted(names.items()):
        if f.endswith(".SCE"):
            d = vol.read(gd + "/" + f)
            if d:
                out[n] = (f, d)
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    line = cfg["line_cells"]
    rooms = {(r[0], tuple(r[1]) if r[1] else None): r[2] for r in cfg["rooms"]}
    merged, order = {}, []
    for n, (f, d) in scenarios(vol, cfg).items():
        ops = C.parse(d)
        for k, kind, s, _var, box in C.strings(ops):
            if all(c < 0x80 for c in s):
                continue
            jp = show(s)
            if kind == "msg" and box == (1, 0x0F):
                kind = "date"
            ref = "%s:%04x" % (f, ops[k][0])
            key = (kind, jp)
            room = {"msg": line, "date": cells(jp)}.get(kind, rooms.get((kind, box), max(cells(jp), 1)))
            if key in merged:
                merged[key]["refs"].append(ref)
                merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
                continue
            note = {"msg": "a message's text: broken between words at %d half-width cells" % line,
                    "date": "a piece of the date line (month, day, weekday): the line shows 12 "
                            "half-width cells when first drawn (a longer one loses its start), its numbers take "
                            "4; max_cells is this piece's share (month 2, day 2, weekday 4)",
                    "choice": "a choice (or a button): one line, its room in half-width cells",
                    "menu": "a menu's title: one line, its room in half-width cells"}[kind]
            merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": note}
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
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _pseudo(e):
    if e["kind"] == "msg":                      # (the paragraph's new lines before it kept)
        lead = e["jp"][:len(e["jp"]) - len(e["jp"].lstrip("\n"))]
        return lead + pseudo(e["id"], cells(e["jp"].replace("\n", "")))
    return pseudo(e["id"], e["max_cells"], 1.0)[:e["max_cells"]]


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    line = cfg["line_cells"]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    sc = scenarios(vol, cfg)
    new = {}
    for n, (f, d) in sc.items():
        ops = C.parse(d)
        found = {k: (kind, s_, box) for k, kind, s_, _var, box in C.strings(ops)}
        win, col = {}, {}                       # a variable's window; a window's column (the file's order)
        for k, (a, op, b) in enumerate(ops):
            if op == 0x18 and k >= 2 and ops[k - 1][1] == 0x14 and ops[k - 2][1] == 0x0C:
                win[b[1:]] = int.from_bytes(ops[k - 2][2][1:], "little")
            if op == 0xCB and k >= 2 and ops[k - 2][1] == 0x11:     # ("11 var 1B CB": the box cleared)
                col[win.get(ops[k - 2][2][1:])] = 0
            if k not in found:
                continue
            kind, s_, box = found[k]
            w = box[0] if box else None
            en = by_ref.get("%s:%04x" % (f, a))
            if en is None:
                last = show(s_).split("\n")[-1]
                c = cells(last) % (line + 1)
                col[w] = c if "\n" in show(s_) else col.get(w, 0) + c
                continue
            e = ids["%s:%04x" % (f, a)]
            if e["kind"] == "msg":
                en, col[w] = wrap(en, line, col.get(w, 0))
            elif cells(en) > e["max_cells"]:
                warn.append("%s: %d cells, room for %d" % (e["id"], cells(en), e["max_cells"]))
            new[(n, k)] = encode(en)
    try:
        built = C.build({n: d for n, (f, d) in sc.items()}, new)
    except ValueError as ex:
        raise SystemExit("%s; shorten the English" % ex)
    for n, (f, d) in sc.items():
        if built[n] != d:
            vol.write(cfg["game_dir"] + "/" + f, built[n])
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
