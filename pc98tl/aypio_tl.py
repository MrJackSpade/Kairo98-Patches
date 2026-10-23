"""English for Aypio's Sex and Sex 2 (pc98tl/aypio.py): strings.json in, a patched disk out.

Strings:
* m (message): a message (01 C0h), any length: broken between words at 64 letters (Sex 2's window 48:
  game.json "width"; the program breaks a line by itself at the window's edge), 3 lines a window under a
  speaker's name (4 without one), the rest in more windows (the message's call made again); \\n a new
  line; {N1}.. a name and {S1}.. a word put in (keep each where it belongs), {C7} a colour, {W100} a wait
  (kept).
* n (name): a speaker's name (T1): up to 16 letters.
* w (word): a word a message puts in (T0, {S1}..): up to 16 letters.
* p (page): a page of text (U2): broken between words at 64 letters (48 in window 1); \\n a new line;
  %d, %s.. where a value goes (keep each, in order: a %s, a name, goes in \\K).
* c (choice): a menu's choice (W8): one line, max_cells letters.
* t (text): another text a script sets (01, into the text variables 20h-3Fh) or a save's label (U6):
  one line.
* f (format): a text shown with values put in (UC, Sex 2's build): broken between words at the window's;
  \\n a new line; %d, %3d.. where a value goes (keep each, in order).
* b (batch): a line INSTALL.BAT shows (echo; Sex 2's, which copies the game from the CD to a hard disk):
  one line, max_cells letters.
* e (program): UK2.EXE's own messages, and those of SOUNDSEL.EXE (Sex 2's sound board menu), in place:
  max_cells letters.

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
from . import engine_strings as ES
from . import starpt as S
from .text import pseudo

PREFIX = {"msg": "m", "name": "n", "insert": "w", "page": "p", "choice": "c", "text": "t", "format": "f",
          "batch": "b", "prog": "e"}
NOTE = {"msg": "a message: any length (broken between words, 3 lines a window under a speaker, more windows "
               "for the rest); \\n a new line; keep each {N1} (a name) and {S1} (a word) where it belongs",
        "name": "a speaker's name: up to 16 letters",
        "insert": "a word a message puts in ({S..}): up to 16 letters",
        "page": "a page of text: broken between words at its window's width; \\n a new line; keep each %d, %s.. "
                "(where a value goes) in order",
        "choice": "a menu's choice: one line, max_cells letters",
        "text": "a text a script sets: one line",
        "format": "a text shown with values put in: broken between words at the window's width; \\n a new line; "
                  "keep each %d, %3d.. (where a value goes) in order",
        "batch": "a line the installing batch file shows (echo): one line, max_cells letters",
        "prog": "the program's own message, in place: max_cells letters"}
ARCHIVES = ("DATALIB1.DLB", "DATALIB2.DLB", "DATALIB3.DLB", "DATALIB4.DLB")
WIDTH = 64                  # a message window's letters a line (Sex's; game.json "width" another's)
PAGE_WIDTH = {1: 48}        # a page's letters a line by its window (U2's first value; others 64)
SLOT = 20                   # a name's or a word's bytes (the tables' 21-byte entries)
KIND = {"T0": "insert", "T1": "name", "U2": "page", "W8": "choice", "U6": "text", "UC": "format"}
SPECS = ("page", "format")      # (texts given to a C format: their %d, %s.. are values' places)
FORMAT = re.compile(r"%[-+ 0#]*\d*(?:\.\d+)?[a-zA-Z]")
TRAIL = re.compile(rb"(?:\\r|\\C\d|\\W\d+)*$")


def _path(cfg, name):
    return cfg["dir"] + "/" + name


def _has(vol, path):
    try:
        return bool(vol.find(path))
    except FileNotFoundError:
        return False


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
            # (the texts set in the text variables 20h-3Fh (Sex's in 20h, Sex 2's menus' in 21h..): the
            # others are the name entry's characters; \\0 a mark)
            if A.is_file(b) or not 0x20 <= d[at + 1] < 0x40 or re.fullmatch(rb"\\.", b):
                continue
            kind = "text"
        elif cmd in KIND:
            kind = KIND[cmd]
        else:
            continue
        m = TRAIL.search(b)
        jp = A.show(b[:m.start()], table, kind in SPECS)
        if not JAPANESE.search(jp) or (kind in ("text", "format") and len(jp) < 2):
            continue
        if kind == "format" and not A.SPEC.search(b):     # (a piece of a label the command puts together)
            continue
        out.append((s, kind, (s, s + m.start()), False))
    return out


def scripts(vol, cfg):
    """[(archive, member, Script)]."""
    g = A.grammar(_program(vol, cfg)[1])
    out = []
    for arc in ARCHIVES:
        p = _path(cfg, arc)
        if not _has(vol, p):
            continue
        data = vol.read(p)
        for name, at, size in A.dlb(data):
            if name.lower().endswith(".mes"):
                out.append((arc, name, A.Script(data[at:at + size], g)))
    return out


def found(vol, cfg):
    """[(ref, kind, Japanese, max cells or None)]."""
    _exe, img = _program(vol, cfg)
    table = A.kana_table(img)
    out = []
    for arc, name, sc in scripts(vol, cfg):
        for s, kind, (a, b), _who in units(sc, table):
            jp = A.show(sc.d[a:b], table, kind in SPECS)
            room = {"name": 16, "insert": 16}.get(kind)
            if kind == "choice":
                room = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in jp)
            out.append(("%s:%s:%x" % (arc[7], name, s), kind, jp, room))
    for s, e in S.program_strings(bytes(img)):
        out.append(("E:%05x" % s, "prog", S.show(img[s:e]), e - s))
    for name in COMS:
        if _has(vol, _path(cfg, name)):
            com = vol.read(_path(cfg, name))
            for s, e in com_strings(com):
                out.append(("%s:%04x" % (name, s), "prog", S.show(com[s:e]), e - s))
    for name in EXES:
        if _has(vol, _path(cfg, name)):
            for a, b in exe_strings(vol.read(_path(cfg, name))):
                t = vol.read(_path(cfg, name))[a:b].decode("cp932")
                out.append(("%s:%04x" % (name, a), "prog", t, b - a))
    for name in BATCHES:
        if _has(vol, _path(cfg, name)):
            for n, t in batch_lines(vol.read(_path(cfg, name))):
                out.append(("%s:%d" % (name, n), "batch", t, BATCH_CELLS))
    return out


COMS = ("NAX.COM", "AYPIO.COM")     # the sound driver's and the floppy version's launcher's DOS messages
EXES = ("SOUNDSEL.EXE",)            # (Sex 2's sound board menu, before the game)
EXE_STRING = re.compile(rb"(?<=\0)(?:[\x81-\x9f\xe0-\xfc][\x40-\x7e\x80-\xfc]|[\x20-\x7e])+(?=\0)")
BATCHES = ("INSTALL.BAT",)          # (Sex 2's: it copies the game from the CD to a hard disk)
BATCH_CELLS = 79                    # a line of the text screen
BATCH_JAPANESE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uff66-\uff9f]")     # (half-width kana too)


def exe_strings(exe):
    """[(start, end)] of a C program's Japanese strings (each up to its 0; only all-JIS text, not code)."""
    out = []
    for m in EXE_STRING.finditer(exe):
        try:
            t = m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        # (kana, or two or more full-width characters and nothing else: code's bytes are rarely either)
        if re.search(r"[ぁ-ヶ]", t) or (len(t) >= 2 and JAPANESE.search(t) and all(ord(c) > 0x7F for c in t)):
            out.append((m.start(), m.end()))
    return out


def batch_lines(data):
    """[(line number, text)] of a batch file's echo lines with Japanese."""
    out = []
    for n, line in enumerate(data.decode("cp932", "replace").split("\r\n")):
        m = re.match(r"(?i)\s*echo[ .](.*)$", line)
        if m and BATCH_JAPANESE.search(m.group(1)):
            out.append((n, m.group(1)))
    return out
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


def _english(sc, s, kind, span, who, text, ident, warn, width=WIDTH):
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
    ls = A.lines(text, width)
    if kind == "page":
        return [pre + A.encode(A.lines(text, page_width(sc, sc.owner[s][0]))) + post]
    if kind == "format":
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


def page_window(sc, at):
    """The window a page (U2 at `at`) is shown in: its first value, a constant (87h 1Fh and a word)."""
    d = sc.d
    return d[at + 4] | d[at + 5] << 8 if d[at + 2] == 0x87 and d[at + 3] == 0x1F else None


def page_width(sc, at):
    return PAGE_WIDTH.get(page_window(sc, at), WIDTH)


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
        if mode == "pseudo" and e["kind"] in SPECS:          # (the values' places kept)
            text = " ".join([text] + FORMAT.findall(e["jp"]))
        for r in e["refs"]:
            by_ref[r] = (e, text)
    if not any(t for _e, t in by_ref.values()):
        img.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    warn = []
    sizes, calls = {}, {}
    table = A.kana_table(_program(vol, cfg)[1])
    g = A.grammar(_program(vol, cfg)[1])
    for arc in ARCHIVES:
        p = _path(cfg, arc)
        if not _has(vol, p):
            continue
        data = vol.read(p)
        members = {}
        for name, at, size in A.dlb(data):
            if not name.lower().endswith(".mes"):
                continue
            sc = A.Script(data[at:at + size], g)
            new = {}
            for s, kind, span, who in units(sc, table):
                e, text = by_ref.get("%s:%s:%x" % (arc[7], name, s), (None, ""))
                if text:
                    if kind in SPECS and FORMAT.findall(text) != FORMAT.findall(e["jp"]):
                        warn.append("%s: its %%d.. differ from the Japanese's" % e["id"])
                    new[s] = _english(sc, s, kind, span, who, text, e["id"], warn, cfg.get("width", WIDTH))
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
    if total > A.ROOM_MAX:
        raise SystemExit("the scripts %s take %d bytes together with their English, the program's room can "
                         "grow to %d; shorten their English" % (" > ".join(path), total, A.ROOM_MAX))
    exe, image = _program(vol, cfg)
    exe = bytearray(exe)
    hdr = int.from_bytes(exe[8:10], "little") * 16
    if total > A.LIMIT:
        # (the room grown to the deepest chain, a kilobyte at a time; MIN_MEM, the memory the program asks
        # for without EMS, by as much)
        room = min(-(-total // 1024) * 1024, A.ROOM_MAX)
        exe[hdr:] = A.set_room(bytes(exe[hdr:]), room)
        cp = _path(cfg, "UK2.CFG")
        if _has(vol, cp):
            conf = vol.read(cp)
            conf = re.sub(rb"(MIN_MEM\s*=\s*)(\d+)", lambda m: m.group(1) + str(int(m.group(2)) + room - A.LIMIT)
                          .encode("ascii"), conf)
            vol.write(cp, conf)
        print("the scripts' room grown from %d to %d bytes (%s)" % (A.LIMIT, room, " > ".join(path)))
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
        if not _has(vol, p):
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
    for name in EXES:
        p = _path(cfg, name)
        if not _has(vol, p):
            continue
        prog = bytearray(vol.read(p))
        changed = False
        for a, b in exe_strings(bytes(prog)):
            e, text = by_ref.get("%s:%04x" % (name, a), (None, ""))
            if not text:
                continue
            t = A.ascii_text(text).replace("\n", " ").encode("ascii")
            if len(t) > b - a:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(t), b - a))
                t = t[:b - a]
            prog[a:b] = t.ljust(b - a, b" ")
            changed = True
        if changed:
            vol.write(p, bytes(prog))
    for name in BATCHES:
        p = _path(cfg, name)
        if not _has(vol, p):
            continue
        bat = vol.read(p)
        values = {}
        for n, _t in batch_lines(bat):
            e, text = by_ref.get("%s:%d" % (name, n), (None, ""))
            if not text:
                continue
            t = A.ascii_text(text).replace("\n", " ")
            if len(t) > BATCH_CELLS:
                warn.append("%s: %d letters, the line holds %d" % (e["id"], len(t), BATCH_CELLS))
            values[n] = t
        if values:
            vol.write(p, ES.apply_batch(bat, values))
    vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
