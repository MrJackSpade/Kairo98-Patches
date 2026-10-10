"""English for Panther Software's Lesser Mern (pc98tl/lmern.py): strings.json in, a patched image out.

Strings:

* "msg": a message's text (refs FILE:offset, the text between the message's controls) in a map's
  script (MDTnnn), an event's (game.json "event_files": EV2nn, LESS.EXE's) or the ending's
  ("ending_files": ED2nn, ENDG.EXE's): any length.  The English is written in the text's own bytes;
  what does not fit goes on elsewhere (a map's: at the script's end, 7Fh lo hi to it; the others: in
  the program's English segment, 7Ch lo hi), back after it (7Dh), the rest of its bytes skipped (7Eh).
  The window wraps between words and waits for a key when full; \\n starts a new line.
* "name": a map's speaker names (refs MDTnnn:name<n>), each put at the script's end and its entry in
  the names' table pointed at it.
* "engine": LESS.EXE's and ENDG.EXE's own strings (refs PROGRAM:offset in its data segment): the same
  as a message (in the program's English segment past its own bytes; `max_cells` the room of the menu
  or line a name or label sits in); and the menu that LM.COM and OP.COM show (refs LM.COM:offset), in
  its own bytes, padded with spaces.
* "opening": OPEN.EXE's messages (refs OPEN.EXE:offset): wrapped by the patcher to the width of the
  page the Japanese is shown on (`max_cells`), two letters to each of its gaiji (188 at most, a
  message's letters at most 376: past them it is cut and reported); \\n starts a new line.

A map's script with its English may take MDT_MAX bytes, a program's English segment 65520; a build
past either is refused and names it.  English is ASCII (drawn half-width by the patch's helpers);
another character is written in Shift-JIS when it has it (two bytes, full-width), else as `?` (and
always as `?` in a program's English segment, which the window reads a byte at a time).  A name the
program copies two bytes at a time is padded with a space to an even length.
"""
import json
import os
import re
import struct

from . import lmern
from .alice_sys2_tl import sha256

PREFIX = {"msg": "m", "name": "n", "engine": "e", "opening": "o"}
SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-",
         "…": "...", "♥": "<3", "~": "-"}
LINE = 52                       # the map window's line: 26 characters' bytes
GAIJI = 188                     # the opening's gaiji for a message
TEXT = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|\x20)+")
MARKS = "「」。、！？・"
ENDING = "ENDG.EXE"
COMS = ("LM.COM", "OP.COM")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def _path(cfg, name):
    return cfg["game_dir"] + "/" + name if cfg["game_dir"] else name


def decode(raw):
    return raw.decode("cp932", "replace").replace("\n", "\\n")


def encode(text, ascii_only=False):
    out = bytearray()
    for c in "".join(SUBST.get(c, c) for c in text):
        if c == "\n":
            out.append(0x0A)
        elif 0x20 <= ord(c) < 0x7C:
            out.append(ord(c))
        elif ascii_only:
            out.append(0x3F)
        else:
            try:
                b = c.encode("cp932")
            except UnicodeEncodeError:
                b = b"?"
            out += b if len(b) == 2 else b"?"
    return bytes(out)


def scripts(vol, cfg):
    cluster = vol.find(cfg["game_dir"])["cluster"] if cfg["game_dir"] else 0
    return sorted(e["name"] for e in vol.listdir(cluster) if not e["is_dir"] and re.match(r"MDT\d+$", e["name"]))


def names(d):
    """[(table entry's offset, the name's start, end past its 00)] of a script's speaker names."""
    t = struct.unpack_from("<H", d, 16)[0]
    if not t:
        return []
    n = struct.unpack_from("<H", d, t)[0]
    out = []
    for k in range(n):
        a = struct.unpack_from("<H", d, t + 2 + 2 * k)[0]
        out.append((t + 2 + 2 * k, a, d.index(0, a) + 1))
    return out


def texts(d, names_too=True, end=None):
    """[(start, end)] of a file's message texts: a run of characters (and spaces) that a control or the
    message's end follows, with kana or the script's punctuation in it (outside a script's names); and
    a string of other characters (魔法, ＯＮ) where it is one of a list of strings, the one before or
    after it taken."""
    inside = {a for _t, s, e in names(d) for a in range(s, e)} if names_too else set()
    out, maybe = [], []
    for m in TEXT.finditer(d, 0, end or len(d)):
        s, e = m.start(), m.end()
        while s < e and d[s] == 0x20:
            s += 1
        while e > s and d[e - 1] == 0x20:
            e -= 1
        if e - s < 4 or s in inside or e >= len(d) or d[e] >= 0x11 and d[e] != 0x20:
            continue
        t = d[s:e].decode("cp932", "replace")
        if "�" in t:
            continue
        if any("぀" <= c <= "ヿ" or c in MARKS for c in t):
            out.append((s, e))
        elif d[s - 1] == 0 and d[e] == 0 and " " not in t:
            maybe.append((s, e))
    taken = {s for s, _e in out} | {e for _s, e in out}
    grew = True
    while grew:
        grew = False
        for s, e in list(maybe):
            if s - 1 in taken or e + 1 in taken:
                out.append((s, e))
                maybe.remove((s, e))
                taken |= {s, e}
                grew = True
    return sorted(out)


def program_data(exe, name):
    """A program's data segment's bytes (LESS.EXE's to the script's room)."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    ds = lmern.data_segment(exe, name)
    nrel, rel_at = struct.unpack_from("<H", exe, 6)[0], struct.unpack_from("<H", exe, 24)[0]
    segs = {struct.unpack_from("<H", exe, hdr + struct.unpack_from("<H", exe, rel_at + 4 * k)[0]
                               + 16 * struct.unpack_from("<H", exe, rel_at + 4 * k + 2)[0])[0] for k in range(nrel)}
    nxt = min(s for s in segs if s > ds)
    base = hdr + ds * 16
    return exe[base:base + min(lmern.MDT_BASE if name == "LESS.EXE" else 0x10000, (nxt - ds) * 16)]


def _program_room(raw):
    """(max_cells, note) of one of a program's strings."""
    t = raw.decode("cp932", "replace")
    if any(c in t for c in "。！？」") or len(raw) >= 30:
        return LINE, "a message (the window wraps it); any length"
    return len(raw), ("a name or label: any length is drawn, but the menu, box or line it sits in "
                      "has room for its Japanese's %d letters" % len(raw))


def com_strings(com):
    """[(start, end)] of LM.COM's (OP.COM's) menu: its two strings."""
    return [(m.start(), m.end() - 1) for m in re.finditer(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc])+\x00", com)
            if len(m.group()) >= 9]


def _opening_width(page):
    return (80 - page[2]) // 2 * 2


def opening_lines(text, widths, chars):
    """The opening's English as lines for its pages: wrapped between words to each page's width,
    each an even number of letters (a space after an odd one); the lines shared among the pages as the
    Japanese's characters are."""
    lines = []
    width = min(widths)
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            while len(word) > width:
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:width])
                word = word[width:]
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line += " " + word
            else:
                lines.append(line)
                line = word
        lines.append(line)
    out, k = [], 0
    total = sum(chars)
    for n, c in enumerate(chars):
        take = len(lines) - k if n + 1 == len(chars) else max(1, round(len(lines) * c / total))
        out.append(lines[k:k + take] or [""])
        k += take
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
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
    for name in scripts(vol, cfg):
        d = vol.read(_path(cfg, name))
        for k, (_t, s, e) in enumerate(names(d)):
            add("name", decode(d[s:e - 1]), "%s:name%d" % (name, k + 1), 24,
                "a speaker's name, on the window's first line")
        for s, e in texts(d):
            add("msg", decode(d[s:e]), "%s:%04x" % (name, s), LINE)
    for name in cfg.get("event_files", []) + cfg.get("ending_files", []):
        d = vol.read(_path(cfg, name))
        for s, e in texts(d, names_too=False):
            add("msg", decode(d[s:e]), "%s:%04x" % (name, s), LINE)
    for prog in (cfg["program"], ENDING):
        data = program_data(vol.read(_path(cfg, prog)), prog)
        for s, e in texts(data, names_too=False):
            cells, note = _program_room(data[s:e])
            add("engine", decode(data[s:e]), "%s:%04x" % (prog, s), cells, note)
    op = vol.read(_path(cfg, cfg["opening"]))
    hdr = struct.unpack_from("<H", op, 8)[0] * 16
    for mm in lmern.open_messages(op):
        s, e = mm["text"]
        width = min(_opening_width(p) for p in mm["pages"])
        add("opening", decode(op[hdr + s + 1:hdr + e - 1]), "%s:%04x" % (cfg["opening"], s), width,
            "the opening: lines of up to %d letters (wrapped by the patcher), %d letters in all" % (width, 2 * GAIJI))
    for com in COMS:
        d = vol.read(_path(cfg, com))
        for s, e in com_strings(d):
            add("engine", decode(d[s:e]).strip("　"), "%s:%04x" % (com, s), e - s,
                "the menu run first: its own %d bytes, one a letter" % (e - s))
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


def _cut(b, n):
    """b's first bytes, at most n, not splitting a Shift-JIS character."""
    k = 0
    while k < len(b):
        w = 2 if b[k] >= 0x80 else 1
        if k + w > n:
            break
        k += w
    return b[:k]


def _even(b):
    return b + b" " if len(b) % 2 else b


def in_place(out, s, e, b, tail, tail_at, esc):
    """The English b in out[s:e] (the Japanese's bytes): itself and 7Eh filler where it fits, else its
    first part, esc and the offset (tail_at + where it goes on in tail), filler; the rest added to
    tail, 7Dh after it.  True where the room is too short to go on elsewhere (b cut to it)."""
    room = e - s
    if len(b) <= room:
        out[s:e] = b + b"\x7e" * (room - len(b))
        return False
    if room < 3:
        out[s:e] = _cut(b, room) + b"\x7e" * (room - len(_cut(b, room)))
        return True
    head = _cut(b, room - 3)
    out[s:e] = head + esc + struct.pack("<H", tail_at + len(tail)) + b"\x7e" * (room - 3 - len(head))
    tail += b[len(head):] + b"\x7d"
    return False


def build_script(d, by_ref, name, cut):
    """A map's script with its English (see the module's docstring)."""
    out = bytearray(d)
    tail = bytearray()
    for k, (t, _s, _e) in enumerate(names(d)):
        key = "%s:name%d" % (name, k + 1)
        if key in by_ref:
            at = len(d) + len(tail)
            tail += _even(encode(by_ref[key].replace("\n", " "))) + b"\x00"
            struct.pack_into("<H", out, t, at)
    for s, e in texts(d):
        key = "%s:%04x" % (name, s)
        if key in by_ref and in_place(out, s, e, encode(by_ref[key]), tail, lmern.MDT_BASE + len(d), b"\x7f"):
            cut.append((key, e - s))
    out += tail
    if len(out) > lmern.MDT_MAX:
        raise SystemExit("%s: %d bytes with its English, a script may take %d; shorten its strings" % (
            name, len(out), lmern.MDT_MAX))
    return bytes(out)


def _far(out, spans, name, by_ref, tail, cut):
    """The English of out's spans (refs name:offset) in their own bytes, going on in tail (7Ch)."""
    for s, e in spans:
        key = "%s:%04x" % (name, s)
        if key in by_ref:
            b = encode(by_ref[key])
            b = b[:e - s] + encode(by_ref[key], ascii_only=True)[len(b[:e - s].decode("cp932", "replace")):] \
                if len(b) > e - s else b
            if in_place(out, s, e, b, tail, 0, b"\x7c"):
                cut.append((key, e - s))


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    by_ref = {}
    for e in doc["strings"]:
        text = pseudo(e["id"], 2 * len(e["jp"]) + 8) if mode == "pseudo" else e["en"]
        if mode == "pseudo" and e["kind"] == "opening":
            text = text[:2 * GAIJI - 8 * text.count(" ")]
        if text:
            for r in e["refs"]:
                by_ref[r] = text
    cut, done = [], 0
    for name in scripts(vol, cfg):
        d = vol.read(_path(cfg, name))
        if any(r.startswith(name + ":") for r in by_ref):
            vol.write(_path(cfg, name), build_script(d, by_ref, name, cut))
            done += 1
    # (the programs' strings and their events' / the ending's, going on in the program's English segment)
    for prog, files in ((cfg["program"], cfg.get("event_files", [])), (ENDING, cfg.get("ending_files", []))):
        tail = bytearray()
        for name in files:
            d = bytearray(vol.read(_path(cfg, name)))
            _far(d, texts(bytes(d), names_too=False), name, by_ref, tail, cut)
            vol.write(_path(cfg, name), bytes(d))
        exe = bytearray(vol.read(_path(cfg, prog)))
        hdr = struct.unpack_from("<H", exe, 8)[0] * 16
        base = hdr + lmern.data_segment(bytes(exe), prog) * 16
        data = program_data(bytes(exe), prog)
        out = bytearray(data)
        _far(out, texts(data, names_too=False), prog, by_ref, tail, cut)
        exe[base:base + len(out)] = out
        vol.write(_path(cfg, prog), lmern.patch_less(bytes(exe), bytes(tail), prog))
    # (the opening: each message's lines, a list for each page)
    op = vol.read(_path(cfg, cfg["opening"]))
    english = {}
    for mm in lmern.open_messages(op):
        key = "%s:%04x" % (cfg["opening"], mm["text"][0])
        if key not in by_ref:
            continue
        pages = opening_lines(by_ref[key], [_opening_width(p) for p in mm["pages"]], _page_chars(op, mm))
        enc, letters = [], 0
        for lines in pages:
            row = []
            for t in lines:
                b = _even(encode(t, ascii_only=True))
                if letters + len(b) > 2 * GAIJI:
                    b = _even(b[:max(0, 2 * GAIJI - letters)])
                    cut.append((key, 2 * GAIJI))
                letters += len(b)
                row.append(b)
            enc.append(row)
        english[mm["text"][0]] = enc
    vol.write(_path(cfg, cfg["opening"]), lmern.patch_open(op, english))
    for com in COMS:
        d = bytearray(vol.read(_path(cfg, com)))
        for s, e in com_strings(bytes(d)):
            key = "%s:%04x" % (com, s)
            if key in by_ref:
                b = encode(by_ref[key].replace("\n", " "), ascii_only=True)
                if len(b) > e - s:
                    cut.append((key, e - s))
                b = b[:e - s]
                pad = (e - s - len(b)) // 2
                d[s:e] = b" " * pad + b + b" " * (e - s - len(b) - pad)
        vol.write(_path(cfg, com), lmern.patch_com(bytes(d), com))
    for key, n in sorted(set(cut)):
        print("warning: %s: cut to %d bytes" % (key, n))
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))


def _page_chars(op, mm):
    """The Japanese's characters on each of a message's pages."""
    hdr = struct.unpack_from("<H", op, 8)[0] * 16
    d = op[hdr:]
    return [sum(a[0] for _p, c, a in lmern.open_ops(d, s, e) if c in (0x07, 0x08)) for s, e, _c in mm["pages"]]
