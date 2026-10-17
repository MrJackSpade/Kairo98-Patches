"""English for May-Be Soft's Escape! (pc98tl/fas.py): strings.json in, a patched disk out.

Strings:
* m (message): a message, any length: broken between words at the window's 47 columns (under the
  speaker's name), a key wait and a new window after five lines; \\n a new line; {K} a key wait, kept.
* n (name): a speaker's name (the brackets included), up to max_cells letters (the column the lines
  start at under it).
* e (program): FAS.EXE's own messages, in place: max_cells letters.

A build with English writes the scripts' packs (ES_FSXP.DAT, ES_HSXP.DAT) again and FAS.EXE with the
half-width helpers and its own text.
"""
import json
import os
import unicodedata

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import fas as F
from . import starpt as S
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "prog": "e"}
NOTE = {"msg": "a message: any length (broken between words and paged by the patcher); \\n a new line; "
               "keep each {K} (a key wait)",
        "name": "a speaker's name: up to max_cells letters",
        "prog": "the program's own message, in place: max_cells letters"}
PACKS = ("ES_FSXP.DAT", "ES_HSXP.DAT")
LIMIT = 0x8000              # a script's bytes (the program's buffer for a scene it loads from a scene)


def _path(cfg, name):
    return cfg["dir"] + "/" + name


def _indents(toks):
    """{token index: the indent (columns) in force there}."""
    out, ind = {}, 0
    for k, (kind, b) in enumerate(toks):
        out[k] = ind
        if kind == "op" and b[0] == F.INDENT:
            ind = 2 * b[1]
        elif kind == "op" and b[0] == F.END:
            ind = 0
    return out


def found(vol, cfg):
    """[(ref, kind, Japanese text, max cells or None)]."""
    out = []
    for pk in PACKS:
        files, _tail = F.pack(vol.read(_path(cfg, pk)))
        for name, script in files:
            for at, head, code, names in F.events(script):
                for a, b in F.streams(code):
                    toks = F.tokens(code, a, b)
                    ind = _indents(toks)
                    for kind, i, j in F.units(toks):
                        ref = "%s:%s:%x:%x:%d" % (pk[3], name, at, a, i)
                        room = 2 * toks[j][1][1] if kind == "name" else None
                        out.append((ref, kind, F.show(toks[i:j]), room))
    exe = vol.read(_path(cfg, cfg["engine"]))
    img = exe[int.from_bytes(exe[8:10], "little") * 16:]
    for s, e in S.program_strings(bytes(img)):
        out.append(("E:%05x" % s, "prog", S.show(img[s:e]), e - s))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for ref, kind, jp, room in found(vol, cfg):
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


def _jp_cols(text):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text.replace("{K}", ""))


def stream_english(toks, texts, warn):
    """A stream's tokens again as bytes, the units with English ({token index: (kind, English, id)})
    written by the patcher."""
    out = bytearray()
    ind = _indents(toks)
    spans = {i: (kind, j) for kind, i, j in F.units(toks)}
    row, col = 0, 0
    k = 0
    while k < len(toks):
        kind, b = toks[k]
        if k in spans and k in texts:
            ukind, j = spans[k]
            _k, text, ident = texts[k]
            if ukind == "name":
                room = 2 * toks[j][1][1]
                nb = F.name(text, room)
                if len(nb) > room:
                    warn.append("%s: %d letters, room for %d" % (ident, len(nb), room))
                out += nb
                col = len(nb)
            else:
                mb, row = F.message(text, col, ind[k], row)
                out += mb
                col = ind[k]
            k = j
            continue
        out += b
        if kind == "text":
            col += len(b)
        elif kind == "op" and b[0] == F.NEWLINE:
            row, col = (row + 1) % F.PAGE, ind[k]
        elif kind == "op" and b[0] == F.END:
            row, col = 0, 0
        k += 1
    return bytes(out)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    by_ref = {}
    for e in doc["strings"]:
        text = pseudo(e["id"], _jp_cols(e["jp"])) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            by_ref[r] = (e, text)
    if not any(t for _e, t in by_ref.values()):
        img.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    warn = []
    for pk in PACKS:
        p = _path(cfg, pk)
        files, tail = F.pack(vol.read(p))
        new_files = []
        for name, script in files:
            codes = {}
            for at, head, code, names in F.events(script):
                st = F.streams(code)
                new_code, remap = bytearray(), {}
                changed = False
                for a, b in st:
                    toks = F.tokens(code, a, b)
                    texts = {}
                    for kind, i, j in F.units(toks):
                        e, text = by_ref.get("%s:%s:%x:%x:%d" % (pk[3], name, at, a, i), (None, ""))
                        if text:
                            texts[i] = (kind, text, e["id"])
                    remap[a] = len(new_code)
                    if texts:
                        new_code += stream_english(toks, texts, warn)
                        changed = True
                    else:
                        new_code += code[a:b]
                remap[len(code)] = len(new_code)
                if changed:
                    if len(new_code) > 0xFFFF:
                        raise SystemExit("%s event %x: %d bytes of code with its English (an event holds 65,535)"
                                         % (name, at, len(new_code)))
                    codes[at] = (bytes(new_code), remap)
            if codes:
                script = F.script_bytes(script, codes)
                if len(script) > LIMIT:
                    raise SystemExit("%s: %d bytes with its English, the program's buffer holds %d; shorten "
                                     "its English" % (name, len(script), LIMIT))
            new_files.append((name, script))
        vol.write(p, F.pack_bytes(new_files, tail))
    exe = vol.read(_path(cfg, cfg["engine"]))
    image = exe[int.from_bytes(exe[8:10], "little") * 16:]
    places = []
    for s, end in S.program_strings(bytes(image)):
        e, text = by_ref.get("E:%05x" % s, (None, ""))
        if not text:
            continue
        b = F.ascii_text(text).replace("\n", " ").encode("ascii")
        if len(b) > end - s:
            warn.append("%s: %d letters, room for %d" % (e["id"], len(b), end - s))
            b = b[:end - s]
        places.append((s, b.ljust(end - s, b"\0")))
    vol.write(_path(cfg, cfg["engine"]), F.patch_exe(exe, places))
    vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
