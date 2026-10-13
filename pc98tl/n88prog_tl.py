"""English for a game written in N88-BASIC(86) (pc98tl/n88prog.py: Starcraft's
Mystery House): strings.json in, a patched disk out.

Strings:
* m (message): text a PRINT statement prints.  The English is broken
  between words at the text layer's width less its last column (a
  character there moves the cursor on, and the line's own new line would
  leave a blank row): each further line becomes a PRINT
  statement of its own put after the literal (":PRINT ..."), so whatever the
  statement printed after it follows the last line.  A message that starts
  after something else on its line (PRINT N$;"...") starts its first line
  at the widest that can stand before it: the longest English word (the
  player's nouns and verbs, which the game prints so) where a variable does,
  the column the line's own literals reach where they do.  A message longer
  than the window (game.json "window_lines", its rows less the line before
  the message and the cursor's) waits for a key after each windowful
  (":Z9$=INPUT$(1)", the key wait the game uses itself, on a variable of
  its own).
* l (line): a row of a page the game lays out itself (the title screen, the
  instructions): a PRINT right after a LOCATE.  Its room is the rest of its
  row from the LOCATE's column (the last column left free: a character
  there moves the cursor on to the next row), longer English cut and
  reported; a row
  ending in an input box "[ ]" (the game puts its cursor there) keeps the
  box at its column, the English padded before it.
* w (word): a word the game matches what the player types against: the
  parser's verbs and nouns (DATA lists searched for in the typed line, the
  spaces around them part of the match) and whole commands compared with =.
  Written as given, spaces included.

A program that changes loses the spaces kept between its tokens (01
bytes, which only LIST shows), and the program with its DATA words must
fit the memory the game leaves it (game.json "memory": {program: bytes},
measured): a build that does not is refused.

Japanese is half-width katakana here, so English goes out as ASCII on the
same text layer: no drawing change.  A string literal holds at most 255
bytes (its length byte): a longer message is split into several, a longer
word refused.
"""
import json
import os
import re

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .n88disk import N88Image
from . import n88prog as P
from .text import pseudo

PREFIX = {"msg": "m", "line": "l", "word": "w"}
LOCATE = 0xAC
WAIT = b"\x3aZ\x019$\xf1\xff\xc4(\x11)"            # :Z9$=INPUT$(1)
PRINT_ = bytes([P.PRINT, 0x01])                       # PRINT and a space


def _image(cfg, src):
    base = os.path.dirname(src)
    return N88Image([src] + [os.path.join(base, n) for n in cfg.get("disks", [])])


def show(b):
    return b.decode("cp932", "replace")


def kind_of(stmt, before):
    """msg for a PRINT's text, word for a DATA list's or a comparison's."""
    if stmt == P.PRINT and before in (P.PRINT, 0x3B, 0x22):
        return "msg"
    return "word"


def _const(body, i):
    """(value, next index) of a numeric constant token at i, or (None, i)."""
    b = body[i] if i < len(body) else None
    if b is not None and 0x10 <= b <= 0x1A:          # (the numbers 0-10)
        return b - 0x10, i + 1
    if b == 0x0F:
        return body[i + 1], i + 2
    if b == 0x1C:
        return body[i + 1] | body[i + 2] << 8, i + 3
    return None, i


def locate_col(body, s):
    """The column of the LOCATE right before the PRINT whose literal starts
    at s (LOCATE x,y:PRINT "..."), or None."""
    k = s - 2
    while k > 0 and body[k] != P.PRINT:
        k -= 1
    if body[k - 1:k] != b":" and body[k - 2:k] != b":\x01":
        return None
    start = body.rfind(b":", 0, k - 1) + 1
    while start < k and body[start] in (0x01, 0x20):
        start += 1
    if body[start] != LOCATE:
        return None
    i = start + 1
    while body[i] == 0x01:
        i += 1
    return _const(body, i)[0]


def found(lines):
    """[(line index, literal index, start, end, kind)] of the Japanese
    literals: half-width katakana in them, longer than one character, every
    byte printable."""
    out = []
    for li, (_num, body) in enumerate(lines):
        for k, (s, e, stmt, before) in enumerate(P.literals(body)):
            t = body[s:e]
            if e - s < 2 or not any(0xA6 <= c <= 0xDF for c in t):
                continue
            if any(not (0x20 <= c < 0x7F or 0xA1 <= c <= 0xDF) for c in t):
                continue
            kind = kind_of(stmt, before)
            if kind == "msg" and before == P.PRINT and locate_col(body, s) is not None:
                kind = "line"
            out.append((li, k, s, e, kind))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(cfg, src).volumes[0]
    width, rows = cfg.get("width", 80), cfg["window_lines"]
    merged, order = {}, []
    for name in cfg["programs"]:
        lines, _tail = P.read(vol.read(name))
        for li, k, s, e, kind in found(lines):
            num, body = lines[li]
            jp = show(body[s:e])
            ref = "%s:%d:%d" % (name, num, k)
            key = (kind, jp)
            if key in merged:
                merged[key]["refs"].append(ref)
                continue
            note = {"msg": "a message: broken between words at %d half-width cells, a key waited for after "
                           "each %d lines" % (width - 1, rows - 2),
                    "line": "a row of a page the game lays out itself: one line, its room the rest of the "
                            "row (max_cells); a row ending in [ ] keeps that input box at its column (end the "
                            "English with [ ])",
                    "word": "a word matched against what the player types (a verb or noun searched for in "
                            "the typed line, or a whole command): the player types it as written, the "
                            "spaces around it included"}[kind]
            room = {"msg": (width - 1) * (rows - 2), "word": width - 1}.get(kind)
            if kind == "line":
                room = len(body[s:e]) if body[s:e].endswith(b"[ ]") else width - 1 - locate_col(body, s)
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
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


SUBST = {"’": "'", "‘": "'", "“": "'", "”": "'", "—": "-", "–": "-",
         "…": "...", '"': "'"}


def encode(text):
    """ASCII (a double quote becomes ', anything else not ASCII ?)."""
    s = "".join(SUBST.get(c, c) for c in text)
    return bytes(ord(c) if 0x20 <= ord(c) < 0x7F else ord("?") for c in s)


def wrap(text, width, col):
    """[line] of the English broken between words, the first line starting
    at `col`; \\n forces a break."""
    out = []
    for para in text.split("\n"):
        line, room = "", width - col
        for word in para.split(" "):
            cand = word if not line else line + " " + word
            if len(cand) <= room or not line and room == width:
                line = cand
                continue
            if line or room < width:
                out.append(line)
            line, room = word, width
            while len(line) > width:
                out.append(line[:width])
                line = line[width:]
        out.append(line)
        col = 0
    return out


def _start_col(body, s, lines_before, word_max):
    """The column a continuing message's first line starts at: what the
    statement printed before it on its line (its literals, a variable
    counted as the longest word)."""
    if body[s - 2] == P.PRINT or body[s - 3:s - 1] == PRINT_:
        return 0
    col = 0
    for ls, le, stmt, before in lines_before:
        col += le - ls
    return col + word_max


def build_message(en, width, rows, col):
    """The bytes put in place of a PRINT literal's text (between its
    quotes): the first line, then for each further line ":PRINT" and the
    line, a key wait after each windowful (the window's rows less two)."""
    lines = wrap(en, width - 1, col)
    parts = []
    for n, ln in enumerate(lines):
        raw = encode(ln)
        pieces = [raw[i:i + P.MAX_LITERAL] for i in range(0, len(raw), P.MAX_LITERAL)] or [b""]
        parts.append(b'";"'.join(pieces))
    out = parts[0]
    for n, part in enumerate(parts[1:], 1):
        out += b'"'
        if n % (rows - 2) == 0:
            out += WAIT
        out += b":" + PRINT_ + b'"' + part
    return out


def _pseudo(e):
    if e["kind"] == "msg":
        return pseudo(e["id"], 2 * len(e["jp"]))
    if e["kind"] == "line":
        box = " [ ]" if e["jp"].endswith("[ ]") else ""
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"] - len(box)] + box
    lead, tail = e["jp"][:len(e["jp"]) - len(e["jp"].lstrip(" "))], e["jp"][len(e["jp"].rstrip(" ")):]
    return lead + pseudo(e["id"], 2 * len(e["jp"].strip()), 1.0).split(" ")[0] + tail


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(cfg, src)
    vol = img.volumes[0]
    width, rows = cfg.get("width", 80), cfg["window_lines"]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e
            if text:
                by_ref[r] = text
    words = [by_ref.get(r, e["jp"]) for e in doc["strings"] if e["kind"] == "word" for r in e["refs"][:1]]
    word_max = max([len(w.strip()) for w in words] + [0])
    warn = []
    for name in cfg["programs"]:
        raw = vol.read(name)
        lines, tail = P.read(raw)
        lits = {}
        for li, k, s, e, kind in found(lines):
            lits.setdefault(li, []).append((k, s, e, kind))
        new_lines = list(lines)
        for li, items in lits.items():
            num, body = lines[li]
            all_lits = P.literals(body)
            out, pos = bytearray(), 0
            for k, s, e, kind in items:
                ref = "%s:%d:%d" % (name, num, k)
                en = by_ref.get(ref)
                if en is None:
                    continue
                if kind == "msg":
                    col = _start_col(body, s, [x for x in all_lits[:k] if x[2] == P.PRINT], word_max)
                    text = build_message(en, width, rows, col)
                elif kind == "line":
                    room = ids[ref]["max_cells"]
                    text = encode(" ".join(en.split("\n")))
                    if body[s:e].endswith(b"[ ]"):
                        if not text.endswith(b"[ ]"):
                            warn.append("%s: the English does not end in the input box [ ]" % ids[ref]["id"])
                        head = text[:-3].rstrip() if text.endswith(b"[ ]") else text
                        if len(head) + 4 > room:
                            warn.append("%s: %d cells, room for %d" % (ids[ref]["id"], len(head) + 4, room))
                            head = head[:room - 4]
                        text = head.ljust(room - 3) + b"[ ]"
                    elif len(text) > room:
                        warn.append("%s: %d cells, room for %d" % (ids[ref]["id"], len(text), room))
                        text = text[:room]
                else:
                    text = encode(en)
                    if len(text) > P.MAX_LITERAL:
                        raise SystemExit("%s: %d bytes, a word holds at most %d" % (ids[ref]["id"], len(text),
                                                                                 P.MAX_LITERAL))
                    if len(text) > width - 1:
                        warn.append("%s: %d cells, room for %d" % (ids[ref]["id"], len(text), width - 1))
                out += body[pos:s] + text
                pos = e
            new_lines[li] = (num, bytes(out + body[pos:]))
        if new_lines == lines:
            continue
        # (a changed program loses the spaces kept between its tokens: room for the English)
        new_lines = [(num, P.compact(body)) for num, body in new_lines]
        mem = cfg.get("memory", {}).get(name)
        if mem is not None:
            need = sum(len(body) + 5 for _num, body in new_lines) + sum(
                e - s for _num, body in new_lines for s, e, stmt, _b in P.literals(body) if stmt == P.DATA)
            if need > mem:
                raise SystemExit("%s: the program and its DATA words take %d bytes, the memory left for them "
                                 "%d; shorten the English" % (name, need, mem))
        vol.write(name, P.write(new_lines, tail))
    vol.create("MTL_NOTE.TXT", MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
