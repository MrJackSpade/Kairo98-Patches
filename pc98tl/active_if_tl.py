"""English for Active's "if" (pc98tl/active_if.py): strings.json in, a patched image out.

Strings (refs SCRIPT:offset of the text in the script; the program's own strings MAIN.EXE:offset in
its data; the scenarios' titles TITLE.DAT's folder and line):

* "msg": a message: the texts one after another up to the one with the key wait (`\\p`), shown as
  lines (`\\n` between the texts, each a line in the window).  Any length: the program counts its
  window's columns in cells (a Shift-JIS character, or a pair of ASCII letters, each letter
  half-width) and breaks the line at the window's edge; the patcher breaks the English between words
  by filling the line with spaces to that width (`max_cells`, in letters: the window's width, less a
  speaker's name the program puts before the message and under which it starts every line), puts the
  message in one text and pages as the program does (it waits for a key and clears the window past
  its lines).  `\\n` in the English forces a new line.  The controls are `{p}`-style tokens (`{v0A}` a
  pause and its length, `{e01}`, `{f}`); the key wait the message ends with is put back by the patcher.
* "name": a speaker's name (if's op 72h; its `「` included): `max_cells` the Japanese's, in letters.
* "item": a choice's item: `max_cells` the choice's widest Japanese item; past it reported.
* "title": a scenario's title (TITLE.DAT's first line the menu's, its second the message's): `max_cells`
  the Japanese's; past it reported.
* "label": a string of the program's: in place, `max_cells` its room in bytes; past it cut and
  reported.  `%s`-style marks and a menu item's leading `*0` are kept.

English is ASCII (two letters a cell, each drawn half-width by the patched program); another character
is written full-width in Shift-JIS when it has one, else `?`.  A text starts with a byte no op has (a
space is put before a letter that is one).  A changed script is laid out anew with every pointer
moved; the program reads at most 32768 bytes of a script, so a longer build is refused and names the
script's strings (in pseudo mode the filler is cut).
"""
import json
import os
import re

from . import active_if as A, exepack
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "item": "i", "title": "t", "label": "l"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "\\": "/", "{": "(",
         "}": ")"}
ROOM = 0x8000                    # the program's script buffer
TOKEN = re.compile(r"\{([a-z\\])([0-9A-F]{2})?\}")
PROG_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                      rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*\x00")
FORMAT = re.compile(r"%[0-9]*[sdux]|^\*[0-9]")
# a string of the program's that says something (kana, kanji or full-width letters, not only frames)
WORDY = re.compile(r"[ぁ-ヿ一-鿿Ａ-ｚ]")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def _program(raw):
    exe = exepack.unpack(raw) if exepack.is_packed(raw) else raw
    return exe, int.from_bytes(exe[8:10], "little") * 16


def cells(text):
    """Half-width cells (a letter one, another character two), the widest line."""
    t = TOKEN.sub("", text)
    return max((sum(1 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 2 for c in line)
                for line in t.split("\n")), default=0)


def show(b):
    """A text's bytes as strings.json shows them: Shift-JIS, the controls as tokens."""
    out, i = [], 0
    while i < len(b):
        c = b[i]
        if c == 0x5C and i + 1 < len(b):
            k = b[i + 1]
            if k in A.ESC_ARG and i + 2 < len(b):
                out.append("{%c%02X}" % (k, b[i + 2]))
                i += 3
            else:
                out.append("{%c}" % k)
                i += 2
            continue
        n = 2 if c >= 0x80 and not 0xA0 <= c <= 0xDF else 1
        out.append(b[i:i + n].decode("cp932", "replace"))
        i += n
    return "".join(out)


def _sjis(ch):
    try:
        return ch.encode("cp932")
    except UnicodeEncodeError:
        return b"?"


def _units(text):
    """[(kind, value)]: "a" an ASCII letter, "j" a Shift-JIS character, "t" a control's bytes."""
    out, i = [], 0
    while i < len(text):
        m = TOKEN.match(text, i)
        if m:
            b = b"\\" + m.group(1).encode()
            if m.group(2):
                b += bytes([int(m.group(2), 16)])
            out.append(("t", b))
            i = m.end()
            continue
        for ch in SUBST.get(text[i], text[i]):
            if " " <= ch <= "~":
                out.append(("a", ch.encode()))
            else:
                out.append(("j", _sjis(ch)))
        i += 1
    return out


def encode(text, width=None):
    """The English as the program's bytes: ASCII letters two a cell, a Shift-JIS character and a
    control on a cell's start (a space before them after an odd letter), the lines filled with spaces
    to width (in letters), an even length."""
    out = bytearray()
    lines = text.split("\n")
    for k, line in enumerate(lines):
        col = 0
        odd = False
        for kind, b in _units(line):
            if kind == "a":
                out += b
                col += 1
                odd = not odd
                continue
            if odd:
                out += b" "
                col += 1
                odd = False
            out += b
            if kind == "j":
                col += 2
        if odd:
            out += b" "
            col += 1
        if width and k < len(lines) - 1:
            used = col % width
            if used or not col:
                out += b" " * (width - used + (width - used) % 2)
    if len(out) & 1:
        out += b" "
    return bytes(out)


def wrap(text, width):
    """The English with new lines between words at width letters."""
    out = []
    for k, para in enumerate(text.split("\n")):
        if k:
            out.append("\n")
        col = 0
        for j, word in enumerate(para.split(" ")):
            w = cells(word) + (cells(word) & 1)
            if j:
                if col + 1 + w > width and col:
                    out.append("\n")
                    col = 0
                else:
                    out.append(" ")
                    col += 1
            out.append(word)
            col += w
            while col > width:
                col -= width
    return "".join(out)


def scripts(vol, gd):
    return sorted(n for n, e in vol.walk() if n.upper().startswith(gd.upper() + "/")
                  and n.upper().endswith(".ADV") and not e["is_dir"])


def titles(vol, gd):
    return sorted(n for n, e in vol.walk() if n.upper().startswith(gd.upper() + "/")
                  and n.upper().endswith("/TITLE.DAT"))


def visible(b):
    return bool(re.sub(r"\{[^}]*\}", "", show(b)).strip("　 "))


def messages(d):
    """[(start, end, jp, has the key wait, the speaker's name's start or None)]: the texts one after
    another (no op between) up to the one ending with the key wait; a text with nothing to show (a new
    window, a pause) stays as it is."""
    _p, ev = A.walk(d)
    out, run, name = [], [], None

    def flush():
        if run:
            parts, jp = [d[s:e - 1] for s, e in run], ""
            for k, b in enumerate(parts):
                t = show(b)
                if k == len(parts) - 1 and t.endswith("{p}"):
                    t = t[:-3]
                jp += t if not jp or jp.endswith("{\\}") else "\n" + t
            out.append((run[0][0], run[-1][1], jp, show(parts[-1]).endswith("{p}"), name))
            run.clear()
    for e in ev:
        if e[0] == "name":
            flush()
            name = e[1] if visible(d[e[1]:e[2] - 1]) or d[e[1]:e[2] - 1].strip(b"\\") else None
            continue
        if e[0] != "text":
            flush()
            continue
        s, en = e[1], e[2]
        if not visible(d[s:en - 1]):
            flush()
            continue
        if run and run[-1][1] != s:
            flush()
        run.append((s, en))
        if show(d[s:en - 1]).endswith("{p}"):
            flush()
    flush()
    return out


def _name_text(d, s):
    b = d[s:d.index(0, s)]
    return show(b[:-2] if b.endswith(b"\\\\") else b)


def prog_strings(exe, hdr):
    img = exe[hdr:]
    out = []
    for m in PROG_STR.finditer(img, A.data_start(img)):
        txt = m.group()[:-1].decode("cp932", "replace")
        if WORDY.search(txt):
            out.append((hdr + m.start(), hdr + m.end() - 1))
    return out


def game_window(exe, hdr, vol, gd):
    """{script: {a text's start: the window's width in cells there}}: a script starts with the window
    of the scripts that start it (op 74h, a script in the same folder), one no script starts with the
    program's first; op 6Fh sets it.  A script started with two widths takes the narrower."""
    first, _h = A.window(exe[hdr:])
    walks = {n: A.walk(vol.read(n))[1] for n in scripts(vol, gd)}
    datas = {n: vol.read(n) for n in walks}
    starts = {}
    for n, ev in walks.items():
        for e in ev:
            if e[0] == "op" and e[2] == 0x74:
                d = datas[n]
                name = d[e[1] + 1:d.index(0, e[1] + 1)].decode("cp932", "replace").split(":")[-1]
                t = n.rsplit("/", 1)[0] + "/" + name.upper()
                starts.setdefault(n, []).append((e[1], t))
    targets = {t for v in starts.values() for _p, t in v}
    entry = {n: first for n in walks if n.upper() not in targets}
    todo = list(entry)
    while todo:
        n = todo.pop()
        w = entry[n]
        for e in walks[n]:
            if e[0] == "window":
                w = e[1]
            elif e[0] == "op" and e[2] == 0x74:
                for p, t in starts.get(n, []):
                    if p == e[1]:
                        t = next((x for x in walks if x.upper() == t), None)
                        if t and (t not in entry or w < entry[t]):
                            entry[t] = w
                            todo.append(t)
    out = {}
    for n, ev in walks.items():
        w = entry.get(n, first)
        out[n] = {}
        for e in ev:
            if e[0] == "window":
                w = e[1]
            elif e[0] == "text":
                out[n][e[1]] = w
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    gd = cfg["game_dir"]
    exe, hdr = _program(vol.read(gd + "/" + cfg["program"]))
    wins = game_window(exe, hdr, vol, gd)
    merged, order = {}, []

    def add(kind, jp, ref, cells_, note=None):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], cells_)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells_}
        if note:
            merged[key]["note"] = note
        order.append(key)
    for s, e in prog_strings(exe, hdr):
        add("label", exe[s:e].decode("cp932", "replace"), "%s:%05x" % (cfg["program"], s - hdr), e - s,
            "a string of the program's (a menu, a prompt): its room in bytes (a letter one, a full-width "
            "character two); %s-style marks and a leading *0 kept")
    for t in titles(vol, gd):
        lines = vol.read(t).decode("cp932", "replace").split("\r\n")
        rel = t[len(gd) + 1:]
        for k in (0, 1):
            if k < len(lines) and lines[k].strip():
                add("title", lines[k], "%s:%d" % (rel, k), cells(lines[k]),
                    "a scenario's title: the first line the scenario menu's, the second the message's")
    for n in scripts(vol, gd):
        d = vol.read(n)
        rel = n[len(gd) + 1:]
        _p, ev = A.walk(d)
        blocks = {}
        for e in ev:
            if e[0] == "item":
                blocks.setdefault(e[3], []).append(e)
        for e in ev:
            if e[0] == "name" and visible(d[e[1]:e[2] - 1]):
                jp = _name_text(d, e[1])
                add("name", jp, "%s:%04x" % (rel, e[1]), cells(jp), "a speaker's name, the message after it "
                    "on its line (the program starts the message's other lines under its end)")
            elif e[0] == "item":
                room = max(cells(show(d[x[1]:x[2] - 1])) for x in blocks[e[3]])
                add("item", show(d[e[1]:e[2] - 1]), "%s:%04x" % (rel, e[1]), room,
                    "a choice's item: one line in its box (the choice's widest Japanese item)")
        for s, e, jp, _wait, name in messages(d):
            indent = cells(_name_text(d, name)) if name is not None else 0
            add("msg", jp, "%s:%04x" % (rel, s), 2 * wins[n][s] - indent)
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
    marks = TOKEN.findall(e["jp"])
    keep = "".join("{%s%s}" % m for m in marks if m[0] not in "v")
    if e["kind"] == "label":
        fm = FORMAT.findall(e["jp"])
        return (" ".join(fm) + " " if fm else "") + pseudo(e["id"], e["max_cells"], 1.0)[:max(
            1, e["max_cells"] - sum(len(m) + 1 for m in fm))]
    if e["kind"] in ("item", "title", "name"):
        return pseudo(e["id"], e["max_cells"], 1.0)[:max(2, e["max_cells"])]
    return keep + pseudo(e["id"], cells(e["jp"]))


def _write(img, path, data):
    """A file written back; a full disk's volume grown (DiskImage.grow_volume) once, then refused."""
    try:
        img.volumes[0].write(path, data)
    except IOError:
        if not img.grow_volume(0):
            raise SystemExit("the disk is full: %s does not fit (%d bytes); shorten its strings" % (path, len(data)))
        try:
            img.volumes[0].write(path, data)
        except IOError:
            raise SystemExit("the disk is full even grown: %s does not fit (%d bytes); shorten its strings"
                             % (path, len(data)))


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    gd = cfg["game_dir"]
    prog_path = gd + "/" + cfg["program"]
    exe, hdr = _program(vol.read(prog_path))
    wins = game_window(exe, hdr, vol, gd)
    by_ref, ids, rooms = {}, {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            rooms[r] = e["max_cells"]
            if text:
                by_ref[r] = text
    warn = []
    prog = bytearray(exe)
    for s, e in prog_strings(exe, hdr):
        ref = "%s:%05x" % (cfg["program"], s - hdr)
        en = by_ref.get(ref)
        if en is None:
            continue
        b = encode(en)
        if len(b) > e - s:
            warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), e - s))
            b = b[:(e - s) & ~1]
        prog[s:e] = b.ljust(e - s, b"\0")
    changed = bytes(prog) != exe
    for t in titles(vol, gd):
        rel = t[len(gd) + 1:]
        lines = vol.read(t).split(b"\r\n")
        put = False
        for k in (0, 1):
            en = by_ref.get("%s:%d" % (rel, k))
            if en is not None and k < len(lines):
                if cells(en) > rooms["%s:%d" % (rel, k)]:
                    warn.append("%s: %d cells, past its room (%d)" % (ids["%s:%d" % (rel, k)], cells(en),
                                                                      rooms["%s:%d" % (rel, k)]))
                lines[k] = encode(en)
                put = True
        if put:
            _write(img, t, b"\r\n".join(lines))
            changed = True
    rebuilt = 0
    for n in scripts(vol, gd):
        d = vol.read(n)
        rel = n[len(gd) + 1:]
        _p, ev = A.walk(d)

        def build(ratio):
            new, names = {}, {}
            for e in ev:
                if e[0] == "name":
                    ref = "%s:%04x" % (rel, e[1])
                    en = by_ref.get(ref)
                    if en is not None:
                        en = en[:max(2, int(len(en) * ratio))] if ratio < 1 else en
                        names[e[1]] = encode(en)
                        new[e[1]] = (e[2], names[e[1]] + b"\\\\\0")
                elif e[0] == "item":
                    ref = "%s:%04x" % (rel, e[1])
                    en = by_ref.get(ref)
                    if en is not None:
                        if cells(en) > rooms[ref]:
                            warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
                        new[e[1]] = (e[2], encode(en) + b"\0")
            for s, e, jp, wait, name in messages(d):
                ref = "%s:%04x" % (rel, s)
                en = by_ref.get(ref)
                if en is None:
                    continue
                if ratio < 1:
                    en = en[:max(4, int(len(en) * ratio))]
                if name is None:
                    indent = 0
                elif name in names:
                    indent = len(names[name])
                else:
                    indent = cells(_name_text(d, name))
                w = 2 * wins[n][s] - indent
                b = encode(wrap(en, w), w)
                if b[:1] and b[0] in A.FMT:
                    b = b" " + b
                    if len(b) & 1:
                        b += b" "
                new[s] = (e, b + (b"\\p" if wait else b"") + b"\0")
            return new, A.rebuild(d, new) if new else d
        new, out = build(1.0)
        if len(out) > ROOM:
            if mode != "pseudo":
                raise SystemExit("%s: %d bytes with its English, the program reads %d; shorten these strings: %s"
                                 % (rel, len(out), ROOM, ", ".join(sorted({ids[r] for r in by_ref
                                                                           if r.startswith(rel + ":")}))))
            ratio = 1.0
            while len(out) > ROOM:
                ratio *= 0.9
                new, out = build(ratio)
            warn.append("%s: the filler was cut to %d%% to fit the program's %d bytes" % (rel, int(ratio * 100),
                                                                                         ROOM))
        if new:
            _write(img, n, out)
            rebuilt += 1
    if changed or rebuilt:
        _write(img, prog_path, A.patch_program(bytes(prog)))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), rebuilt))
