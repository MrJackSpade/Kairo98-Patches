"""English for D.O.'s Branmarker (pc98tl/brm.py): strings.json in, patched floppies out.

Strings:
* m (message): a message of the game (DOS.SYS, the map overlays, MAP02M's shop and town talk, the omake
  disk's events): any length, broken between words at 40 letters (the window's width), four lines a
  window (more after a key).  \\n a new line; {N1}... a name the game puts in (an item, a character),
  {V1}... a number: keep them.
* p (plain): a menu item, a name, an item, a prompt, written in place: max_cells letters.
* d (disk prompt): the prompt for another disk, in place: max_cells letters; {D} the disk's letter.
* s (scene): a line of the opening or the ending, drawn at its place: max_cells letters.
* c (credit): a line of the staff roll: max_cells letters.
* n (name): a speaker's name in the ending: max_cells letters.

English is ASCII.  A message's English that does not fit in place goes on in DATA.SYS's segment (the
program's and MAP02M's) or after the overlay's own end (the maps').
"""
import json
import os
import re

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .aypio import ascii_text
from .disk import DiskImage
from . import brm as R
from .text import pseudo

PREFIX = {"msg": "m", "plain": "p", "prompt": "d", "scene": "s", "credit": "c", "name": "n"}
NOTE = {"msg": "a message: any length (broken between words at 40 letters, four lines a window, more after "
               "a key); \\n a new line, {N..} a name and {V..} a number the game puts in: keep them",
        "plain": "a menu item, name, item or prompt in place: max_cells letters",
        "prompt": "a prompt for another disk, in place: max_cells letters, broken between words at 40; "
                  "{D} the disk's letter, put in by the game: keep it",
        "scene": "a line of the opening or the ending, drawn at its place: max_cells letters",
        "credit": "a line of the staff roll: max_cells letters",
        "name": "a speaker's name in the ending: max_cells letters"}
DISKS = "ABCDE"
MAPS = re.compile(r"MAP\d\d$")
JAPANESE = re.compile(r"[぀-ヿ一-鿿]")


def _disks(cfg, src):
    base = os.path.dirname(src)
    return [DiskImage(src)] + [DiskImage(os.path.join(base, n)) for n in cfg["disks"]]


def _files(vol):
    return [e["name"] for e in vol.listdir() if not e["is_dir"]]


def _clusters(d, lo=0):
    """Stretches of a file dense with kana runs: [[runs (match objects)]]."""
    hits = []
    for m in R.CHAR.finditer(d, lo):
        try:
            t = d[m.start():m.end()].decode("cp932")
        except UnicodeDecodeError:
            continue
        if len(R.KANA.findall(t)) * 2 >= len(t):
            hits.append(m)
    out = []
    for h in hits:
        if out and h.start() - out[-1][-1].start() < 0x200:
            out[-1].append(h)
        else:
            out.append([h])
    return [c for c in out if len(c) >= 8]


def streams(d, lo=0):
    """The stream stretches of OPENG, BROE or the omake program from `lo`: [(kind, start, end)], kind
    "name" (the speakers' table: strings ended by 00), "credit" (a staff roll: a run after a step along
    the line) or "scene"."""
    out = []
    for runs in _clusters(d, lo):
        before = [d[m.start() - 1] for m in runs]
        after = [d[m.end()] if m.end() < len(d) else 0 for m in runs]
        if sum(1 for x in after if x == 0) * 4 >= len(runs) * 3:
            kind = "name"
        elif sum(1 for x in before if 0x21 <= x < 0x40) * 2 >= len(runs):
            kind = "credit"
        else:
            kind = "scene"
        out.append((kind, runs[0].start(), runs[-1].end() + (0x80 if kind == "scene" else 0x10)))
    return out


def found(disks, cfg):
    """[(ref, kind, japanese, room)] of every text on the disks."""
    out = []
    a_dos = disks[0].volumes[0].read("DOS.SYS")
    plain_a = R.plain_drawer(a_dos)
    for x, img in zip(DISKS, disks):
        vol = img.volumes[0]
        for name in _files(vol):
            d = vol.read(name)
            if name == "DOS.SYS":
                plain = R.plain_drawer(d)
                st = streams(d, cfg["omake_streams"]) if x != "A" else []
                skip = (min(s for _k, s, _e in st), max(e for _k, _s, e in st)) if st else None
                lets = R.letters(d, R.ORG)
                for t in R.texts(d, R.ORG, plain):
                    if skip and skip[0] <= t.start < skip[1]:
                        continue
                    at = [p for p in lets if t.start <= p < t.end]
                    if at:
                        jp = R.show(d, t.start, at[0]) + "{D}" + R.show(d, at[0] + 2, t.end)
                        out.append(("%s:%s:%05x" % (x, name, t.start), "prompt", jp, t.end - t.start))
                        continue
                    out.append(_text(x, name, d, t))
                out += _scenes(x, name, d, st)
            elif name == "DATA.SYS":
                out += [_text(x, name, d, t) for t in R.texts(d, 0, data=True)]
            elif MAPS.match(name) or name in cfg["message_overlays"]:
                base = 0 if name in cfg["message_overlays"] else R.MODULE_AT
                out += [_text(x, name, d, t) for t in R.texts(d, base, plain_a)]
            elif name in cfg["stream_overlays"]:
                out += _scenes(x, name, d, streams(d))
    return out


def _text(x, name, d, t):
    ref = "%s:%s:%05x" % (x, name, t.start)
    return ref, "msg" if t.message else "plain", R.show(d, t.start, t.end), (R.WIDTH if t.message else
                                                                               t.end - t.start)


def _scenes(x, name, d, st):
    out = []
    for kind, a, b in st:
        if kind == "name":
            for t in R.texts(d, 0, data=True):
                if a <= t.start <= b:
                    out.append(("%s:%s:%05x" % (x, name, t.start), "name", R.show(d, t.start, t.end),
                                t.end - t.start))
            continue
        for s in R.scenes(d, a, b, a if kind == "credit" else None):
            out.append(("%s:%s:%05x" % (x, name, s.start), kind, R.scene_show(d, s), s.room))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    disks = _disks(cfg, src)
    merged, order = {}, []
    for ref, kind, jp, room in found(disks, cfg):
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
    t = re.sub(r"\{[^{}]*\}", "", t).replace("\n", "")
    return sum(2 if ord(c) > 0x7F else 1 for c in t)


def _pseudo(e):
    if e["kind"] == "prompt":
        head, tail = e["jp"].split("{D}")
        return (pseudo(e["id"], _cols(head), 1.0)[:max(0, _cols(head) - 1)] + " {D} " +
                pseudo(e["id"], _cols(tail), 1.0))[:e["max_cells"]]
    if e["kind"] != "msg":
        return pseudo(e["id"], _cols(e["jp"]), 1.0)[:e["max_cells"]]
    parts = re.split(r"(\{[NV]\d+\}|\n)", e["jp"])
    return "".join(p if re.fullmatch(r"\{[NV]\d+\}|\n", p) or not p else pseudo(e["id"], _cols(p))
                   for p in parts)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    disks = _disks(cfg, src)
    by_ref, warn = {}, []
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        if not text:
            continue
        text = ascii_text(text)
        if e["kind"] == "msg":
            if sorted(R.TOKEN.findall(text)) != sorted(R.TOKEN.findall(e["jp"])):
                warn.append("%s: its {N..}/{V..} differ from the Japanese's" % e["id"])
        elif e["kind"] == "prompt":
            if text.count("{D}") != 1:
                warn.append("%s: it needs one {D} (the disk's letter); the Japanese kept" % e["id"])
                continue
        else:
            text = text.replace("\n", " ")
            if len(text) > e["max_cells"]:
                warn.append("%s: %d letters, room for %d (cut)" % (e["id"], len(text), e["max_cells"]))
                text = text[:e["max_cells"]]
        for r in e["refs"]:
            by_ref[r] = (e, text)
    stem, _ext = os.path.splitext(dst)
    if not by_ref:
        disks[0].save(dst)
        for img, name in zip(disks[1:], cfg["disks"]):
            img.save("%s - %s" % (stem, name))
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    a_vol = disks[0].volumes[0]
    a_dos, a_entries = R.patch_dos(a_vol.read("DOS.SYS"))
    plain_a = R.plain_drawer(a_dos)
    try:
        for x, img in zip(DISKS, disks):
            vol = img.volumes[0]
            names = _files(vol)
            bank = R.Placer(R.GOTO_BANK, R.BANK_START, R.BANK_END, "disk %s's DATA.SYS bank" % x)
            for name in names:
                d = bytearray(vol.read(name))
                if name == "DOS.SYS":
                    if x == "A":
                        d = bytearray(a_dos)
                        entries = a_entries
                    else:
                        p, entries = R.patch_dos(bytes(d))
                        d = bytearray(p)
                        st = streams(d, cfg["omake_streams"])
                        p, _n = R.patch_module(bytes(d), entries, R.ORG)
                        d = bytearray(p)
                        _put_scenes(x, name, d, st, by_ref)
                    high = R.Placer(R.GOTO_NEAR, R.DOS_HIGH, R.DOS_HIGH_END, "DOS.SYS's own room", bank)
                    _put_texts(x, name, d, R.ORG, R.plain_drawer(bytes(d)), high, by_ref,
                               st if x != "A" else [])
                    if high.data:
                        d += bytes(R.DOS_HIGH - R.ORG - len(d)) + high.data
                elif name == "DATA.SYS":
                    continue
                elif MAPS.match(name) or name in cfg["message_overlays"]:
                    if name in cfg["message_overlays"]:
                        _put_texts(x, name, d, 0, plain_a, bank, by_ref, [])
                    else:
                        near = R.Placer(R.GOTO_NEAR, R.MODULE_AT + len(d), R.MODULE_END, "%s:%s" % (x, name))
                        _put_texts(x, name, d, R.MODULE_AT, plain_a, near, by_ref, [])
                        d += near.data
                elif name in cfg["stream_overlays"]:
                    p, _n = R.patch_module(bytes(d), a_entries)
                    d = bytearray(p)
                    _put_scenes(x, name, d, streams(d), by_ref)
                else:
                    continue
                vol.write(name, bytes(d))
            if "DATA.SYS" in names:
                d = bytearray(vol.read("DATA.SYS"))
                for t in R.texts(bytes(d), 0, data=True):
                    hit = by_ref.get("%s:DATA.SYS:%05x" % (x, t.start))
                    if hit:
                        R.patch_plain(d, t.start, t.end - t.start, hit[1])
                d += b"\0" * (R.BANK_START - len(d)) + bank.data
                vol.write("DATA.SYS", bytes(d))
    except ValueError as err:
        raise SystemExit(str(err))
    if any(t for _e, t in by_ref.values()):
        a_vol.create("MTL_NOTE.TXT", MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    disks[0].save(dst)
    for img, name in zip(disks[1:], cfg["disks"]):
        img.save("%s - %s" % (stem, name))
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))


def _put_texts(x, name, d, base, plain, place, by_ref, st):
    skip = (min(s for _k, s, _e in st), max(e for _k, _s, e in st)) if st else None
    items = []
    found_ = [t for t in R.texts(bytes(d), base, plain) if not (skip and skip[0] <= t.start < skip[1])]
    words = R.references(bytes(d), base, [base + p for t in found_ if t.message
                                          for p in range(max(0, t.start - 6), t.start + 1)],
                         [(t.start, t.rec_end) for t in found_])
    lets = R.letters(bytes(d), base) if base == R.ORG else {}
    for t in found_:
        hit = by_ref.get("%s:%s:%05x" % (x, name, t.start))
        at = [p for p in lets if t.start <= p < t.end]
        if at:
            if hit:
                try:
                    R.patch_prompt(d, base, t.start, t.end - t.start, hit[1], lets[at[0]])
                except ValueError as err:
                    raise ValueError("%s: %s" % (hit[0]["id"], err))
            continue
        if t.message:
            items.append((t, hit[1] if hit else None))
        elif hit:
            try:
                R.patch_plain(d, t.start, t.end - t.start, hit[1])
            except ValueError as err:
                raise ValueError("%s: %s" % (hit[0]["id"], err))
    R.patch_messages(d, base, items, place, words)


def _put_scenes(x, name, d, st, by_ref):
    for kind, a, b in st:
        if kind == "name":
            for t in R.texts(bytes(d), 0, data=True):
                hit = by_ref.get("%s:%s:%05x" % (x, name, t.start))
                if a <= t.start <= b and hit:
                    R.patch_plain(d, t.start, t.end - t.start, hit[1], high=True)
            continue
        for s in R.scenes(bytes(d), a, b, a if kind == "credit" else None):
            hit = by_ref.get("%s:%s:%05x" % (x, name, s.start))
            if hit:
                try:
                    d[s.start:s.end] = R.encode_scene(s, hit[1])
                except ValueError as err:
                    raise ValueError("%s: %s" % (hit[0]["id"], err))
