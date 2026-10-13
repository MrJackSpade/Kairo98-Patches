"""English for Cal (pc98tl/cal.py, pc98tl/ados.py): strings.json in, patched disks out.

Strings:
* m (message): a text line's text (after its colour, speaker and indent codes).  Any length: broken
  between words at the window's 70 cells (from the indent after a speaker's name, 16, or the left
  edge), \\n a new line; a message longer than the window's 4 rows is ended and continued after a
  click.  {c0}-{c7} a colour, {A}-{Z} a name the game puts in (the player's name, a speaker's): keep them.
* c (choice): an option of a choice menu: one line, up to 78 letters (its record holds 80 bytes).
* n (name): a speaker's name (shown before their lines): up to 16 letters.

The scripts are read from disk A and written to disk B (where there is room), the program patched to
read them there; a script that outgrows the buffer (24 sectors) is split.  ASCII letters only: anything
else is written as ?.
"""
import json
import os
import re

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .ados import AdosDisk
from . import cal as C
from .text import pseudo

PREFIX = {"msg": "m", "choice": "c", "name": "n", "program": "p", "prompt": "k"}
WIDTH = 70
ROWS = 4
INDENT = 16
NAME_MAX = 16
CHOICE_MAX = 78
NOTE = {"msg": "a message: any length, broken between words at the window's width, paged after 4 rows; "
               "\\n a new line; {c0}-{c7} a colour and {A}-{Z} a name put in by the game: keep them",
        "choice": "a choice menu's option: one line, up to 78 letters",
        "name": "a speaker's name, shown before their lines: up to 16 letters",
        "program": "a string of the program's (a menu, a chapter's name, the name prompt, the music test, the "
                   "credits): written in place, two letters to a full-width cell: max_cells letters",
        "prompt": "the system's disk prompt: {1} and {2} are the disk's and the drive's letters, put in by "
                  "the system; up to 10 letters before {1}, 18 between, 18 after"}


def _disks(cfg, src):
    base = os.path.dirname(src)
    return [AdosDisk(src)] + [AdosDisk(os.path.join(base, n)) for n in cfg.get("disks", [])]


def units(s):
    """[(kind, ref place, item, start, end, prefix)] of a script's text: lines' bodies, choices' items,
    names."""
    out = []
    for kind, a, e in C.tokens(s):
        if kind == "text":
            pre, body, _suf = C.text_parts(s, a, e)
            if C.has_japanese(body):
                out.append(("msg", a, 0, a + len(pre), a + len(pre) + len(body), pre))
        elif kind == "choice":
            for k, (x, y) in enumerate(C.choice_items(s, a, e)):
                if C.has_japanese(s[x:y]):
                    out.append(("choice", a, k, x, y, b""))
        elif kind == "name":
            x, y = C.name_text(s, a, e)
            if C.has_japanese(s[x:y]):
                out.append(("name", a, 0, x, y, b""))
    return out


def _ref(n, a, k):
    return "S%02X:%04x:%d" % (n, a, k)


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    disk = _disks(cfg, src)[0]
    merged, order = {}, []
    for n in cfg["scripts"]:
        s = disk.read(n)
        for kind, a, k, x, y, _pre in units(s):
            jp = C.show(s[x:y])
            key = (kind, jp)
            ref = _ref(n, a, k)
            if key in merged:
                merged[key]["refs"].append(ref)
                continue
            room = {"msg": WIDTH * ROWS, "choice": CHOICE_MAX, "name": NAME_MAX}[kind]
            merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room, "note": NOTE[kind]}
            order.append(key)
    prog = disk.read(cfg["program"])
    for x, y in C.program_strings(prog):
        if y - x > 64:
            continue
        jp = prog[x:y].decode("cp932")
        key = ("program", jp)
        if key in merged:
            merged[key]["refs"].append("P:%04x" % x)
            continue
        merged[key] = {"kind": "program", "jp": jp, "en": "", "refs": ["P:%04x" % x], "max_cells": y - x,
                       "note": NOTE["program"]}
        order.append(key)
    kern = disk.read(cfg["kernel"])
    k = kern.find(C.DISK_PROMPT)
    if k >= 0:
        jp = (C.DISK_PROMPT[:10].decode("cp932") + "{1}" + C.DISK_PROMPT[12:30].decode("cp932") + "{2}" +
              C.DISK_PROMPT[32:].decode("cp932"))
        merged[("prompt", jp)] = {"kind": "prompt", "jp": jp, "en": "", "refs": ["K:%04x" % k], "max_cells": 46,
                                  "note": NOTE["prompt"]}
        order.append(("prompt", jp))
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


# ---- English ---------------------------------------------------------------------------------------
TOKEN = re.compile(r"\{[A-Z]\}|\{c[0-7]\}")


def _visible(word):
    return len(TOKEN.sub("", word))


def wrap(text, width, first):
    """[line] of the English broken between words; the first line has `first` cells."""
    out = []
    room = first
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = word if not line else line + " " + word
            if _visible(cand) <= room or not line:
                line = cand
                while _visible(line) > room:
                    out.append(line[:room])
                    line = line[room:]
                    room = width
                continue
            out.append(line)
            line, room = word, width
        out.append(line)
        room = width
    return out


def message(pre, en, suffix, rows_before):
    """The bytes of a text line with English: its codes, the English broken into lines, a page ended
    and continued (\\$, click, clear, the colour and indent again) where the window fills."""
    indent = INDENT if b"#" in pre else 0
    lines = wrap(en, WIDTH - indent, WIDTH - indent)
    cont = bytes(c for c in pre if 0x30 <= c <= 0x37) + (b"#" if indent else b"")
    out = bytearray(pre)
    row = rows_before
    for k, line in enumerate(lines):
        if k and row >= ROWS:
            out += b"\\$\x0a\x1d" + cont
            row = 0
        elif k:
            out += b"\\"
        out += C.encode_chars(line)
        row += 1
    out += suffix
    return bytes(out), row


def _rows_japanese(pre, body):
    indent = INDENT if b"#" in pre else 0
    cells, k = 0, 0
    while k < len(body):
        if body[k] >= 0x80:
            cells += 2
            k += 2
        else:
            k += 1
    return max(1, -(-cells // (WIDTH - indent)))


def _pseudo(e):
    if e["kind"] == "prompt":
        return "<k1> {1} dog {2} ok"
    if e["kind"] == "program":
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"]]
    jp = re.sub(r"\{[^}]*\}", "", e["jp"]).replace("\n", "")
    toks = "".join(TOKEN.findall(e["jp"]))
    if e["kind"] == "msg":
        return toks + pseudo(e["id"], 2 * len(jp))
    if e["kind"] == "name":
        return pseudo(e["id"], 2 * len(jp), 1.0)[:NAME_MAX]
    return pseudo(e["id"], 2 * len(jp))[:CHOICE_MAX]


def build_script(s, n, by_ref, ids, warn):
    """The script with its English."""
    out = bytearray()
    rows = 0
    for kind, a, e in C.tokens(s):
        if kind == "cmd" and s[a] == 0x1D:
            rows = 0
        if kind == "text":
            pre, body, suf = C.text_parts(s, a, e)
            en = by_ref.get(_ref(n, a, 0))
            if en is None or not C.has_japanese(body):
                out += s[a:e]
                rows += _rows_japanese(pre, body)
                continue
            b, rows = message(pre, en, suf, rows)
            out += b
            continue
        if kind == "choice":
            items = C.choice_items(s, a, e)
            seg = bytearray(s[a:a + 2])
            for k, (x, y) in enumerate(items):
                en = by_ref.get(_ref(n, a, k))
                if en is None:
                    seg += s[x:y]
                else:
                    b = C.encode_chars(" ".join(en.split("\n")))
                    if len(b) % 2:
                        b += bytes([C.MAP[" "]])
                    if len(b) > CHOICE_MAX:
                        warn.append("%s: %d letters, an option holds %d" % (ids[_ref(n, a, k)]["id"], len(b),
                                                                             CHOICE_MAX))
                        b = b[:CHOICE_MAX]
                    seg += b
                seg += b"\0" if k < len(items) - 1 or s[y:y + 1] == b"\0" else b""
            out += seg
            continue
        if kind == "name":
            x, y = C.name_text(s, a, e)
            en = by_ref.get(_ref(n, a, 0))
            if en is None:
                out += s[a:e]
            else:
                b = C.encode_chars(" ".join(en.split("\n")))
                if len(b) > NAME_MAX:
                    warn.append("%s: %d letters, a name holds %d" % (ids[_ref(n, a, 0)]["id"], len(b), NAME_MAX))
                    b = b[:NAME_MAX]
                out += s[a:x] + b + s[y:e]
            continue
        out += s[a:e]
    return bytes(out)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    disks = _disks(cfg, src)
    a, b = disks[0], disks[1]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    warn = []
    built = {n: build_script(a.read(n), n, by_ref, ids, warn) for n in cfg["scripts"]}
    if any(built[n] != a.read(n) for n in built):
        limit = C.buffer_sectors(None) * 1024
        spare = [n for n in range(0x10, 0x100) if n not in built and not a.entry(n) and not b.entry(n)]
        out = {}
        for n, data in built.items():
            parts = C.split(n, data, limit, spare)
            out.update(parts)
        for n, data in sorted(out.items()):
            b.write(n, data)
        prog = bytearray(a.read(cfg["program"]))
        for x, y in C.program_strings(bytes(prog)):
            en = by_ref.get("P:%04x" % x)
            if en is None or y - x > 64:
                continue
            one = " ".join(en.split("\n"))
            if len(C.encode_chars(one)) > y - x:
                warn.append("%s: %d letters, room for %d" % (ids["P:%04x" % x]["id"], len(C.encode_chars(one)),
                                                             y - x))
            prog[x:y] = C.encode_pairs(one, y - x)
        kern = bytearray(a.read(cfg["kernel"]))
        k = kern.find(C.DISK_PROMPT)
        en = by_ref.get("K:%04x" % k) if k >= 0 else None
        if en is not None:
            parts = (en.replace("\n", " ").split("{1}", 1) + [""])[:2]
            mid = (parts[1].split("{2}", 1) + [""])[:2]
            segs = [(parts[0], 10), (mid[0], 18), (mid[1], 18)]
            for text, room in segs:
                if len(C.encode_chars(text)) > room:
                    warn.append("%s: a part of %d letters, room for %d" % (ids["K:%04x" % k]["id"],
                                                                         len(C.encode_chars(text)), room))
            out = C.encode_pairs(segs[0][0], 10) + C.DISK_PROMPT[10:12] + C.encode_pairs(segs[1][0], 18) + \
                C.DISK_PROMPT[30:32] + C.encode_pairs(segs[2][0], 18)
            kern[k:k + len(C.DISK_PROMPT)] = out
        a.write(cfg["kernel"], bytes(kern))
        prog, addr = C.patch_program(bytes(prog))
        a.write(cfg["program"], prog)
        a.write(cfg["kernel"], C.patch_kernel(a.read(cfg["kernel"]), addr))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    a.save(dst)
    stem, ext = os.path.splitext(dst)
    for disk, name in zip(disks[1:], cfg.get("disks", [])):
        extra = "%s - %s" % (stem, name)
        disk.save(extra)
        print("patched %s" % extra)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
