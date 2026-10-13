"""English for Active's Angel Halo (pc98tl/active_halo.py): strings.json in, a patched image out.

Strings (refs SCRIPT:offset in the script's code; OPENING.DAT:line; MENU.GMO:item; the program's own
strings MAIN98.EXE:offset in its data):

* "msg": a message: the texts one after another (op 04h each, a line each) up to another op; shown as
  lines (`\\n` between them).  Any length: the patcher breaks the English between words into lines of
  `max_cells` half-width cells (the narrower window's width; a letter one cell, another character two),
  each a text of its own, and the program pages the window past its lines.  `\\n` in the English
  forces a new line.  The controls are `{W}`-style tokens (`{P}` the key wait, `{W}` the key wait and a
  cleared window, `{V0102}` a control and its two bytes); a key wait the message ends with is put back
  when the English leaves it out.
* "item": a choice's item (an `I` entry's name): `max_cells` the menu's widest Japanese item; past it
  reported.
* "prompt": a string op 0Bh's sub-op 1Bh keeps for later: `max_cells` the Japanese's; past it reported.
* "opening": a block of the opening's lines (OPENING.DAT's `>N` and its lines, shown centred): any
  number of lines, each at most `max_cells` (the widest Japanese line); the patcher breaks the English
  between words and sets the block's line count.
* "menu": a main menu item's description (the *.GMO menus'), shown on the line under the menu:
  `max_cells` the menu's widest Japanese one; past it reported.
* "label": a string of the program's: in place, `max_cells` its room in bytes; past it cut and
  reported.  `%s`-style marks are kept.

English is ASCII (the program draws it half-width); another character is written full-width in
Shift-JIS when it has one, else `?`.  A changed script is laid out anew with every place moved; the
program holds a script of at most 49152 bytes, so a longer build is refused and names the script's
strings (in pseudo mode the filler is cut).  FDHALO.PAK is written anew.
"""
import json
import os
import re
import struct

from . import active_halo as H
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "item": "i", "prompt": "p", "opening": "o", "menu": "d", "label": "l"}
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "\\": "/", "{": "(",
         "}": ")"}
ROOM = 0xC000                    # the program's script buffer
TOKEN = re.compile(r"\{([A-Z\\])([0-9A-F]{4})?\}")
PROG_STR = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*[\x81-\x9f\xe0-\xef][\x40-\xfc]"
                      rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e])*\x00")
FORMAT = re.compile(r"%[0-9]*[sdux]")
WORDY = re.compile(r"[ぁ-ヿ一-鿿Ａ-ｚ]")


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def cells(text):
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
            if k in H.ESC_ARG and i + 3 < len(b):
                out.append("{%c%02X%02X}" % (k, b[i + 2], b[i + 3]))
                i += 4
            else:
                out.append("{%c}" % k)
                i += 2
            continue
        n = 2 if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF) else 1
        out.append(b[i:i + n].decode("cp932", "replace"))
        i += n
    return "".join(out)


def _sjis(ch):
    try:
        return ch.encode("cp932")
    except UnicodeEncodeError:
        return b"?"


def encode(text):
    """The English as the program's bytes: ASCII as it is, another character in Shift-JIS, the
    tokens as their controls."""
    out, i = bytearray(), 0
    while i < len(text):
        m = TOKEN.match(text, i)
        if m:
            out += b"\\" + m.group(1).encode()
            if m.group(2):
                out += bytes.fromhex(m.group(2))
            i = m.end()
            continue
        for ch in SUBST.get(text[i], text[i]):
            out += ch.encode() if " " <= ch <= "~" else _sjis(ch)
        i += 1
    return bytes(out)


def wrap(text, width):
    """The English's lines, broken between words at width cells."""
    out = []
    for para in text.split("\n"):
        line, col = [], 0
        for word in para.split(" "):
            w = cells(word)
            if line and col + 1 + w > width:
                out.append(" ".join(line))
                line, col = [], 0
            line.append(word)
            col += w + (1 if col else 0)
            while col > width and len(line) == 1:
                cut, k = [], 0
                for ch in word:
                    if cells("".join(cut) + ch) > width:
                        break
                    cut.append(ch)
                out.append("".join(cut))
                word = word[len(cut):]
                line, col = [word], cells(word)
        out.append(" ".join(line))
    return out


def visible(b):
    return bool(re.sub(r"\{[^}]*\}", "", show(b)).strip("　 "))


def scripts(pak):
    return [n for n in pak.names() if n.upper().endswith(".HGO")]


def messages(h):
    """[(start, end, [text starts], jp)]: the op 04h texts one after another (the ops' bytes from the
    first op to past the last text) with something to show; a place an op points at starts another."""
    d, ents, ptrs, ev = H.walk(h)
    targets = {struct.unpack_from("<H", d, p)[0] for p in ptrs} | {e[1] for e in ents} | {e[2] for e in ents}
    out, run = [], []

    def flush():
        if run:
            jp = "\n".join(show(d[s:e - 1]) for _o, s, e in run)
            out.append((run[0][0], run[-1][2], [s for _o, s, _e in run], jp))
            run.clear()
    k = 0
    while k < len(ev):
        e = ev[k]
        if e[0] == "op" and e[2] == 4 and k + 1 < len(ev) and ev[k + 1][0] == "text":
            t = ev[k + 1]
            if visible(d[t[1]:t[2] - 1]):
                if run and (run[-1][2] != e[1] or e[1] in targets):
                    flush()
                run.append((e[1], t[1], t[2]))
            else:
                flush()
            k += 2
            continue
        flush()
        k += 1
    flush()
    return out


def items(h):
    d, ents, _p, ev = H.walk(h)
    out = []
    menu = []
    for e in ev:
        if e[0] == "item":
            ent = ents[e[1]]
            out.append((ent[4], d.index(0, ent[4]) + 1, show(H.item_name(d, ent)), len(menu)))
    return out


def prompts(h):
    d, _ents, _p, ev = H.walk(h)
    out = []
    for k, e in enumerate(ev):
        if e[0] == "op" and e[2] == 0xB and e[3] == 0x1B:
            s = e[1] + 2
            out.append((s, d.index(0, s) + 1, show(d[s:d.index(0, s)])))
    return out


def opening_blocks(data):
    """[(first line, count, [lines])]: OPENING.DAT's `>N` blocks."""
    lines = data.split(b"\r\n")
    out = []
    for k, ln in enumerate(lines):
        if ln.startswith(b">") and ln[1:].isdigit():
            n = int(ln[1:])
            out.append((k, n, [show(x) for x in lines[k + 1:k + 1 + n]]))
    return out


def prog_strings(exe, hdr):
    img = exe[hdr:]
    segs = [struct.unpack("<H", m.group(1))[0] * 16 for m in re.finditer(rb"\xb8(..)\x8e\xd8", img, re.S)]
    start = min(s for s in segs if 0 < s < len(img))
    out = []
    for m in PROG_STR.finditer(img, start):
        txt = m.group()[:-1].decode("cp932", "replace")
        if WORDY.search(txt):
            out.append((hdr + m.start(), hdr + m.end() - 1))
    return out


def _paths(cfg):
    gd = cfg["game_dir"]
    return gd + "/" + cfg["program"], gd + "/" + cfg["archive"]


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    prog_path, pak_path = _paths(cfg)
    exe = vol.read(prog_path)
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    pak = H.Pak(vol.read(pak_path))
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
            "character two); %s-style marks kept")
    if "OPENING.DAT" in pak.names():
        blocks = opening_blocks(pak.read("OPENING.DAT"))
        width = max((cells(x) for _k, _n, ls in blocks for x in ls), default=0)
        for k, n, ls in blocks:
            add("opening", "\n".join(ls), "OPENING.DAT:%d" % k, width,
                "the opening's lines shown together, centred: any number, each at most max_cells")
    for n in [x for x in pak.names() if x.upper().endswith(".GMO")]:
        descs = H.gmo(pak.read(n))
        room = max(cells(show(t)) for _i, t in descs)
        for item, t in descs:
            add("menu", show(t), "%s:%d" % (n, item), room, "a main menu item's description, on the line "
                "under the menu (the menu's widest Japanese one)")
    for n in scripts(pak):
        h = pak.read(n)
        its = items(h)
        room = max((cells(t) for _s, _e, t, _m in its), default=0)
        for s, e, t, _m in its:
            if t.strip():
                add("item", t, "%s:%04x" % (n, s), room, "a choice's item (the script's widest Japanese item)")
        for s, e, t in prompts(h):
            if visible(t.encode("cp932", "replace")):
                add("prompt", t, "%s:%04x" % (n, s), cells(t))
        for s, e, starts, jp in messages(h):
            add("msg", jp, "%s:%04x" % (n, s), H.LINE)
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
    if e["kind"] == "label":
        marks = FORMAT.findall(e["jp"])
        return (" ".join(marks) + " " if marks else "") + pseudo(e["id"], e["max_cells"], 1.0)[:max(
            1, e["max_cells"] - sum(len(m) + 1 for m in marks))]
    if e["kind"] in ("item", "prompt", "menu"):
        return pseudo(e["id"], e["max_cells"], 1.0)[:max(2, e["max_cells"])]
    keep = "".join(m.group() for m in TOKEN.finditer(e["jp"]) if m.group(1) in "WP")
    return pseudo(e["id"], cells(e["jp"])) + keep


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    prog_path, pak_path = _paths(cfg)
    exe = vol.read(prog_path)
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    raw_pak = vol.read(pak_path)
    pak = H.Pak(raw_pak)
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
            b = b[:e - s]
            while b and b[-1] >= 0x80 and len(b.decode("cp932", "ignore").encode("cp932")) != len(b):
                b = b[:-1]
        prog[s:e] = b.ljust(e - s, b"\0")
    if bytes(prog) != exe:
        vol.write(prog_path, bytes(prog))
    changed = False
    if "OPENING.DAT" in pak.names():
        data = pak.read("OPENING.DAT")
        lines = data.split(b"\r\n")
        outl, at = [], 0
        for k, n, ls in opening_blocks(data):
            en = by_ref.get("OPENING.DAT:%d" % k)
            outl += lines[at:k]
            if en is None:
                outl += lines[k:k + 1 + n]
            else:
                new = [encode(x) for x in wrap(en, rooms["OPENING.DAT:%d" % k])]
                outl += [b">%d" % len(new)] + new
            at = k + 1 + n
        outl += lines[at:]
        nd = b"\r\n".join(outl)
        if nd != data:
            pak.replace("OPENING.DAT", nd)
            changed = True
    for n in [x for x in pak.names() if x.upper().endswith(".GMO")]:
        d = pak.read(n)
        texts = {}
        for item, t in H.gmo(d):
            ref = "%s:%d" % (n, item)
            en = by_ref.get(ref)
            if en is not None:
                if cells(en) > rooms[ref]:
                    warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
                texts[item] = encode(en)
        if texts:
            pak.replace(n, H.gmo_build(d, texts))
            changed = True
    rebuilt = 0
    for n in scripts(pak):
        h = pak.read(n)
        msgs, its, prs = messages(h), items(h), prompts(h)

        def build(ratio):
            new = {}
            for s, e, t, _m in its:
                ref = "%s:%04x" % (n, s)
                en = by_ref.get(ref)
                if en is not None:
                    if cells(en) > rooms[ref]:
                        warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
                    new[s] = (e, encode(en) + b"\0")
            for s, e, t in prs:
                ref = "%s:%04x" % (n, s)
                en = by_ref.get(ref)
                if en is not None:
                    if cells(en) > rooms[ref]:
                        warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
                    new[s] = (e, encode(en) + b"\0")
            for s, e, starts, jp in msgs:
                ref = "%s:%04x" % (n, s)
                en = by_ref.get(ref)
                if en is None:
                    continue
                if ratio < 1:
                    en = en[:max(4, int(len(en) * ratio))]
                for tok in ("{W}", "{P}"):
                    if jp.endswith(tok) and tok not in en:
                        en += tok
                lines = wrap(en, rooms[ref])
                new[s] = (e, b"".join(b"\x04" + encode(ln) + b"\0" for ln in lines))
            return new, H.rebuild(h, new) if new else h
        new, out = build(1.0)
        if len(out) > ROOM:
            if mode != "pseudo":
                raise SystemExit("%s: %d bytes with its English, the program holds %d; shorten these strings: %s"
                                 % (n, len(out), ROOM, ", ".join(sorted({ids[r] for r in by_ref
                                                                         if r.startswith(n + ":")}))))
            ratio = 1.0
            while len(out) > ROOM:
                ratio *= 0.9
                new, out = build(ratio)
            warn.append("%s: the filler was cut to %d%% to fit the program's %d bytes" % (n, int(ratio * 100), ROOM))
        if new:
            pak.replace(n, out)
            rebuilt += 1
            changed = True
    if changed:
        vol.write(pak_path, pak.build())
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), rebuilt))
