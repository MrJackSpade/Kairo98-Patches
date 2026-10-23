"""English for Aypio's Sex (pc98tl/aypio.py): strings.json in, a patched disk out.

Strings:
* m (message): a message (01 C0h), any length: broken between words at 64 letters (the program breaks a
  line by itself at the window's edge), 3 lines a window under a speaker's name (4 without one), the rest
  in more windows (the message's call made again); \\n a new line; {N1}.. a name and {S1}.. a word put in
  (keep each where it belongs), {C7} a colour, {W100} a wait (kept).
* n (name): a speaker's name (T1): up to 16 letters.
* w (word): a word a message puts in (T0, {S1}..): up to 16 letters.
* p (page): a page of text (U2): broken between words at 64 letters; \\n a new line.
* c (choice): a menu's choice (W8): one line, max_cells letters.
* t (text): another text a script sets (01): one line.
* e (program): UK2.EXE's own messages, in place: max_cells letters.

English is ASCII, written in \\k (the program then draws bytes as themselves, half-width); a name or a word
put in goes in \\K (the program's own characters).  A build with English writes the DLB archives again
(the scripts with every address moved) and UK2.EXE's messages in place.
"""
import json
import os
import re
import unicodedata

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import aypio as A
from . import starpt as S
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "insert": "w", "page": "p", "choice": "c", "text": "t", "prog": "e"}
NOTE = {"msg": "a message: any length (broken between words, 3 lines a window under a speaker, more windows "
               "for the rest); \\n a new line; keep each {N1} (a name) and {S1} (a word) where it belongs",
        "name": "a speaker's name: up to 16 letters",
        "insert": "a word a message puts in ({S..}): up to 16 letters",
        "page": "a page of text: broken between words at 64 letters; \\n a new line",
        "choice": "a menu's choice: one line, max_cells letters",
        "text": "a text a script sets: one line",
        "prog": "the program's own message, in place: max_cells letters"}
ARCHIVES = ("DATALIB1.DLB", "DATALIB2.DLB", "DATALIB3.DLB", "DATALIB4.DLB")
WIDTH = 64
SLOT = 20                   # a name's or a word's bytes (the tables' 21-byte entries)
KIND = {"T0": "insert", "T1": "name", "U2": "page", "W8": "choice"}
TRAIL = re.compile(rb"(?:\\r|\\C\d|\\W\d+)*$")


def _path(cfg, name):
    return cfg["dir"] + "/" + name


def _program(vol, cfg):
    exe = vol.read(_path(cfg, cfg["engine"]))
    return exe, exe[int.from_bytes(exe[8:10], "little") * 16:]


JAPANESE = re.compile(r"[ぁ-ヶ一-鿿々]")


def units(sc, table):
    """[(string start, kind, the unit's bytes (start, end), speaker)] of a script's texts (with Japanese
    letters in them: the others are marks and pieces the program puts together)."""
    d, out = sc.d, []
    for s, e in sc.strings:
        at, cmd = sc.owner[s]
        b = d[s:e]
        if not A.visible(b):
            continue
        if cmd == "01":
            if d[at + 1] == 0xC0:
                pre, rest, who = A.speaker(b)
                if A.visible(rest):
                    out.append((s, "msg", (s + len(pre), e), who))
                continue
            # (the texts set in variable 20h: the others are the name entry's characters; \\0 a mark)
            if A.is_file(b) or d[at + 1] != 0x20 or re.fullmatch(rb"\\.", b):
                continue
            kind = "text"
        elif cmd in KIND:
            kind = KIND[cmd]
        else:
            continue
        m = TRAIL.search(b)
        jp = A.show(b[:m.start()], table)
        if not JAPANESE.search(jp) or (kind == "text" and len(jp) < 2):
            continue
        out.append((s, kind, (s, s + m.start()), False))
    return out


def scripts(vol, cfg):
    """[(archive, member, Script)]."""
    out = []
    for arc in ARCHIVES:
        p = _path(cfg, arc)
        if not vol.find(p):
            continue
        data = vol.read(p)
        for name, at, size in A.dlb(data):
            if name.lower().endswith(".mes"):
                out.append((arc, name, A.Script(data[at:at + size])))
    return out


def found(vol, cfg):
    """[(ref, kind, Japanese, max cells or None)]."""
    _exe, img = _program(vol, cfg)
    table = A.kana_table(img)
    out = []
    for arc, name, sc in scripts(vol, cfg):
        for s, kind, (a, b), _who in units(sc, table):
            jp = A.show(sc.d[a:b], table)
            room = {"name": 16, "insert": 16}.get(kind)
            if kind == "choice":
                room = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in jp)
            out.append(("%s:%s:%x" % (arc[7], name, s), kind, jp, room))
    for s, e in S.program_strings(bytes(img)):
        out.append(("E:%05x" % s, "prog", S.show(img[s:e]), e - s))
    for name in COMS:
        if vol.find(_path(cfg, name)):
            com = vol.read(_path(cfg, name))
            for s, e in com_strings(com):
                out.append(("%s:%04x" % (name, s), "prog", S.show(com[s:e]), e - s))
    return out


COMS = ("NAX.COM", "AYPIO.COM")     # the sound driver's and the floppy version's launcher's DOS messages
COM_STRING = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x1b\x20-\x23\x25-\x7e\r\n])+(?=[$\0])")


def com_strings(com):
    """[(start, end)] of a COM program's Japanese messages (up to a $ or a 0)."""
    out = []
    for m in COM_STRING.finditer(com):
        t = com[m.start():m.end()]
        if len(re.findall(rb"\x82[\x9f-\xf1]|\x83[\x40-\x96]", t)) >= 2:
            out.append((m.start(), m.end()))
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


def _cols(t):
    t = re.sub(r"\{[^{}]*\}", "", t)
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


def _english(sc, s, kind, span, who, text, ident, warn):
    """[bytes or ("addr", old)] for the whole string at s."""
    d = sc.d
    a, b = span
    pre, post = d[s:a], d[b:sc_end(sc, s)]
    if kind in ("name", "insert"):
        enc = A.encode(A.lines(text.replace("\n", " "), 9999))
        if len(enc) > SLOT:
            warn.append("%s: %d bytes, room for %d" % (ident, len(enc), SLOT))
            enc = enc[:SLOT - 2] + b"\\K" if enc.endswith(b"\\K") else enc[:SLOT]
        return [pre + enc + post]
    if kind in ("choice", "text"):
        return [pre + A.encode(A.lines(text.replace("\n", " "), 9999)) + post]
    ls = A.lines(text, WIDTH)
    if kind == "page":
        return [pre + A.encode(ls) + post]
    rows = 3 if who else 4
    pages = [ls[k:k + rows] for k in range(0, len(ls), rows)] or [[]]
    at, _cmd = sc.owner[s]
    nxt = sc.next_command(at)
    call = None
    if nxt is not None and nxt[1] == "J1":
        call = sc.w(nxt[0] + 2)
    if len(pages) > 1 and call is None:
        warn.append("%s: %d lines, room for %d (no call after it to show a second window)" % (
            ident, len(ls), rows))
        pages = [ls[:rows]]
    parts = [pre + A.encode(pages[0])]
    for page in pages[1:]:
        # (the window so far: shown by the message's call, then the message set again)
        parts += [b"\0J1", ("addr", call), b"\x01\xc0\x87\x60" + pre + A.encode(page)]
    parts[-1] = parts[-1] + post
    return parts


def sc_end(sc, s):
    return dict(sc.strings)[s]


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    by_ref = {}
    for e in doc["strings"]:
        text = pseudo(e["id"], _cols(e["jp"])) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            by_ref[r] = (e, text)
    if not any(t for _e, t in by_ref.values()):
        img.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    warn = []
    sizes, calls = {}, {}
    table = A.kana_table(_program(vol, cfg)[1])
    for arc in ARCHIVES:
        p = _path(cfg, arc)
        if not vol.find(p):
            continue
        data = vol.read(p)
        members = {}
        for name, at, size in A.dlb(data):
            if not name.lower().endswith(".mes"):
                continue
            sc = A.Script(data[at:at + size])
            new = {}
            for s, kind, span, who in units(sc, table):
                e, text = by_ref.get("%s:%s:%x" % (arc[7], name, s), (None, ""))
                if text:
                    new[s] = _english(sc, s, kind, span, who, text, e["id"], warn)
            try:
                out = A.rebuild(sc, new) if new else sc.d
            except A.ScriptError as err:
                raise SystemExit("%s: %s; shorten its English" % (name, err))
            if new:
                members[name] = out
            sizes[name.lower()] = len(out)
            calls[name.lower()] = {sc.d[s2:e2].decode("latin-1").lower().rstrip("1")
                                   for s2, e2 in sc.strings if re.fullmatch(rb"[0-9A-Za-z_\-]+\.mes1?", sc.d[s2:e2], re.I)}
        if members:
            vol.write(p, A.dlb_bytes(data, members))
    # (a script runs on top of the ones that called it: the deepest chain must fit the program's room)
    def chain(n, seen=()):
        if n in seen or n not in sizes:
            return 0, ()
        best = max([chain(c, seen + (n,)) for c in calls.get(n, ())] or [(0, ())])
        return sizes[n] + best[0], (n,) + best[1]
    total, path = max(chain(n) for n in sizes)
    if total > A.LIMIT:
        raise SystemExit("the scripts %s take %d bytes together with their English, the program's room is %d; "
                         "shorten their English" % (" > ".join(path), total, A.LIMIT))
    exe, image = _program(vol, cfg)
    exe = bytearray(exe)
    hdr = int.from_bytes(exe[8:10], "little") * 16
    for s, end in S.program_strings(bytes(image)):
        e, text = by_ref.get("E:%05x" % s, (None, ""))
        if not text:
            continue
        b = A.ascii_text(text).replace("\n", " ").encode("ascii")
        if len(b) > end - s:
            warn.append("%s: %d letters, room for %d" % (e["id"], len(b), end - s))
            b = b[:end - s]
        exe[hdr + s:hdr + end] = b.ljust(end - s, b"\0")
    vol.write(_path(cfg, cfg["engine"]), bytes(exe))
    for name in COMS:
        p = _path(cfg, name)
        if not vol.find(p):
            continue
        com = bytearray(vol.read(p))
        changed = False
        for s, end in com_strings(bytes(com)):
            e, text = by_ref.get("%s:%04x" % (name, s), (None, ""))
            if not text:
                continue
            b = b"".join(b"\x1b" if part == "{ESC}" else
                         A.ascii_text(part).replace("$", "S").encode("ascii").replace(b"\n", b"\r\n")
                         for part in re.split(r"(\{ESC\})", text))
            if len(b) > end - s:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(b), end - s))
                b = b[:end - s]
            com[s:end] = b.ljust(end - s, b" ")
            changed = True
        if changed:
            vol.write(p, bytes(com))
    vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
