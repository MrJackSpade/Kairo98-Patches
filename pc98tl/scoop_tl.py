"""English for Scoop's Adventure Script Interpreter (pc98tl/scoop.py; Immoral Study 1-3):
strings.json in, a patched image out.

Strings (refs SCRIPT:offset of the string in its table):

* "msg": a message (op 44h): any length.  The patcher breaks its lines between words (0Dh) at the
  window's width (game.json "window_cells"), going on from where the message before it left the
  line (a speaker's tag starts a new one); the window pages by itself.  `\\n` in the English forces
  a new line; "[" and "]" around words show them in the highlight colour, as in the Japanese.
* "name": a speaker's tag (op 44h, "<...>"): one line, `max_cells` the Japanese's.
* "item": a menu's item (op 4Ah): one line in the menu's box, `max_cells` the Japanese's (past it
  reported).
* "title": a menu's heading (op 4Bh, shown highlighted): one line, `max_cells` the Japanese's (past
  it reported).
* "batch": a line the game's batch file prints when it cannot start (refs BAT:line): one line.

`{C1}`-style tokens stand for the colour commands inside a string and must be kept.  English is
ASCII, drawn half-width; "<" and ">" (a tag's marks) are written "(" and ")"; another character is
written in Shift-JIS when it has a two-byte one, else "?".  A script with its English may take
64 KB; a longer build is refused and names the script.
"""
import json
import os
import re

from . import scoop
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "item": "i", "title": "t", "batch": "b"}
COMMAND = re.compile(rb"\x1b[^;\x00]*;|[<>\x01-\x05]")
TOKEN = re.compile(r"\{C(\d+)\}")
UNKNOWN = re.compile(r"\{X([0-9A-F]{4})\}")
ANY_TOKEN = re.compile(r"\{C(\d+)\}|\{X([0-9A-F]{4})\}")
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "<": "(", ">": ")"}


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def _path(cfg, name):
    return cfg["game_dir"] + "/" + name


def atoms(raw, kana):
    """[(kind, text, bytes)]: "c" a command, "n" a new line (0Dh), "t" a character (one the table or
    Shift-JIS does not have is a {Xhhhh} token)."""
    out, i = [], 0
    while i < len(raw):
        m = COMMAND.match(raw, i)
        if m:
            out.append(("c", "", m.group(0)))
            i = m.end()
            continue
        b = raw[i]
        if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
            r = raw[i:i + 2]
            try:
                ch = r.decode("cp932")
            except UnicodeDecodeError:
                ch = "{X%s}" % r.hex().upper()
            i += 2
        elif 0xA0 <= b <= 0xDF:
            r, ch = raw[i:i + 1], kana[b]
            i += 1
        elif b == 0x0D:
            out.append(("n", "\n", raw[i:i + 1]))
            i += 1
            continue
        else:
            r, ch = raw[i:i + 1], chr(b)
            i += 1
        out.append(("t", ch, r))
    return out


def split(raw, kana):
    """(prefix bytes, visible text, suffix bytes, [inner command bytes]): the commands and new lines
    at either end are the prefix and suffix; a command inside is a {Cn} token, a new line "\n"."""
    at = atoms(raw, kana)
    a, b = 0, len(at)
    while a < b and at[a][0] in "cn":
        a += 1
    while b > a and at[b - 1][0] in "cn":
        b -= 1
    inner, vis = [], ""
    for kind, ch, r in at[a:b]:
        if kind == "c":
            inner.append(r)
            vis += "{C%d}" % len(inner)
        else:
            vis += ch
    return b"".join(r for _k, _c, r in at[:a]), vis, b"".join(r for _k, _c, r in at[b:]), inner


def cells(text):
    """The cells a visible text takes on one line (the tokens and the highlight marks none, an
    {Xhhhh} two)."""
    t = TOKEN.sub("", text).replace("[", "").replace("]", "")
    t = UNKNOWN.sub("..", t)
    return sum(1 if ord(c) < 0x80 else 2 for c in t)


def encode(text, inner):
    out = bytearray()
    pos = 0
    for m in ANY_TOKEN.finditer(text):
        out += _chars(text[pos:m.start()])
        if m.group(1):
            k = int(m.group(1)) - 1
            if 0 <= k < len(inner):
                out += inner[k]
        else:
            out += bytes.fromhex(m.group(2))
        pos = m.end()
    out += _chars(text[pos:])
    return bytes(out)


def _chars(text):
    out = bytearray()
    for ch in "".join(SUBST.get(c, c) for c in text):
        if ch == "\n":
            out += b"\r"
        elif " " <= ch <= "~":
            out += ch.encode("ascii")
        else:
            try:
                b = ch.encode("cp932")
            except UnicodeEncodeError:
                b = b"?"
            out += b if len(b) == 2 else b"?"
    return bytes(out)


def scripts(vol, cfg):
    for path, e in vol.walk():
        if e["is_dir"] or not path.upper().startswith(cfg["game_dir"].upper() + "/"):
            continue
        if path.upper().endswith(".BIN"):
            d = vol.read(path)
            if scoop.is_script(d):
                yield path, d


def batch_lines(bat):
    """[(line index, the text after "echo ")] of the batch file's Japanese lines."""
    out = []
    for k, ln in enumerate(bat.split(b"\r\n")):
        if ln.lower().startswith(b"echo ") and any(c >= 0x80 for c in ln):
            out.append((k, ln[5:].decode("cp932")))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    kana = scoop.kana_table(vol.read(_path(cfg, cfg["program"])))
    merged, order = {}, []

    def add(kind, jp, ref, cells_, note=None):
        key = (kind, jp)
        if key in merged:
            if ref not in merged[key]["refs"]:
                merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], cells_)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells_}
        if note:
            merged[key]["note"] = note
        order.append(key)
    for path, d in scripts(vol, cfg):
        sc = scoop.Script(d)
        name = path.rsplit("/", 1)[-1]
        seen = set()
        for _a, off, kind in sc.shown:
            if off in seen:
                continue
            seen.add(off)
            _p, vis, _s, _inner = split(sc.text(off), kana)
            if not vis.strip("　 \n"):
                continue
            if kind == "msg" and sc.text(off).startswith(b"<"):
                kind = "name"
            ref = "%s:%04x" % (name, off)
            if kind == "msg":
                add(kind, vis, ref, cfg["window_cells"])
            else:
                add(kind, vis, ref, cells(vis), {
                    "name": "a speaker's tag: one line",
                    "item": "a menu's item: one line in its box",
                    "title": "a menu's heading, highlighted: one line"}[kind])
    bat = cfg.get("batch")
    if bat:
        for k, t in batch_lines(vol.read(_path(cfg, bat))):
            add("batch", t, "%s:%d" % (bat, k), 78, "printed by the batch file when the game cannot start")
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


def wrap(text, col, width):
    """(the English with new lines between words at the window's width, the column it ends at)."""
    out = []
    for k, para in enumerate(text.split("\n")):
        if k:
            out.append("\n")
            col = 0
        for j, word in enumerate(para.split(" ")):
            w = cells(word)
            if j and col:
                if col + 1 + w > width:
                    out.append("\n")
                    col = 0
                else:
                    out.append(" ")
                    col += 1
            elif j:
                out.append(" ")
                col += 1
            out.append(word)
            col += w
            while col > width:
                col -= width
    return "".join(out), col


def _pseudo(e):
    if e["kind"] in ("name", "item", "title"):
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"]]
    if e["kind"] == "batch":
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"]]
    return pseudo(e["id"], cells(e["jp"]))


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    kana = scoop.kana_table(vol.read(_path(cfg, cfg["program"])))
    by_ref, ids, rooms = {}, {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            rooms[r] = e["max_cells"]
            if text:
                by_ref[r] = text
    warn, done = [], 0
    width = cfg["window_cells"]
    for path, d in list(scripts(vol, cfg)):
        sc = scoop.Script(d)
        name = path.rsplit("/", 1)[-1]
        new, col = {}, 0
        for _a, off, kind in sc.shown:
            raw = sc.text(off)
            prefix, vis, suffix, inner = split(raw, kana)
            if kind == "msg" and raw.startswith(b"<"):
                col = 0
                kind = "name"
            ref = "%s:%04x" % (name, off)
            if kind == "msg" and b"\r" in prefix:
                col = 0
            t = by_ref.get(ref) if vis.strip("　 \n") else None
            if kind == "msg":
                if t is None:
                    for k, line in enumerate(vis.split("\n")):
                        col = cells(line) + (0 if k else col)
                    col %= width
                else:
                    t, col = wrap(t, col, width)
            elif t is not None and cells(t) > rooms[ref]:
                warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(t), rooms[ref]))
            if kind == "msg" and b"\r" in suffix:
                col = 0
            if t is not None and off not in new:
                new[off] = prefix + encode(t, inner) + suffix
        if not new:
            continue
        try:
            out = scoop.rebuild(sc, new)
        except OverflowError:
            raise SystemExit("%s: past 64 KB with its English; shorten these strings: %s" % (
                name, ", ".join(sorted({ids["%s:%04x" % (name, o)] for o in new}))))
        vol.write(path, out)
        done += 1
    bat = cfg.get("batch")
    if bat:
        lines = vol.read(_path(cfg, bat)).split(b"\r\n")
        changed = False
        for k, _t in batch_lines(b"\r\n".join(lines)):
            ref = "%s:%d" % (bat, k)
            if ref in by_ref:
                lines[k] = b"echo " + _chars(by_ref[ref])
                changed = True
        if changed:
            vol.write(_path(cfg, bat), b"\r\n".join(lines))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
