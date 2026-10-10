"""English for Panther Software's Hamlet (pc98tl/panther.py): strings.json in, a patched image out.

Strings:

* "msg": a scene's strings (refs SCENE:offset): a message (shown by function 5, its offset the
  immediate of a mov si) takes any length: in its own bytes when it fits, else put at the scene's
  end, the mov si's pointed at it; wrapped by the patcher between words to `max_cells` (45) letters a
  line with 0Dh, the engine paging every 5 lines.  A string no mov si names (`note` says so) keeps
  its own bytes.  \\n starts a new line.
* "engine": HAM.EXE's own strings (refs HAM.EXE:offset): its messages (a mov si names them: the
  items' descriptions, the game over) as the scenes' are, put past its data segment when longer than
  their own bytes; the menus' labels (a mov bx names them, for the string routine) the same, one line
  each, their room the Japanese's (past it reported); the rest (the weapons' names padded with spaces
  as the Japanese are, the disk prompts) each in its own bytes.

* "opening": HOPEN.EXE's (game.json "opening"; refs HOPEN.EXE:offset), all rebuilt past its data
  segment, one line each: the story pages' lines (80 letters, centred anew where the Japanese is
  centred), the characters' names (centred in their card's columns), the glossary page's (80) and the
  mode labels (their room the Japanese's, past it reported).  A line past its room is cut.

English is ASCII (drawn half-width by the patch's helper); another character is written in Shift-JIS
when it has it (two bytes, full-width), else as `?`.
"""
import json
import os
import re
import struct

from . import panther
from .alice_sys2_tl import sha256

PREFIX = {"msg": "m", "engine": "e", "opening": "o"}
SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "♥": "<3"}
LINE = 45                       # a message line: 23 characters' 46 letters, one short
RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e\x0d])+\x00", re.S)
SJIS = re.compile(rb"[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]", re.S)


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def _path(cfg, name):
    return cfg["game_dir"] + "/" + name if cfg["game_dir"] else name


def decode(raw):
    return raw.decode("cp932", "replace").replace("\r", "\n")


def _kana(text):
    return sum(1 for c in text if "぀" <= c <= "ヿ")


def scene_strings(d):
    """[(start, end past the 00, [the mov si's offsets])] of a scene's strings: in each run of text
    the earliest character mov si names, else (no mov si names it: [] ) the run past any leading
    letters that aren't a space or 0Dh, when it has two kana or is a credit (full-width spaces first,
    something after them: the ending's)."""
    out = []
    for m in RUN.finditer(d):
        if len(SJIS.findall(m.group())) < 2:
            continue
        pos, chosen = m.start(), None
        while pos < m.end() - 1:
            refs = [h.start() - 1 for h in re.finditer(re.escape(struct.pack("<H", pos)), d) if d[h.start() - 1] == 0xBE]
            if refs:
                chosen = (pos, m.end(), refs)
                break
            pos += 2 if SJIS.match(d, pos) else 1
        if chosen is None:
            text = decode(m.group()[:-1])
            if _kana(text) < 2 and not (text.startswith("　") and text.strip("　\n")):
                continue
            start = m.start()
            while d[start] < 0x80 and d[start] not in (0x0D, 0x20):
                start += 1
            chosen = (start, m.end(), [])
        out.append(chosen)
    return out


def scenes(vol, cfg):
    cluster = vol.find(cfg["game_dir"])["cluster"] if cfg["game_dir"] else 0
    return sorted(e["name"] for e in vol.listdir(cluster)
                  if not e["is_dir"] and e["name"].upper().endswith((".P", ".CMN", ".BIN")))


def program_strings(exe):
    """[(start, end past the 00, [the mov si's file offsets], [the mov bx's])] of HAM.EXE's own strings
    (in its data segment): a message (the items' descriptions, the game over) is one a mov si in the
    code names; a label (the menus') one a mov bx names, the string routine called after it."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    base = hdr + panther.data_segment(exe) * 16
    strfn = panther.string_routine(exe)
    out = []
    for m in RUN.finditer(exe, base):
        if len(SJIS.findall(m.group())) >= 2 and "�" not in decode(m.group()):
            rel = struct.pack("<H", m.start() - base)
            at = [h.start() - 1 for h in re.finditer(re.escape(rel), exe[:base])]
            msg = [r for r in at if exe[r] == 0xBE]
            label = [r for r in at if exe[r] == 0xBB and any(
                exe[k] == 0xE8 and (k + 3 + struct.unpack_from("<h", exe, k + 1)[0] - hdr) & 0xFFFF == strfn
                for k in range(r + 3, r + 10))]
            out.append((m.start(), m.end(), msg, label))
    return out


def encode(text, newlines=True):
    out = bytearray()
    for c in "".join(SUBST.get(c, c) for c in text):
        if c == "\n":
            out += b"\x0d" if newlines else b" "
        elif 0x20 <= ord(c) < 0x7F:
            out.append(ord(c))
        else:
            try:
                b = c.encode("cp932")
            except UnicodeEncodeError:
                b = b"?"
            out += b if len(b) == 2 else b"?"
    return bytes(out)


def wrap(text, width=LINE):
    """text with new lines between words where a line would pass width letters."""
    lines = []
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
    return "\n".join(lines)


def _centred(di, raw):
    """Whether a line of the opening is centred on the 80-column screen as the Japanese has it."""
    return abs(di % 80 - (80 - len(raw)) // 2) <= 2


def _opening_room(kind, di, raw, box=None):
    """(max_cells, note) of a string of the opening."""
    if box:
        return box[1], "the opening: a character's name, one line, centred anew in the card's %d columns" % box[1]
    if kind == "records" and _centred(di, raw):
        return 80, "the opening: one line, centred anew"
    if kind == "records":
        return 80 - di % 80, "the opening: one line"
    if kind == "lines":
        return 80, "the opening's glossary page: one line"
    return len(raw), "the opening's mode label: one line, its room the Japanese's (one a letter)"


def opening_bytes(blocks, op, by_ref, name, ids, warn):
    """(the opening's text rebuilt in one block, [(an immediate's file offset, its block offset)])."""
    blob, moved = bytearray(), []
    for block in blocks:
        moved += [(r, len(blob)) for r in block["refs"]]
        for di, s, e in block["items"]:
            key = "%s:%04x" % (name, s)
            raw = op[s:e - 1]
            b = encode(by_ref[key], newlines=False) if key in by_ref else raw
            cells, _note = _opening_room(block["kind"], di, raw, block["box"])
            if key in by_ref and len(b) > cells:
                if block["kind"] == "string":
                    warn.append("%s: %d letters, past its room (%d)" % (ids[key], len(b), cells))
                else:
                    warn.append("%s: cut to its room (%d letters)" % (ids[key], cells))
                    b = b[:cells]
            if block["kind"] == "records":
                if key in by_ref and block["box"]:
                    di = di - di % 80 + block["box"][0] + (block["box"][1] - len(b)) // 2
                elif key in by_ref and _centred(di, raw):
                    di = di - di % 80 + max(0, (80 - len(b)) // 2)
                blob += struct.pack("<H", di)
            blob += b + b"\x00"
    return blob, moved


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    merged, order = {}, []

    def add(kind, jp, ref, cells, note=None):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], cells)
            if note and "note" not in merged[key]:
                merged[key]["note"] = note
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells}
        if note:
            merged[key]["note"] = note
        order.append(key)
    for name in scenes(vol, cfg):
        d = vol.read(_path(cfg, name))
        for s, e, ref in scene_strings(d):
            jp = decode(d[s:e - 1])
            if not ref:
                add("msg", jp, "%s:%04x" % (name, s), e - s - 1,
                    "at %s:%04x no mov si names it: there it keeps its own %d bytes (one a letter)" % (name, s, e - s - 1))
            else:
                add("msg", jp, "%s:%04x" % (name, s), LINE)
    exe = vol.read(_path(cfg, cfg["program"]))
    for s, e, refs, labels in program_strings(exe):
        if refs:
            add("engine", decode(exe[s:e - 1]), "%s:%04x" % (cfg["program"], s), LINE,
                "a message (the message window's, wrapped as the scenes' are)")
        elif labels:
            add("engine", decode(exe[s:e - 1]), "%s:%04x" % (cfg["program"], s), e - s - 1,
                "a menu's label: one line, its room the Japanese's (one a letter)")
        else:
            add("engine", decode(exe[s:e - 1]), "%s:%04x" % (cfg["program"], s), e - s - 1)
    if cfg.get("opening"):
        op = vol.read(_path(cfg, cfg["opening"]))
        for block in panther.opening_text(op):
            for di, s, e in block["items"]:
                cells, note = _opening_room(block["kind"], di, op[s:e - 1], block["box"])
                add("opening", decode(op[s:e - 1]), "%s:%04x" % (cfg["opening"], s), cells, note)
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


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = pseudo(e["id"], 2 * len(e["jp"]) + 8) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            if text:
                by_ref[r] = text
    warn, largest, done = [], 0, 0
    for name in scenes(vol, cfg):
        d = vol.read(_path(cfg, name))
        out = bytearray(d)
        changed = False
        for s, e, ref in scene_strings(d):
            key = "%s:%04x" % (name, s)
            if key not in by_ref:
                continue
            changed = True
            room = e - s - 1
            if not ref:
                b = encode(by_ref[key], newlines=True)
                if len(b) > room:
                    warn.append("%s: cut to its %d bytes (no mov si names it)" % (ids[key], room))
                    b = b[:room]
            else:
                b = encode(wrap(by_ref[key]))
            if len(b) <= room:
                out[s:e] = b + bytes(e - s - len(b))
            else:
                # (past its own bytes: at the scene's end, the mov si's pointed at it)
                at = len(out)
                out += b + b"\x00"
                for r in ref:
                    struct.pack_into("<H", out, r + 1, at)
                out[s:e] = bytes(e - s)
        if changed:
            if len(out) > panther.OVERLAY_MAX:
                raise SystemExit("%s: %d bytes, a scene may take 65535; shorten its strings" % (name, len(out)))
            vol.write(_path(cfg, name), bytes(out))
            done += 1
        largest = max(largest, len(out))
    exe = vol.read(_path(cfg, cfg["program"]))
    out, blob, moved = bytearray(exe), bytearray(), []
    for s, e, refs, labels in program_strings(exe):
        key = "%s:%04x" % (cfg["program"], s)
        if key not in by_ref:
            continue
        if refs or labels:
            b = encode(wrap(by_ref[key])) if refs else encode(by_ref[key], newlines=False)
            if not refs and len(b) > e - s - 1:
                warn.append("%s: %d letters, past its room (%d)" % (ids[key], len(b), e - s - 1))
            if len(b) <= e - s - 1:
                out[s:e] = b + bytes(e - s - len(b))
            else:
                # (past its own bytes: in the room put in after the data segment, the mov si's or mov bx's
                # pointed at it)
                moved += [(r, len(blob)) for r in refs + labels]
                blob += b + b"\x00"
                out[s:e] = bytes(e - s)
            continue
        b = encode(by_ref[key], newlines=False)
        room = e - s - 1
        if len(b) > room:
            warn.append("%s: cut to the program's room (%d bytes)" % (ids[key], room))
            b = b[:room]
        # (padded as the Japanese is: with spaces where it ends in spaces, else NUL)
        pad = b" " if exe[e - 2:e - 1] == b" " else b"\x00"
        out[s:e] = b + pad * (room - len(b)) + b"\x00"
    if blob:
        out, at = panther.grow_data(bytes(out), bytes(blob))
        out = bytearray(out)
        for r, o in moved:
            struct.pack_into("<H", out, r + 1, at + o)
    vol.write(_path(cfg, cfg["program"]), panther.patch_ham(bytes(out), largest))
    if cfg.get("opening"):
        # (the opening's text, all of it, in one block put in after its data segment, the immediates
        # naming its parts pointed at them)
        op = vol.read(_path(cfg, cfg["opening"]))
        blob, moved = opening_bytes(panther.opening_text(op), op, by_ref, cfg["opening"], ids, warn)
        op, at = panther.grow_data(op, bytes(blob), cfg["opening"])
        op = bytearray(op)
        for r, o in moved:
            struct.pack_into("<H", op, r, at + o)
        vol.write(_path(cfg, cfg["opening"]), panther.patch_hopen(bytes(op)))
    for w in warn:
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scenes rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
