"""English for Himeya Soft's Bacta 1&2 + Voice (pc98tl/b12.py): strings.json in, a patched hard disk out.

Strings:
* m (message): a message of the window (Bacta's 3 lines of 68 letters, Bacta 2's 4 of 60: max_cells), any
  length: broken between words, more lines shown a window at a time (a key between); \\n a new line.  The
  speaker's name (【...】 at its start) is a string of its own.
* n (name): a speaker's name, put before each of their messages: up to 16 letters.
* c (choice): a menu's choice: up to max_cells letters (its menu's widest Japanese).

English is ASCII (the engine draws it half-width itself).  A build writes the changed scripts again with
their texts at any length (every address moved) and the SNR archive again.
"""
import json
import os

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import b12 as B
from . import hmy as H
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "item": "c"}
NOTE = {"msg": "a message: any length (broken between words at max_cells letters, more windows for the "
               "rest); \\n a new line; the speaker's name is a string of its own",
        "name": "a speaker's name, put before their messages: up to 16 letters",
        "item": "a menu's choice: up to max_cells letters"}
NAME_ROOM = 16


def _path(cfg, name):
    return cfg["dir"] + "/" + name


def scripts(vol, cfg):
    raw = vol.read(_path(cfg, cfg["archive"]))
    members, size = B.archive(raw)
    return [(name, B.Script(B.decode(d))) for name, d in members], members, size


def _menus(sc):
    """{item start: the menu's widest item (cells)}"""
    out = {}
    for s, op, n in sc.ops:
        if op != 0x0E:
            continue
        items = [(k, ts, te) for k, ts, te in sc.texts if k == "item" and s < ts < s + n]
        widest = max((sum(H._cells(c) for c in H.show(sc.d[ts:te], 9999)) for _k, ts, te in items), default=0)
        for _k, ts, _te in items:
            out[ts] = widest
    return out


def visible(b):
    """a text with letters in it (the others are the window's codes: a key waited for, a clear...)"""
    k = 0
    while k < len(b):
        c = b[k]
        if c < 0x20:
            k += 1 + B.CODES[c - 1]
        else:
            return True
    return False


def found(vol, cfg):
    out = []
    for name, sc in scripts(vol, cfg)[0]:
        menus = _menus(sc)
        for kind, s, e in sc.texts:
            ref = "%s:%04x" % (name, s)
            if not visible(sc.d[s:e]):
                continue
            if kind == "item":
                out.append((ref, "item", H.show(sc.d[s:e], 9999), menus.get(s, 12)))
                continue
            width, _rows = sc.window_at(s)
            jp = H.show(sc.d[s:e], width)
            m = H.SPEAKER.match(jp)
            if m:
                out.append((ref, "name", m.group(1), NAME_ROOM))
                jp = jp[m.end():]
            out.append((ref, "msg", jp, width))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for ref, kind, jp, room in found(vol, cfg):
        if not jp.strip("　\n"):
            continue
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
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
    return sum(H._cells(c) for c in t.replace("\n", ""))


def run_patch(here, src, dst, mode="en"):
    from .aypio import ascii_text
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    by_ref = {}
    for e in doc["strings"]:
        text = e["en"]
        if mode == "pseudo":
            text = pseudo(e["id"], _cols(e["jp"]))
            if e["kind"] != "msg":
                text = text[:e["max_cells"]]
        for r in e["refs"]:
            by_ref[(r, e["kind"])] = (e, text)
    warn = []
    scs, members, size = scripts(vol, cfg)
    changed = {}
    for name, sc in scs:
        new = {}
        for kind, s, e in sc.texts:
            ref = "%s:%04x" % (name, s)
            if not visible(sc.d[s:e]):
                continue
            if kind == "item":
                ent, text = by_ref.get((ref, "item"), (None, ""))
                if text:
                    b = ascii_text(text).replace("\n", " ").encode("ascii")
                    if len(b) > ent["max_cells"]:
                        warn.append("%s: %d letters, the menu's room %d" % (ent["id"], len(b), ent["max_cells"]))
                    new[s] = b
                continue
            ent, text = by_ref.get((ref, "msg"), (None, ""))
            nent, name_en = by_ref.get((ref, "name"), (None, ""))
            if not text and not name_en:
                continue
            width, rows = sc.window_at(s)
            jp = H.show(sc.d[s:e], width)
            m = H.SPEAKER.match(jp)
            who = m.group(1).encode("cp932") if m else b""
            if name_en:
                head = ascii_text(name_en).replace("\n", " ").encode("ascii")
                if len(head) > NAME_ROOM:
                    warn.append("%s: %d letters, room for %d" % (nent["id"], len(head), NAME_ROOM))
                head += b" "
            else:
                head = who
            body = B.layout(text, width, rows, first=len(head)) if text else sc.d[s + len(who):e]
            new[s] = head + body
        if new:
            try:
                changed[name] = B.encode(B.rebuild(sc, new))
            except B.ScriptError as err:
                raise SystemExit("%s: %s; shorten its English" % (name, err))
    if changed:
        vol.write(_path(cfg, cfg["archive"]),
                  B.archive_bytes([(n, changed.get(n, d)) for n, d in members], size))
        vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
