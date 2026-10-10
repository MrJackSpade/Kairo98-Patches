"""English for D.O.'s CHAN.EXE games (pc98tl/chan.py): strings.json in, a patched image out.

Strings:

* "msg": the quiz's questions (QDAT, refs Qnn.QDT:question), and the girls' profiles (CHAN.EXE's
  table, refs CHAN.EXE:offset); drawn in the text window, `max_cells` letters a line (the window's
  room), the program wrapping between words and paging; \\n starts a new line.
* "cmd": the quiz's choices (refs Qnn.QDT:question.choice), each one line at its place.
* "engine": the program's other strings (refs CHAN.EXE:offset), each in its own bytes; and the
  messages of a console program run before the game (game.json "console_programs", Yuu Disk Vol. 7's
  PSTAT.EXE: DOS's text console), each in its own bytes, its escape sequences and printf fields
  {X1}, {X2}... kept in their order.

English is ASCII (one byte a letter, drawn half-width by the patch's helper); another character is
written in Shift-JIS when it has it (two bytes, full-width), else as `?`.
"""
import json
import os
import re
import struct

from . import chan
from .alice_sys2_tl import sha256

PREFIX = {"msg": "m", "cmd": "c", "engine": "e"}
SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "♥": "<3"}
QUESTION_CELLS = 50             # the quiz window's line: 50 bytes (4C06h's dh)
PROFILE_CELLS = 38              # the profiles' window's line
SCREEN_COLS = 80


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def _path(cfg, name):
    return cfg["game_dir"] + "/" + name if cfg["game_dir"] else name


def encode(text, newlines=True):
    """English as the program's bytes: ASCII, \\n as 0Ah (or a space where a string has no new line)."""
    out = bytearray()
    for c in "".join(SUBST.get(c, c) for c in text):
        if c == "\n":
            out += b"\x0a" if newlines else b" "
        elif 0x20 <= ord(c) < 0x7F:
            out.append(ord(c))
        else:
            try:
                b = c.encode("cp932")
            except UnicodeEncodeError:
                b = b"?"
            out += b if len(b) == 2 else b"?"
    return bytes(out)


def decode(raw):
    return raw.decode("cp932", "replace")


CONSOLE_TOKEN = re.compile(rb"\x1b\[(?:%s|[^A-Za-z])*[A-Za-z]|%[-0-9.l]*[sdouxXc%]", re.S)
TOKEN = re.compile(r"\{X(\d+)\}")


def console_text(raw):
    """(a console message as text, its tokens: escape sequences and printf fields as {X1}...)."""
    tokens = [m.group() for m in CONSOLE_TOKEN.finditer(raw)]
    parts = CONSOLE_TOKEN.split(raw)
    text = ""
    for k, p in enumerate(parts):
        text += decode(p) + ("{X%d}" % (k + 1) if k < len(tokens) else "")
    return text, tokens


def console_bytes(text, raw, sid):
    """(a console message's English in raw's bytes, NUL after; whether it was cut)."""
    _t, tokens = console_text(raw)
    found = [int(n) for n in TOKEN.findall(text)]
    if found != list(range(1, len(tokens) + 1)):
        raise SystemExit("%s: the English must keep %s in this order" % (
            sid, ", ".join("{X%d}" % (k + 1) for k in range(len(tokens)))))
    parts = [encode(p) for p in TOKEN.split(text)[0::2]]
    # (past the room the text is cut from its end, the tokens kept whole)
    over = sum(len(p) for p in parts) + sum(len(t) for t in tokens) - len(raw)
    cut = over > 0
    k = len(parts) - 1
    while over > 0 and k >= 0:
        drop = min(over, len(parts[k]))
        parts[k] = parts[k][:len(parts[k]) - drop]
        over -= drop
        k -= 1
    out = bytearray()
    for k, p in enumerate(parts):
        out += p
        if k < len(tokens):
            out += tokens[k]
    return bytes(out) + bytes(len(raw) + 1 - len(out)), cut


def _choice_cells(cfg):
    """The letters from the choices' place (column 57) to the screen's edge."""
    return cfg.get("choice_cells", SCREEN_COLS - 57)


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    exe = vol.read(_path(cfg, cfg["program"]))
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
    members, _hs = chan.qdat_read(vol.read(_path(cfg, "QDAT")))
    for name, m in members:
        for k, (ans, strs) in enumerate(chan.member_read(m)):
            add("msg", decode(strs[0]), "%s:%02x" % (name, k), QUESTION_CELLS,
                "a quiz question; its choices are the c strings with refs %s:%02x.1-3 (choice %d is right)"
                % (name, k, ans))
            for c in range(3):
                add("cmd", decode(strs[1 + c]), "%s:%02x.%d" % (name, k, c + 1), _choice_cells(cfg))
    t, refs, block = chan.profiles(exe)
    for o in sorted(set(refs)):
        add("msg", decode(exe[o:exe.index(0, o)]), "%s:%04x" % (cfg["program"], o), PROFILE_CELLS,
            "a girl's profile (the lines after 0Ah, \\n in the English)")
    for s, e in chan.strings(exe):
        add("engine", decode(exe[s:e - 1]), "%s:%04x" % (cfg["program"], s), e - s - 1)
    for pname in cfg.get("console_programs", []):
        raw = vol.read(_path(cfg, pname))
        for s, e in chan.console_strings(raw):
            text, tokens = console_text(raw[s:e - 1])
            note = ("a message the program prints to DOS's console; {X1}...: its escape sequences and printf "
                    "fields, kept in this order" if tokens else "a message the program prints to DOS's console")
            add("engine", text, "%s:%04x" % (pname, s), e - s - 1 - sum(len(t) for t in tokens), note)
    counts, strings = {}, []
    for key in order:
        e = merged[key]
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        strings.append({"id": "%s%05d" % (PREFIX[e["kind"]], counts[e["kind"]]), **e})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                e["en"] = prev.get("en", "")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _cut_all(values, ratio):
    return {k: v[:max(4, int(len(v) * ratio))] for k, v in values.items()}


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    prog = cfg["program"]
    exe = vol.read(_path(cfg, prog))
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        if mode == "pseudo":
            text = pseudo(e["id"], 2 * len(e["jp"]) + 8)
            if e["kind"] != "msg":
                text = text[:e["max_cells"]]
        else:
            text = e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            if text:
                by_ref[r] = text
    warn = []
    # (the quiz: each member rebuilt with its English; past the room, refused, or the filler cut)
    members, hs = chan.qdat_read(vol.read(_path(cfg, "QDAT")))
    ratio = 1.0
    while True:
        out_members = []
        for name, m in members:
            ents = []
            for k, (ans, strs) in enumerate(chan.member_read(m)):
                new = list(strs)
                for c in range(4):
                    ref = "%s:%02x" % (name, k) + ("" if c == 0 else ".%d" % c)
                    if ref in by_ref:
                        t = by_ref[ref] if ratio == 1.0 else by_ref[ref][:max(4, int(len(by_ref[ref]) * ratio))]
                        new[c] = encode(t, newlines=(c == 0))
                ents.append((ans, new))
            out_members.append((name, chan.member_write(ents)))
        qdat = chan.qdat_write(out_members, hs)
        if len(qdat) <= chan.QDAT_MAX:
            break
        if mode != "pseudo":
            raise SystemExit("QDAT: %d bytes, the program reads 163840; shorten the quiz's strings" % len(qdat))
        ratio *= 0.9
    if ratio < 1.0:
        warn.append("QDAT: the filler was cut to %d%% to fit the program's reads" % (ratio * 100))
    vol.write(_path(cfg, "QDAT"), qdat)
    out = bytearray(exe)
    # (the profiles: one block in the room the Japanese took, the table's offsets anew)
    t, refs, block = chan.profiles(exe)
    hdr, ds = chan.data_segment(exe)
    keys = ["%s:%04x" % (prog, a) for a, _e in block]
    raws = [encode(by_ref[k]) if k in by_ref and a in refs else exe[a:e - 1] for k, (a, e) in zip(keys, block)]
    room = block[-1][1] - block[0][0]
    if sum(len(r) + 1 for r in raws) > room:
        if mode != "pseudo":
            raise SystemExit("the profiles take %d bytes, their room %d; shorten these strings: %s" % (
                sum(len(r) + 1 for r in raws), room, ", ".join(sorted({ids[k] for k in keys if k in ids}))))
        share = room // len(raws) - 1
        raws = [r[:share] for r in raws]
        warn.append("the profiles' filler was cut to fit their room (%d bytes)" % room)
    at, moved = block[0][0], {}
    for (a, _e), r in zip(block, raws):
        moved[a] = at
        out[at:at + len(r) + 1] = r + b"\x00"
        at += len(r) + 1
    out[at:block[-1][1]] = bytes(block[-1][1] - at)
    for n, a in enumerate(refs):
        struct.pack_into("<H", out, t + 2 * n, moved[a] - (hdr + ds * 16))
    # (the program's other strings, each in its own bytes)
    for s, e in chan.strings(exe):
        ref = "%s:%04x" % (prog, s)
        if ref in by_ref:
            b = encode(by_ref[ref], newlines=False)
            if len(b) > e - s - 1:
                warn.append("%s: cut to the program's room (%d bytes)" % (ids[ref], e - s - 1))
                b = b[:e - s - 1]
            out[s:e] = b + bytes(e - s - len(b))
    vol.write(_path(cfg, prog), chan.patch_exe(bytes(out), prog, len(qdat)))
    for pname in cfg.get("console_programs", []):
        raw = vol.read(_path(cfg, pname))
        pout = bytearray(raw)
        for s, e in chan.console_strings(raw):
            ref = "%s:%04x" % (pname, s)
            if ref in by_ref:
                text = by_ref[ref]
                if mode == "pseudo":
                    # (the filler with the message's tokens kept)
                    _t, tokens = console_text(raw[s:e - 1])
                    text = text[:max(1, e - s - 1 - sum(len(t) for t in tokens))] + "".join(
                        "{X%d}" % (k + 1) for k in range(len(tokens)))
                b, cut = console_bytes(text, raw[s:e - 1], ids[ref])
                if cut:
                    warn.append("%s: cut to the program's room (%d bytes)" % (ids[ref], e - s - 1))
                pout[s:e] = b
        vol.write(_path(cfg, pname), bytes(pout))
    for w in warn:
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
