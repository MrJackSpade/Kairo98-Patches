"""English for Black Package's Miwaku no Chousho (pc98tl/mcs.py): strings.json in, a patched hard disk out.

Strings:
* m (message): a message's text after its speaker: any length, broken between words at 72 letters (the
  window's width), the window paging every 4 lines.  \\n a new line; {`0} the hero's name (others {`n}),
  {%n} {&n} a number, {?n} a colour, {^n} {}n} the program's own: keep them.
* l (label): a line of the system's screens (the sound setup, the menus, the options: the scripts A0_*.SO3,
  INIT.SO3 and MC_000.SO3), drawn at its place: up to max_cells letters; keep its {..} codes.
* n (name): a speaker's name, shown before a message ("name_" in the scripts): up to max_cells letters.
* c (choice): a choice's item: up to max_cells letters.
* i (insert): a name or line a script puts in its table of words (`n puts it in a message): up to max_cells
  letters.
* e (program): MCEXE.EXE's own message: in place, up to max_cells letters.

English is ASCII; the marks the program takes as codes (! ? - % & $ ^ ` { } # | * _ \\ ~) are written as
their full-width forms.
"""
import json
import os
import re

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .aypio import ascii_text
from .disk import DiskImage
from . import mcs as M
from .text import pseudo

PREFIX = {"msg": "m", "label": "l", "name": "n", "choice": "c", "insert": "i", "prog": "e"}
NOTE = {"msg": "a message: any length (broken between words at 72 letters, 4 lines a window, more after "
               "a key); \\n a new line; keep {`0} (the hero's name), {%n} (a number) and the other {..} codes",
        "label": "a line of the system's screens (sound setup, menus, options), drawn at its place: max_cells "
                 "letters; keep its {..} codes",
        "name": "a speaker's name before a message: max_cells letters",
        "choice": "a choice's item: max_cells letters",
        "insert": "a name or line a script keeps for its messages: max_cells letters",
        "prog": "the program's own message, in place: max_cells letters"}
SPEAKER = re.compile(rb"^((?:[\x81-\x9f\xe0-\xfc][\x40-\xfc]|`\d){1,8})_")
REAL = re.compile("[ぁ-ヺ一-鿿Ａ-ｚ０-９]")
EXE_TEXT = re.compile(rb"(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|[\x20-\x7e])*"
                      rb"(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]){3,}"
                      rb"(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|[\x20-\x7e])*")
NAME_WIDTH = 12                # letters allowed for the hero's name when breaking lines
SYSTEM = re.compile(r"A0_|INIT\.|MC_000\.")   # scripts of the system's screens: their messages are labels


def _cells(t):
    """Half-width cells of a label's characters (its codes left out)."""
    return sum(len(x[1]) for x in M.parts(t) if x[0] == "t")


def _path(cfg, name):
    return cfg["dir"] + "/" + name if cfg.get("dir") else name


def _vol(src):
    img = DiskImage(src)
    return img, img.volumes[0]


def _scripts(vol, cfg):
    return sorted(e["name"] for e in vol.listdir(vol.find(cfg["dir"])["cluster"]) if e["name"].endswith(".SO3"))


def _choice_text(a):
    """A choice's text: after its operands (its number, a condition's) and FFFFh, up to a NUL: (start, end)
    in the args."""
    p = a.find(b"\xff\xff", 3)
    if p < 0:
        return None
    end = a.find(b"\0", p + 2)
    return (p + 2, end) if end > p + 2 else None


def _insert_text(a):
    """An insert's text: after its operand (3 bytes), up to its "!": (start, end)."""
    end = a.find(b"!", 3)
    return (3, end) if end > 3 else None


def _decodes(b):
    try:
        return b.decode("cp932")
    except UnicodeDecodeError:
        return None


def found(vol, cfg):
    """[(ref, kind, japanese, room)]."""
    out = []
    for name in _scripts(vol, cfg):
        s = M.Script(vol.read(_path(cfg, name)))
        for it in s.ops():
            c, a = it[2], it[3]
            ref = "%s:%05x" % (name, it[1])
            if c == M.MESSAGE:
                t = a.split(b"\0")[0]
                if _decodes(t) is None or not REAL.search(M.show(t)):
                    continue
                m = SPEAKER.match(t)
                if m:
                    who = m.group(1)
                    if not who.startswith(b"`"):
                        out.append((ref + ":n", "name", who.decode("cp932"), len(who)))
                    t = t[m.end():]
                if REAL.search(M.show(t)):
                    if SYSTEM.match(name):
                        out.append((ref, "label", M.show(t), _cells(t)))
                    else:
                        out.append((ref, "msg", M.show(t), M.WIDTH))
            elif c == M.CHOICE:
                r = _choice_text(a)
                if r and _decodes(a[r[0]:r[1]]) and REAL.search(_decodes(a[r[0]:r[1]])):
                    out.append((ref, "choice", M.show(a[r[0]:r[1]]), r[1] - r[0]))
            elif c == M.INSERT:
                r = _insert_text(a)
                if r and _decodes(a[r[0]:r[1]]) and REAL.search(_decodes(a[r[0]:r[1]])):
                    out.append((ref, "insert", _decodes(a[r[0]:r[1]]).rstrip("　"), r[1] - r[0]))
    exe = vol.read(_path(cfg, cfg["program"]))
    for m in EXE_TEXT.finditer(exe):
        t = _decodes(m.group())
        if _program_text(t):
            out.append(("E:%05x" % m.start(), "prog", t, m.end() - m.start()))
    return out


def _program_text(t):
    """A message of the program's own: kana, no private-use characters (bytes of code), no blanks the
    program fills in itself (two spaces, a full-width space)."""
    return bool(t and re.search("[ぁ-ヺ]", t) and not re.search("[-]|  |　", t))


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    _img, vol = _vol(src)
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


# ---- English ----

TOKEN = re.compile(r"\{([`%&?^}]\d*)\}")


def _bytes(text):
    """English as the program's bytes: ASCII, its code marks full-width."""
    out = bytearray()
    for ch in ascii_text(text):
        out += M.FULL[ch].encode("cp932") if ch in M.FULL else ch.encode("ascii")
    return bytes(out)


def _cols(t):
    t = re.sub(r"\{[^{}]*\}", "", t).replace("\n", "")
    return sum(2 if ord(c) > 0x7F else 1 for c in t)


def _pseudo(e):
    if e["kind"] == "label":
        parts = re.split(r"(\{[^{}]*\}|\n)", e["jp"])
        return "".join(p if re.fullmatch(r"\{[^{}]*\}|\n", p) or not p else pseudo(e["id"], _cols(p), 1.0)[:_cols(p)]
                       for p in parts)
    if e["kind"] != "msg":
        return pseudo(e["id"], _cols(e["jp"]), 1.0)[:e["max_cells"]]
    parts = re.split(r"(\{[^{}]*\}|\n)", e["jp"])
    return "".join(p if re.fullmatch(r"\{[^{}]*\}|\n", p) or not p else pseudo(e["id"], _cols(p))
                   for p in parts)


def _width(piece):
    m = TOKEN.fullmatch(piece)
    if m:
        return NAME_WIDTH if m.group(1).startswith("`") else 6 if m.group(1)[0] in "%&" else 0
    return len(_bytes(piece))


def message(text):
    """A message's English as its bytes: lines broken between words at WIDTH cells with "-"."""
    lines = []
    for para in text.split("\n"):
        words = re.findall(r"\{[^{}]*\}\S*|\S+", para)
        cur, w = [], 0
        for word in words:
            ww = sum(_width(x) for x in re.findall(r"\{[^{}]*\}|[^{]+|\{", word))
            if cur and w + 1 + ww > M.WIDTH:
                lines.append(" ".join(cur))
                cur, w = [], 0
            cur.append(word)
            w += ww + (1 if len(cur) > 1 else 0)
        lines.append(" ".join(cur))
    out = bytearray()
    for k, ln in enumerate(lines):
        if k:
            out += b"-"
        for x in re.findall(r"\{[^{}]*\}|[^{]+|\{", ln):
            m = TOKEN.fullmatch(x)
            out += m.group(1).encode("ascii") if m else _bytes(x)
    return bytes(out)


def label(text):
    """A label's English as its bytes: its lines as they are ("-" between them), codes kept."""
    out = bytearray()
    for k, ln in enumerate(text.split("\n")):
        if k:
            out += b"-"
        for x in re.findall(r"\{[^{}]*\}|[^{]+|\{", ln):
            m = TOKEN.fullmatch(x)
            out += m.group(1).encode("ascii") if m else _bytes(x)
    return bytes(out)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img, vol = _vol(src)
    by_ref, warn = {}, []
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        if not text:
            continue
        if e["kind"] in ("msg", "label"):
            if e["kind"] == "label" and _cols(text) > e["max_cells"]:
                warn.append("%s: %d letters, room for %d" % (e["id"], _cols(text), e["max_cells"]))
            if sorted(TOKEN.findall(text)) != sorted(TOKEN.findall(e["jp"])):
                warn.append("%s: its {..} codes differ from the Japanese's" % e["id"])
        else:
            text = text.replace("\n", " ")
            if len(_bytes(text)) > e["max_cells"]:
                warn.append("%s: %d letters, room for %d (cut)" % (e["id"], len(_bytes(text)), e["max_cells"]))
        for r in e["refs"]:
            by_ref[r] = (e, text)
    if not by_ref:
        img.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    try:
        for name in _scripts(vol, cfg):
            s = M.Script(vol.read(_path(cfg, name)))
            changed = False
            for it in s.ops():
                c, a = it[2], it[3]
                ref = "%s:%05x" % (name, it[1])
                if c == M.MESSAGE:
                    t = a.split(b"\0")[0]
                    m = SPEAKER.match(t)
                    who, body = (t[:m.end()], t[m.end():]) if m else (b"", t)
                    hn, hm = by_ref.get(ref + ":n"), by_ref.get(ref)
                    if not hn and not hm:
                        continue
                    if hn:
                        who = _bytes(hn[1])[:hn[0]["max_cells"]] + b"_"
                    if hm:
                        body = message(hm[1]) if hm[0]["kind"] == "msg" else label(hm[1])
                    it[3] = who + body + b"\0" + a[len(t) + 1:]
                    changed = True
                elif c in (M.CHOICE, M.INSERT):
                    r = (_choice_text if c == M.CHOICE else _insert_text)(a)
                    hit = by_ref.get(ref)
                    if not r or not hit:
                        continue
                    b = _bytes(hit[1])[:hit[0]["max_cells"]]
                    if c == M.INSERT:
                        b = b.ljust(r[1] - r[0])
                    it[3] = a[:r[0]] + b + a[r[1]:]
                    changed = True
            if changed:
                try:
                    data = s.build()
                except ValueError as err:
                    raise ValueError("%s: %s" % (name, err))
                vol.write(_path(cfg, name), M.lz(data))
        p = _path(cfg, cfg["program"])
        exe = bytearray(vol.read(p))
        for m in EXE_TEXT.finditer(bytes(exe)):
            if not _program_text(_decodes(m.group())):
                continue
            hit = by_ref.get("E:%05x" % m.start())
            if hit:
                b = _bytes(hit[1])[:m.end() - m.start()]
                exe[m.start():m.end()] = b.ljust(m.end() - m.start())
        vol.write(p, bytes(exe))
    except ValueError as err:
        raise SystemExit(str(err))
    vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
