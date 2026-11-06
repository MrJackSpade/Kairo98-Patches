"""English for FairyDust's Ma Doll (pc98tl/madoll.py): strings.json in, a patched hard disk out.

Strings:
* m (message): a message (a record whose op's low byte is 02), any length: broken between words at 58
  letters, the window scrolling by itself; \\n a new line; {N0} the hero's name and {N1}.. the cast's
  names and 【】 tags the program puts in (n ids), {01} the program's own: keep them.
* c (choice): a choice's item (the scripts' second blocks): one line, max_cells letters.
* n (name): a name the messages put in ({Nx}, kept in MDMAIN.EXE: the hero's, the cast's and their
  【】 tags), in place: max_cells letters (the Japanese's bytes; an odd length padded with a space, as
  the program draws a name two bytes at a time).
* e (program): MDMAIN.EXE's own strings (the menus, the name entry's words), in place: max_cells
  letters.

A build with no English leaves the disk as it is; one with English writes every script's messages to
its STY_nn.MSG, the scripts' choices anew at their text's end, and the program patched (madoll.py).
"""
import json
import os
import re
import struct
import unicodedata

from . import madoll as M
from .alice_sys2_tl import sha256
from .disk import DiskImage
from .text import pseudo

PREFIX = {"msg": "m", "choice": "c", "name": "n", "prog": "e"}
NOTE = {"msg": "a message: any length (broken between words at 58 letters, the window scrolls); \\n a new "
               "line; keep {N0} (the hero's name), {N1}.. (the names the program puts in) and {01}",
        "choice": "a choice's item: one line, max_cells letters",
        "name": "a name the messages put in ({Nx}): max_cells letters",
        "prog": "the program's own string, in place: max_cells letters"}
JAPANESE = re.compile(r"[ぁ-ヶ一-鿿々]")
PROG_TEXT = re.compile(rb"(?<=\0)(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|[\xa1-\xdf])+(?=\0)")
KANA_ROW = re.compile(r"[ぁ-ゖァ-ヶ。「」、‥ー…ｦ-ﾟ]{5,}")   # (the name entry's rows of letters, picked by their place)


def _dir(cfg):
    return cfg["dir"]


def _scripts(vol, cfg):
    return sorted(e["name"] for e in vol.listdir(vol.find(_dir(cfg))["cluster"])
                  if re.fullmatch(r"STY_\w+\.SCR", e["name"]))


def _program(vol, cfg):
    exe = vol.read(_dir(cfg) + "/" + cfg["program"])
    u = M.unpack_program(exe)
    return exe, u, u[struct.unpack_from("<H", u, 8)[0] * 16:]


def _cells(t):
    t = re.sub(r"\{[^{}]*\}", "", t)
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


def prog_strings(img):
    """[(DS place, bytes)] of the program's Japanese strings in its data (not the names it puts in)."""
    ds = M.DS_PARA * 16
    names = {p for p, _b in M.inserts(img).values()}
    out = []
    for m in PROG_TEXT.finditer(img, ds, ds + 0x2000):
        p = m.start() - ds
        try:
            t = m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        if p not in names and JAPANESE.search(t) and len(t) >= 2 and not KANA_ROW.fullmatch(t):
            out.append((p, m.group()))
    return out


def found(vol, cfg):
    """[(ref, kind, Japanese, room)]."""
    _exe, _u, img = _program(vol, cfg)
    tab = M.table(img)
    out = []
    for name in _scripts(vol, cfg):
        data = vol.read(_dir(cfg) + "/" + name)
        _n, _n2, _recs, area = M.load(data)
        for kind, _k, _f, s in M.strings(data):
            raw = area[s:M.text_end(area, s)]
            jp = M.show(raw, tab)
            if not JAPANESE.search(jp):
                continue
            out.append(("%s:%04x" % (name, s - 2), kind, jp, M.WIDTH if kind == "msg" else _cells(jp)))
    for x, (p, b) in sorted(M.inserts(img).items()):
        t = b.decode("cp932", "replace")
        if JAPANESE.search(t):
            out.append(("N:%s" % chr(x), "name", t, len(b)))
    for p, b in prog_strings(img):
        out.append(("E:%04x" % p, "prog", b.decode("cp932"), len(b)))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for ref, kind, jp, room in found(vol, cfg):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room)
            continue
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": NOTE[kind]}
        order.append(key)
    counts, strings = {}, []
    for key in order:
        e = merged[key]
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        strings.append({"id": "%s%05d" % (PREFIX[e["kind"]], counts[e["kind"]]), **e})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):
        old = {(x["kind"], x["jp"]): x for x in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                e["en"] = prev.get("en", "")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _pseudo(e):
    keep = " ".join(re.findall(r"\{N.\}|\{01\}", e["jp"]))
    if e["kind"] == "msg":
        return pseudo(e["id"], _cells(e["jp"])) + (" " + keep if keep else "")
    return pseudo(e["id"], e["max_cells"], 1.0)[:e["max_cells"]]


def _short(text, room, what, warn):
    b = M._ascii(" ".join(text.split("\n"))).encode("ascii")
    if len(b) > room:
        warn.append("%s: %d letters, room for %d (cut)" % (what, len(b), room))
        b = b[:room]
    return b


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img_file = DiskImage(src)
    vol = img_file.volumes[0]
    by_ref = {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        if text:
            for r in e["refs"]:
                by_ref[r] = (e, text)
    if not by_ref:
        img_file.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    warn = []
    exe, u, img = _program(vol, cfg)
    tab = M.table(img)
    names = {chr(x): b.decode("cp932", "replace") for x, (_p, b) in M.inserts(img).items()}
    for x, (_p, b) in M.inserts(img).items():
        hit = by_ref.get("N:%s" % chr(x))
        if hit:
            names[chr(x)] = hit[1]
    need = 0
    msgs = {}
    for name in _scripts(vol, cfg):
        path = _dir(cfg) + "/" + name
        data = vol.read(path)
        n, _n2, recs, area = M.load(data)
        places, texts = {}, []
        # (the text area written anew with only the pictures' names and the choices, their places moved:
        # the messages go to the .MSG file)
        new_area, moved = bytearray(2), {}

        def keep(s, enc):
            if (s, enc) not in moved:
                moved[(s, enc)] = len(new_area) - 2
                new_area.extend(enc + b"\0")
            return moved[(s, enc)]
        for k, (op, a, b) in enumerate(recs[:n]):
            if op & 0xFF == M.PICTURE_OPS_LOW and a != 0xFFFF:
                s = a + 2
                recs[k][1] = keep(s, area[s:M.text_end(area, s)])
        for kind, k, f, s in M.strings(data):
            raw = area[s:M.text_end(area, s)]
            hit = by_ref.get("%s:%04x" % (name, s - 2))
            if kind == "msg":
                if s not in places:
                    places[s] = len(texts)
                    texts.append(M.english(hit[1], names) if hit else M.spell_out(raw, tab))
                continue
            enc = _short(hit[1], hit[0]["max_cells"], hit[0]["id"], warn) if hit else M.spell_out(raw, tab)
            recs[k][1] = keep(s, enc)
        body, paras = M.msg_file(texts)
        for k, (op, a, b) in enumerate(recs[:n]):
            if op & 0xFF == M.MSG_OPS_LOW and b != 0xFFFF:
                recs[k][2] = paras[places[b + 2]]
        if len(new_area) - 2 > M.HELPERS - M.TEXT_SEG * 16 - 2:
            raise SystemExit("%s: its text area takes %d bytes, the helpers start at %d" % (
                name, len(new_area), M.HELPERS - M.TEXT_SEG * 16))
        vol.write(path, M.save(data, recs, bytes(new_area)))
        mpath = _dir(cfg) + "/" + name[:-4] + ".MSG"
        try:
            vol.find(mpath)
            vol.write(mpath, body)
        except FileNotFoundError:
            vol.create(mpath, body)
        need = max(need, (len(body) + 15) // 16)
        msgs[name] = len(body)
    prog = bytearray(M.patch_program(exe, need))
    base = struct.unpack_from("<H", prog, 8)[0] * 16
    ds = base + M.DS_PARA * 16
    for x, (p, b) in M.inserts(img).items():
        hit = by_ref.get("N:%s" % chr(x))
        if hit:
            # (drawn two bytes at a time: an odd length is padded with a space, or loses its last letter)
            enc = _short(hit[1], len(b), hit[0]["id"], warn)
            if len(enc) % 2:
                enc = enc + b" " if len(enc) < len(b) else enc[:-1]
            prog[ds + p:ds + p + len(b)] = enc.ljust(len(b), b"\0")
    for p, b in prog_strings(img):
        hit = by_ref.get("E:%04x" % p)
        if hit:
            enc = _short(hit[1], len(b), hit[0]["id"], warn)
            prog[ds + p:ds + p + len(b)] = enc.ljust(len(b), b" ")
    vol.write(_dir(cfg) + "/" + cfg["program"], bytes(prog))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img_file.save(dst)
    print("patched %s (%s mode, %d/%d strings translated; the largest message file %d bytes)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), max(msgs.values())))
