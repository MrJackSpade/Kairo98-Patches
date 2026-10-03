"""Adv98V (Cocktail Soft / Fairytale) extract/patch driver.

The game's scripts are the MES/MEC files of its MES folder on the hard-disk
image (pc98tl/adv98v.py has the bytecode).  Text is runs of SJIS
characters (hiragana in one byte), ASCII/SJIS strings (21 ... 00) and text
breaks (A5) between them; a run is one string here.

* Messages flow in the current text frame (A6 x1 y1 x2 y2: x in half-width
  columns, y in pixels).  The engine wraps at the frame's right edge, even
  inside a word, and does not scroll: a fourth line of a 3-line frame draws
  over the first.  So English is written as ASCII strings (the engine draws
  them half-width), broken between words to the frame's width with A5, and
  cut into pages of the frame's line count; between pages goes a call of the
  file's message-end procedure (the procedure called most often right after
  a message: it waits for a key and clears the frame), as between the
  original messages.
* Menu items (the texts in the block after AD/AE) sit in boxes drawn for the
  Japanese, so they keep their width: two letters to a full-width cell, and
  longer ones are cut and reported.  So does text in a one-line frame.
* Encrypted segment tails (D5 with a key, later engines) are decrypted,
  read and written back encrypted.

* The hero's name is printed in the middle of a message by a procedure
  call between two text runs; the run after it carries on the same line,
  so it is wrapped from where the name ends, with room left for the
  longest name the name entry takes.  Called without its inline flag the
  same procedure prints a name tag that ends its line.
* Procedures (B9 n) are copied into a table of fixed slots, one per
  number; a body may run on into the free slots after it.  A name tag's
  procedure can only grow that far: game.json's proc_slot and proc_slots
  give the table (read off the engine's memory), and a build that would
  overrun a slot is refused.

game.json: {"title", "key", "image" (the HDI), "encoding": "adv98v",
            "game_dir", "extraop" (bool), "proc_slot" (bytes a procedure
            slot holds), "proc_slots" (slots in the table; both only for a game
            whose procedures hold text), "name_insert"
            ({"call": hex of the hero's name procedure call, "flag": hex of
            the register set that makes it print inline, "cols": the
            widest name part it prints}), "name_cols" (the widest name the
            name entry takes, where there is no name_insert), "base_scripts"
            (the scripts run before the scenes, in order, where the chain
            goes past the startup script the INI names), "hdd" and
            "drive_prefix" (a floppy set laid out on a hard disk, see
            pc98tl/illusion_game.py), "menu_fullwidth" (an engine whose
            menus take Shift-JIS only), "default_frame" (the message box
            the startup script sets, in force where a script sets none),
            "wait" (hex of the wait put before a page's message end, ""
            where the end procedure waits itself; default D1 1 3 0, which
            the oldest engines read differently), "boot_steps"}
Refs: "<file>:<n>" (n counts the file's text runs in order; a "c<k>." before
n for runs inside the k-th encrypted tail).
"""
import collections
import re
import json
import os
import struct

from .alice_sys2_tl import sha256
from .disk import DiskImage
from . import adv98v as av, engine_strings

TEXT = ("chr1", "chr2", "str")
LINE_H, GLYPH_H = 20, 16
WAIT = b"\xd1\x24\x26\x23"      # D1 1 3 0: wait for a key or click, as after a message
MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""


def _num(data, s):
    return av._num(data, s)


def _cmd(data, tok, code):
    return tok[0] == "cmd" and data[tok[1]] == code


def units(data, toks, proc_frames=None, frame=None):
    """[(first, end, kind, frame)] of the text runs: token index range,
    "msg" or "item", and the text frame (x1, y1, x2, y2) in force (set by
    A6, or by calling a procedure that sets one: proc_frames {number:
    frame}); frame: the one in force when the script starts."""
    out, i = [], 0
    menu_depth, proc_depth, depth = [], [], 0      # depths of open menu item / procedure blocks
    pending_menu = pending_proc = False
    while i < len(toks):
        k, s, e = toks[i]
        if k == "cmd" and data[s] == 0xA6:
            nums = [t for t in toks[i + 1:i + 5] if t[0] == "num"]
            if len(nums) == 4:
                frame = tuple(_num(data, t[1]) for t in nums)
        if k == "cmd" and data[s] == 0xBA and proc_frames and i + 1 < len(toks) and toks[i + 1][0] == "num":
            frame = proc_frames.get(_num(data, toks[i + 1][1])) or frame
        if k == "cmd" and data[s] in (0xAD, 0xAE):
            pending_menu = True
        if k == "cmd" and data[s] == 0xB9:
            pending_proc = True
        if k == "mark" and data[s] == 0xA2:
            depth += 1
            if pending_menu:
                menu_depth.append(depth)
                pending_menu = False
            elif pending_proc:
                proc_depth.append(depth)
                pending_proc = False
        elif k == "mark" and data[s] == 0xA3:
            if menu_depth and menu_depth[-1] == depth:
                menu_depth.pop()
            if proc_depth and proc_depth[-1] == depth:
                proc_depth.pop()
            depth -= 1
        if k in TEXT:
            j = i
            while j < len(toks) and (toks[j][0] in TEXT or (_cmd(data, toks[j], 0xA5) and j + 1 < len(toks)
                                                            and toks[j + 1][0] in TEXT)):
                j += 1
            # menu items keep their box; text in a procedure (a name tag) is
            # printed inline by its callers, so it is not wrapped or paged
            kind = "item" if menu_depth and menu_depth[-1] == depth else "inline" if proc_depth else "msg"
            out.append((i, j, kind, frame))
            i = j
            continue
        i += 1
    return out


def procs(data, toks):
    """{number: (body start, body end)} of the procedures a file defines
    (B9 n A2 ... A3): the body is what the engine copies to the
    procedure's slot, from after the A2 to its matching A3, both ends
    included."""
    out, x = {}, 0
    while x < len(toks):
        k, s, _e = toks[x]
        if k == "cmd" and data[s] == 0xB9 and x + 2 < len(toks) and toks[x + 1][0] == "num":
            y = x + 2
            depth = 0
            for z in range(y, len(toks)):
                kk, ss, _ee = toks[z]
                if kk == "mark" and data[ss] == 0xA2:
                    depth += 1
                elif kk == "mark" and data[ss] == 0xA3:
                    depth -= 1
                    if depth == 0:
                        break
            out[_num(data, toks[x + 1][1])] = (toks[y][2], toks[z][2])
            x = z
        x += 1
    return out


def proc_room(nums, start_nums, slot, slots):
    """{number: bytes} the procedure table gives each procedure a file
    defines: its slot and the free slots after it, up to the next
    procedure in force (this file's or the startup script's)."""
    live = sorted(set(nums) | set(start_nums))
    out = {}
    for n in nums:
        nxt = min([m for m in live if m > n] + [slots])
        out[n] = slot * (nxt - n)
    return out


def unit_text(data, toks, i, j):
    out = []
    for k, s, e in toks[i:j]:
        if k == "cmd":
            out.append("\n")
        elif k == "str":
            body = bytes(data[s + 1:e - 1] if data[e - 1] in (0, 0xFF) else data[s + 1:e])
            out.append(body.decode("cp932", "replace"))
        elif k == "chr2" and (data[s] >= 0xEB or _undecodable(data[s:e])):
            out.append("{U%02x%02x}" % (data[s], data[s + 1]))       # a PC-98 own character
        else:
            out.append(av.char_text(data, k, s, e))
    return "".join(out)


def _undecodable(b):
    try:
        bytes(b).decode("cp932")
        return False
    except UnicodeDecodeError:
        return True


def unit_cells(data, toks, i, j):
    """Width in full-width cells: a two-byte character is one, a one-byte
    one half."""
    half = 0
    for k, s, e in toks[i:j]:
        if k in ("chr1", "chr2"):
            half += 2
        elif k == "str":
            body = bytes(data[s + 1:e])
            n = 0
            while n < len(body) and body[n] not in (0, 0xFF):
                if 0x81 <= body[n] <= 0x9F or 0xE0 <= body[n] <= 0xEF:
                    half, n = half + 2, n + 2
                else:
                    half, n = half + 1, n + 1
    return -(-half // 2)


def end_proc(data, toks, effects=None):
    """The file's message-end procedure: the BA call that most often
    follows a message within a few tokens; None when there is none.
    With effects (resolve_effects), only a procedure that clears the
    text counts (a game may call one that prints an ellipsis first)."""
    seen = collections.Counter()
    for _i, j, kind, _f in units(data, toks):
        if kind != "msg":
            continue
        for x in range(j, min(j + 12, len(toks) - 1)):
            k, s, _e = toks[x]
            if k == "cmd" and data[s] == 0xBA and toks[x + 1][0] == "num":
                call = bytes(data[s:toks[x + 1][2]])
                if effects is not None and effects.get(_call_num(call), ("none",))[0] != "reset":
                    continue
                seen[call] += 1
                break
            if k in TEXT:
                break
    return max((c, b) for b, c in seen.items())[1] if seen else None


def _subdir(vol, game_dir, kind):
    """The game folder's subfolder for scripts or modules ("MES", "TCM"):
    named so, or ending in "_MES" ("GIBO_MES"); None if there is none."""
    for e in vol.listdir(vol.find(game_dir)["cluster"]):
        if e["is_dir"] and (e["name"].upper() == kind or e["name"].upper().endswith("_" + kind)):
            return game_dir + "/" + e["name"]
    return None


def mes_path(vol, game_dir, name):
    return _subdir(vol, game_dir, "MES") + "/" + name


def inline_end(data, toks, us=None, wait=WAIT):
    """A file's message end written out after its messages instead of a
    procedure call: the commands most often right after a message, up to
    and including a text reset (AA n); with the window close (AB) among
    them they wait for a key themselves, else a wait goes first.  None
    when the file has none."""
    seen = collections.Counter()
    for _i, j, kind, _f in us if us is not None else units(data, toks):
        if kind != "msg":
            continue
        x = j
        while x < len(toks) and toks[x][0] in ("cmd", "num") and x - j < 8:
            if toks[x][0] == "cmd" and data[toks[x][1]] == 0xAA and x + 1 < len(toks) and toks[x + 1][0] == "num":
                seen[bytes(data[toks[j][1]:toks[x + 1][2]])] += 1
                break
            x += 1
    if not seen:
        return None
    seq = max((c, b) for b, c in seen.items())[1]
    return seq if seq[0] == 0xAB else wait + seq


def _files(vol, game_dir):
    """The MES folder's scripts: [(name, path)]."""
    mes = _subdir(vol, game_dir, "MES")
    return [(e["name"], mes + "/" + e["name"]) for e in vol.listdir(vol.find(mes)["cluster"])
            if not e["is_dir"] and e["name"].upper().endswith((".MES", ".MEC"))]


def start_script(vol, game_dir, extraop):
    """The script the engine runs first: the one the game's INI (itself a
    script, its tail often encrypted; in the game folder or one below)
    names, else START.MES."""
    inis = []
    for e in vol.listdir(vol.find(game_dir)["cluster"]):
        if e["is_dir"] and e["name"] not in (".", ".."):
            inis += [game_dir + "/" + e["name"] + "/" + f["name"] for f in vol.listdir(e["cluster"])
                     if not f["is_dir"] and f["name"].upper().endswith(".INI")]
        elif e["name"].upper().endswith(".INI"):
            inis.insert(0, game_dir + "/" + e["name"])
    for ini in inis:
        for _tag, data, _toks in _streams(vol.read(ini), extraop):
            m = re.search(rb'"(?:[a-z]:)?\\?(?:\w+_)?mes\\([^"\\]+\.mes)"', data, re.I)
            if m:
                return m.group(1).decode("cp932").upper()
    return "START.MES"


def _streams(data, extraop):
    """[(tag, bytes, tokens)]: the file itself and its decrypted tails."""
    toks = av.tokenize(data, extraop)
    out = [("", data, toks)]
    for n, (k, s, e) in enumerate([t for t in toks if t[0] == "crypt"]):
        key = _num(data, [t for t in toks if t[2] == s][0][1])
        inner = av.decrypt(data[s:e], key)
        out.append(("c%d." % n, inner, av.tokenize(inner, extraop)))
    return out


PROGRAM_EXT = (".COM", ".EXE", ".OV1", ".OVL", ".TCM")
_HERO = re.compile(rb"@\d+='([^']+)'")


def _programs(vol, game_dir):
    """The engine's program files (the game folder's and its TCM modules'):
    [(name, path)]."""
    out = []
    tcm = _subdir(vol, game_dir, "TCM")
    for folder in [game_dir] + ([tcm] if tcm else []):
        prefix = folder[len(game_dir) + 1:] + "/" if folder != game_dir else ""
        out += [(prefix + e["name"], folder + "/" + e["name"]) for e in vol.listdir(vol.find(folder)["cluster"])
                if not e["is_dir"] and e["name"].upper().endswith(PROGRAM_EXT)]
    return out


def _is_table(text):
    """A character table the name entry picks from by position: kana,
    full-width letters and Japanese punctuation without kanji, or kana in
    code order (a stray code byte may sit before it)."""
    body = [c for c in text if c != "　"]
    if len(body) >= 20 and all("、" <= c <= "ヿ" or "！" <= c <= "～" for c in body):
        return True
    # tables list kana in code order: six or more rising kana in a row
    run = best = 0
    for prev, c in zip([""] + body, body):
        kana = "ぁ" <= c <= "ヶ"
        run = run + 1 if kana and prev and "ぁ" <= prev <= "ヶ" and c > prev else (1 if kana else 0)
        best = max(best, run)
    return best >= 6


def program_strings(exe):
    """[(start, end, text)] of the Japanese in a program, with rows of
    labels split at their full-width spaces so each label keeps its place
    (the name window picks a label by where it is clicked)."""
    out = []
    for s, e, text in engine_strings.find(exe):
        if _is_table(text):
            continue
        pos, piece, at = s, "", s
        for ch in text + "　":
            n = len(ch.encode("cp932"))
            if ch == "　":
                if piece.strip():
                    out.append((at, pos, piece))
                piece, at = "", pos + n
            else:
                piece += ch
            pos += n
    return out


def _all_japanese(raw):
    """An argument that is Japanese text only (a name entry's default)."""
    try:
        text = raw.decode("cp932")
    except UnicodeDecodeError:
        return False
    return bool(text) and all(ord(c) >= 0x3000 for c in text)


def var_strings(vol, game_dir, extraop, entry_cols):
    """{file name: [(start, end, text, room, pad)]}: the values the scripts give
    string variables (@n='...' in an argument: the hero's default name,
    item names, picture titles), and the name entry's defaults (an
    argument holding just one of them, or just Japanese text).  room is the bytes a value may
    take: its own length, or the name entry's width for the names it
    offers; a value inside a procedure keeps its length, as the
    procedure's slot is fixed.  pad: a shorter English value is padded
    with spaces to the old length (lists and menus drawn from the
    variable); a name the player can change is not."""
    files = [(name, vol.read(path)) for name, path in _files(vol, game_dir)]
    values, offered = set(), set()
    for _name, data in files:
        for k, s, e in av.tokenize(data, extraop):
            if k == "arg":
                values |= {m.group(1) for m in _HERO.finditer(data[s:e])}
    for _name, data in files:
        for k, s, e in av.tokenize(data, extraop):
            if k == "arg" and bytes(data[s + 1:e - 1]) in values:
                offered.add(bytes(data[s + 1:e - 1]))
    out = {}
    for name, data in files:
        toks = av.tokenize(data, extraop)
        bodies = list(procs(data, toks).values())
        found = []
        for k, s, e in toks:
            if k != "arg":
                continue
            spans = [(s + m.start(1), s + m.end(1)) for m in _HERO.finditer(data[s:e])]
            inner = bytes(data[s + 1:e - 1])
            if inner in values or _all_japanese(inner):
                spans.append((s + 1, e - 1))
                offered.add(inner)
            for a, b in spans:
                raw = bytes(data[a:b])
                if not raw.decode("cp932").strip("　 "):
                    continue
                room = max(len(raw), entry_cols) if raw in offered else len(raw)
                if any(bs <= a < be for bs, be in bodies):
                    room = len(raw)
                found.append((a, b, raw.decode("cp932"), room, raw not in offered))
        if found:
            out[name] = sorted(found)
    return out


def mec_rooms(vol, game_dir, extraop):
    """{file name: bytes}: the room of each file the scripts load into the
    engine's MEC buffer (C0 "file" offset: the file goes in at that byte
    offset, beside the others loaded at other offsets).  A file may take up to the next higher offset any script loads at, or,
    loaded at the top, up to the furthest the original game's loads
    reach (past that the buffer meets the engine's stack); never less
    than its own size."""
    sizes = {name.upper(): len(vol.read(path)) for name, path in _files(vol, game_dir)}
    loads = []
    for _name, path in _files(vol, game_dir):
        for _tag, data, toks in _streams(vol.read(path), extraop):
            for x, (k, s, _e) in enumerate(toks[:-2]):
                if k == "cmd" and data[s] == 0xC0 and toks[x + 1][0] == "arg" and toks[x + 2][0] == "num":
                    arg = bytes(data[toks[x + 1][1] + 1:toks[x + 1][2] - 1]).decode("cp932")
                    target = arg.replace("\\", "/").split("/")[-1].upper()
                    if target in sizes:
                        loads.append((target, _num(data, toks[x + 2][1])))
    if not loads:
        return {}
    top = max(off + sizes[t] for t, off in loads)
    offsets = sorted({off for _t, off in loads})
    rooms = {}
    for t, off in loads:
        nxt = min([o for o in offsets if o > off] + [top])
        rooms[t] = min(rooms.get(t, nxt - off), nxt - off)
    return {t: max(r, sizes[t]) for t, r in rooms.items()}


def _image(cfg, src):
    """(image, cfg): the source image, or for a floppy set too small for
    the English ("hdd" in game.json) the game laid out on a hard disk
    (pc98tl/illusion_game.py _hdd_install), game_dir its install folder."""
    if cfg.get("hdd"):
        from .illusion_game import _hdd_install
        return _hdd_install(cfg, src)
    return DiskImage(src), cfg


def strip_drives(data, extraop, prefixes):
    """A script with the drive prefixes of its file names ("a:", "b:":
    floppy drives) mapped as installed (game.json "drive_prefix")."""
    if not prefixes:
        return data
    out, pos = bytearray(), 0
    for k, s, e in av.tokenize(data, extraop):
        if k != "arg":
            continue
        inner = bytes(data[s + 1:e - 1])
        for old, new in prefixes.items():
            if inner.lower().startswith(old.lower().encode("ascii")):
                out += data[pos:s + 1] + new.encode("ascii") + inner[len(old):]
                pos = e - 1
                break
    return bytes(out + data[pos:])


# ---- extraction ------------------------------------------------------------------------------
def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    img, cfg = _image(cfg, src)
    vol = img.volumes[0]
    merged, order = {}, []
    for name, path in _files(vol, cfg["game_dir"]):
        data = vol.read(path)
        for tag, d, toks in _streams(data, cfg.get("extraop", False)):
            for n, (i, j, kind, frame) in enumerate(units(d, toks)):
                jp = unit_text(d, toks, i, j)
                if not jp.strip():
                    continue
                cells = unit_cells(d, toks, i, j)
                key = (kind, jp)
                ref = "%s:%s%d" % (name, tag, n)
                if key in merged:
                    merged[key]["refs"].append(ref)
                    merged[key]["max_cells"] = max(merged[key]["max_cells"], cells)
                    continue
                merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells}
                order.append(key)
    extra = [("var", name, "v%d" % n, s, e, text, room // 2)
             for name, found in var_strings(vol, cfg["game_dir"], cfg.get("extraop", False),
                                            cfg.get("name_cols", cfg.get("name_insert", {}).get("cols", 0))).items()
             for n, (s, e, text, room, _pad) in enumerate(found)]
    for name, path in _programs(vol, cfg["game_dir"]):
        extra += [("engine", name, "%04x" % s, s, e, text, (e - s) // 2)
                  for s, e, text in program_strings(vol.read(path))]
    for kind, name, at, _s, _e, jp, cells in extra:
        key = (kind, jp)
        if key not in merged:
            merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [], "max_cells": cells}
            order.append(key)
        merged[key]["refs"].append("%s:%s" % (name, at))
        merged[key]["max_cells"] = min(merged[key]["max_cells"], cells)
    prefix = {"msg": "m", "item": "i", "inline": "n", "var": "v", "engine": "e"}
    counters, strings = {}, []
    for key in order:
        e = merged[key]
        counters[e["kind"]] = counters.get(e["kind"], 0) + 1
        strings.append({"id": "%s%05d" % (prefix[e["kind"]], counters[e["kind"]]), **e})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                e["en"] = prev.get("en", "")
                if "note" in prev:
                    e["note"] = prev["note"]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def roundtrip(src, cfg):
    """Every script rebuilt from its tokens, its tails re-encrypted,
    matches the disk."""
    img, cfg = _image(cfg, src)
    vol = img.volumes[0]
    for _name, path in _files(vol, cfg["game_dir"]):
        data = vol.read(path)
        toks = av.tokenize(data, cfg.get("extraop", False))
        if b"".join(data[s:e] for _k, s, e in toks) != data:
            return False
        for tag, inner, itoks in _streams(data, cfg.get("extraop", False))[1:]:
            if b"".join(inner[s:e] for _k, s, e in itoks) != inner:
                return False
    return True


# ---- patch -----------------------------------------------------------------------------------
_SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "¥": "\\"}


_UTOK = re.compile(r"\{U([0-9a-f]{4})\}")


def _fullwidth(text, cells):
    """A menu item as full-width Shift-JIS, one character a cell, cut and
    padded to cells."""
    out = ""
    for ch in "".join(_SUBST.get(c, c) for c in text):
        if ch == " ":
            ch = "　"
        elif 0x21 <= ord(ch) < 0x7F:
            ch = chr(ord(ch) + 0xFEE0)
        try:
            ch.encode("cp932")
        except UnicodeEncodeError:
            ch = "？"
        out += ch
    return out[:cells].ljust(cells, "　").encode("cp932")


def _encode(text):
    """A line as a 21 string: ASCII as it is, {Uxxxx} as those SJIS bytes,
    anything else as SJIS."""
    out = b""
    for n, part in enumerate(_UTOK.split(text)):
        out += bytes.fromhex(part) if n % 2 else _plain(part)
    return b"\x21" + out + b"\x00"


def _plain(text):
    out = b""
    for ch in "".join(_SUBST.get(c, c) for c in text):
        if 0x20 <= ord(ch) < 0x7F:
            out += ch.encode("ascii")
        else:
            try:
                out += ch.encode("cp932")
            except UnicodeEncodeError:
                out += b"?"
    return out


def _width(text):
    w = 0
    for ch in _UTOK.sub("　", text):
        w += 1 if ord(ch) < 0x80 or 0xFF61 <= ord(ch) <= 0xFF9F else 2
    return w


def wrap(text, cols, col=0):
    """Lines of at most cols columns, broken between words; the first line
    starts at column col (an empty first line: nothing fits there)."""
    lines, room = [], cols - col
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = (line + " " + word) if line else word
            if _width(cand) <= room or (not line and (room == cols or lines)):
                line = cand
            elif not line:
                lines.append("")                # the first word does not fit after col
                line = word
            else:
                lines.append(line)
                line = word
            if lines:
                room = cols
        lines.append(line)
        room = cols
    return lines


def frame_size(frame):
    """(columns, lines) of a text frame; None: unknown."""
    if not frame:
        return None
    x1, y1, x2, y2 = frame
    return x2 - x1, max(1, (y2 - y1 - GLYPH_H) // LINE_H + 1)


def build(text, kind, frame, cells, brk, warn, sid, start=(0, 0), reserve=0, down=0, max_cols=None,
          max_rows=None, fullwidth=False):
    """English for a text run: (the bytes to put in its place, the (line,
    column) it ends at).  A message starts at start (line, column) of its
    page and leaves reserve columns at its end for what is printed after
    it on its line; down: the lines what follows moves on before the next
    text (which must stay inside the frame); max_cols, max_rows: a
    narrower width and fewer lines than the frame's to keep to;
    fullwidth: menu items written as full-width characters (older
    engines draw a menu from Shift-JIS only, and crash on an ASCII
    string in one)."""
    size = frame_size(frame)
    if kind in ("item", "inline", "label") or not size or size[1] == 1:
        # text in a one-line frame often has more drawn after it on the
        # line (an input field, numbers), so it keeps its Japanese width
        # (a label placed on the screen, too)
        room = 2 * cells if kind == "item" or not size else size[0] if kind == "inline" else min(size[0], 2 * cells)
        flat = " ".join(text.split("\n"))
        if _width(flat) > room:
            warn.append("%s: %d columns, the box has %d" % (sid, _width(flat), room))
            out, w = "", 0
            for ch in flat:
                if w + _width(ch) > room:
                    break
                out, w = out + ch, w + _width(ch)
            flat = out
        if kind == "item" and fullwidth:
            return _fullwidth(" ".join(text.split("\n")), cells), None
        if kind == "item":
            flat = flat.ljust(room)
        return _encode(flat), None
    cols, rows = size
    if max_cols:
        cols = min(cols, max_cols)
    if max_rows:
        rows = min(rows, max_rows)
    row, col = start
    if col >= cols:
        row, col = row + 1, 0
    lead = b""
    if row >= rows:
        # carried past the frame's last line (line breaks after a full
        # page): a new page first, or it would draw over the first line
        lead, row, col = (brk or b""), 0, 0
    lines = wrap(text, cols, col)
    # the first page has the lines left below the start row
    first = rows - row
    pages = [lines[:first]] + [lines[k:k + rows] for k in range(first, len(lines), rows)]
    pages = [p for p in pages if p]
    if len(pages) > 1 and not brk:
        warn.append("%s: %d lines, the frame shows %d and this file has no message end to page with"
                    % (sid, len(lines), rows))
        pages = [lines]
    end_row = (row if len(pages) == 1 else 0) + len(pages[-1]) - 1
    end_col = _width(pages[-1][-1]) + (col if len(pages) == 1 and len(pages[-1]) == 1 else 0)
    body = [b"\xa5".join(_encode(ln) if ln else b"" for ln in page) for page in pages]
    out = lead + (brk.join(body) if brk else body[0])
    if reserve and end_col + reserve > cols:
        # what follows on this line (the hero's name) goes to the next one
        if end_row + 1 < rows or not brk:
            out, end_row, end_col = out + b"\xa5", end_row + 1, 0
        else:
            out, end_row, end_col = out + brk, 0, 0
    if down and brk and end_row + down >= rows:
        # what follows (a name tag, line breaks) would leave the frame: it
        # opens the next page instead
        out, end_row, end_col = out + brk, 0, 0
    return out, (end_row, end_col)


def patch_stream(data, toks, tag, name, by_ref, ids, proc, warn, table, insert=None, fit=False, effects=None,
                 frames=None, fallback=None, fullwidth=False, default_frame=None, wait=WAIT):
    """The stream with its text runs replaced.  table: (slot bytes, slot
    count, the startup script's procedure numbers).  A procedure body may grow to
    the larger of its own length and its room in the procedure table;
    past that it would overwrite a procedure in force, so the build is
    refused, or with fit (the --pseudo filler) the body's texts are cut
    to fit.  With no table (a game whose procedures hold no text, so it
    was not measured) a procedure may not grow."""
    defs = procs(data, toks)
    room = proc_room(defs, table[2], table[0], table[1]) if table else {}
    limit = {n: max(e - s, room.get(n, 0)) for n, (s, e) in defs.items()}
    reps = {}
    us = units(data, toks, frames, default_frame)
    starts = [_start(data, toks, i, proc, insert, effects or {}) for i, _j, _k, _f in us]
    # a page break: a wait and the message-end procedure, or the file's
    # own message end where it has none
    brk = (wait + proc) if proc else inline_end(data, toks, us, wait) or fallback
    end = None                          # where the last message replaced ended
    for n, (i, j, kind, frame) in enumerate(us):
        ref = "%s:%s%d" % (name, tag, n)
        text = by_ref.get(ref)
        if text is None:
            end = None
            continue
        cont, down, col, _need, located = starts[n]
        # a message after text on its page starts where that text ended,
        # moved on by what was printed between
        start = ((end[0] + down, col) if down else (end[0], end[1] + col)) if cont and end else (down, col)
        # room for what is printed after it on its line (a name, an
        # ellipsis), and the lines that moves on before more text
        reserve, down, follows = _after(data, toks, j, proc, insert, effects or {})
        down = down if follows else 0
        s, e = toks[i][1], toks[j - 1][2]
        # a question with a menu after it keeps to its Japanese lines'
        # width: the menu's window is drawn over the frame's right side
        # and its Japanese line count (the menu may sit on the frame's next
        # line; longer English pages first)
        narrow = _line_cols(data, toks, i, j) if _menu_follows(data, toks, j) else None
        lines = 1 + sum(1 for k, s2, _e in toks[i:j] if k == "cmd" and data[s2] == 0xA5) if narrow else None
        bkind = kind
        if located and kind == "inline":
            bkind = "label"         # a marker placed by a procedure (the wait arrow)
        if located and kind == "msg":
            # placed text: a label at its Japanese width, or, with lines
            # of its own, a message starting where it is placed
            x, y = located
            if lines is None and any(k == "cmd" and data[s2] == 0xA5 for k, s2, _e in toks[i:j]) and frame                     and x is not None and x >= frame[0] and y >= frame[1]:
                start = ((y - frame[1]) // LINE_H, x - frame[0])
            else:
                bkind = "label"
        new, end = build(text, bkind, frame, unit_cells(data, toks, i, j),
                         brk, warn, ids.get(ref, ref), start, reserve, down, narrow, lines, fullwidth)
        reps[s] = (e, ids.get(ref, ref), new)
    for pn, (bs, be) in defs.items():
        inside = sorted(s for s in reps if bs <= s < be)
        grown = (be - bs) + sum(len(reps[s][2]) - (reps[s][0] - s) for s in inside)
        if grown <= limit[pn]:
            continue
        if not fit:
            raise SystemExit("%s%s: procedure %d would be %d bytes, it may take %d (strings %s); shorten them"
                             % (name, tag and " " + tag, pn, grown, limit[pn], ", ".join(reps[s][1] for s in inside)))
        # each text gets its old bytes and an even share of the room left
        spare = limit[pn] - (be - bs)
        for s in inside:
            e, sid, new = reps[s]
            keep = max(1, (e - s) + spare // len(inside) - 2)
            reps[s] = (e, sid, new[:1 + keep] + b"\x00" if len(new) > keep + 2 else new)
    out, pos = bytearray(), 0
    for s in sorted(reps):
        e, _sid, new = reps[s]
        out += data[pos:s] + new
        pos = e
    out += data[pos:]
    return bytes(out)


def proc_frames(data, toks):
    """{number: frame} of the procedures a stream defines: the text frame
    a procedure sets (the last A6 in the body), or None (so a definition
    that sets none replaces one from another file that does)."""
    out = {}
    for pn, (bs, be) in procs(data, toks).items():
        out[pn] = None
        for x, (k, s, _e) in enumerate(toks):
            if bs <= s < be and k == "cmd" and data[s] == 0xA6:
                nums = [t for t in toks[x + 1:x + 5] if t[0] == "num"]
                if len(nums) == 4:
                    out[pn] = tuple(_num(data, t[1]) for t in nums)
    return out


def proc_effects(data, toks, name, tag, by_ref, proc, name_cols=0):
    """{number: facts} of the procedures a stream defines, read off their
    bodies, for resolve_effects: the columns of text they print (the
    Japanese's or the English's, the wider; a string variable shown with
    "DISP @n" counts as a name of name_cols), their line breaks (A5),
    whether they set the frame or clear the text (A6, AA, AB, or a call
    of the message-end procedure), and the procedures they call."""
    defs = procs(data, toks)
    starts = {t[1]: x for x, t in enumerate(toks)}
    us = units(data, toks)
    out = {}
    for pn, (bs, be) in defs.items():
        x, body = starts.get(bs), []
        while x is not None and x < len(toks) and toks[x][1] < be:
            body.append(x)
            x += 1
        cmds = [data[toks[y][1]] for y in body if toks[y][0] == "cmd"]
        calls = [bytes(data[toks[y][1]:toks[y + 1][2]]) for y in body
                 if toks[y][0] == "cmd" and data[toks[y][1]] == 0xBA and y + 1 < len(toks)]
        width = sum(name_cols for y in body if toks[y][0] == "arg"
                    and _DISP.match(bytes(data[toks[y][1]:toks[y][2]])))
        for n, (i, j, _kind, _f) in enumerate(us):
            if bs <= toks[i][1] < be:
                en = by_ref.get("%s:%s%d" % (name, tag, n))
                width += max(2 * unit_cells(data, toks, i, j), _width(" ".join(en.split("\n"))) if en else 0)
        out[pn] = {"width": width, "breaks": cmds.count(0xA5),
                   "reset": bool(set(cmds) & {0xA6, 0xAA, 0xAB}) or (proc is not None and proc in calls),
                   "calls": [_call_num(c) for c in calls]}
    return out


_DISP = re.compile(rb'^"DISP @\d+"$')


def resolve_effects(layers):
    """{number: effect} in force on the text cursor, from layers of
    proc_effects facts (later ones over earlier ones), with what a
    procedure calls counted as its own: ("tag", columns) prints text and
    ends its line (a speaker's name tag); ("insert", columns) prints text
    on the line; ("reset",) sets the frame or clears the text; ("break",
    n) only breaks the line n times; ("none",) leaves the cursor alone
    (pictures, sounds, flags)."""
    facts = {}
    for layer in layers:
        facts.update(layer)

    def total(pn, seen):
        f = facts.get(pn)
        if f is None or pn in seen:
            return 0, 0, False
        width, breaks, reset = f["width"], f["breaks"], f["reset"]
        for c in f["calls"]:
            w, b, r = total(c, seen | {pn})
            width, breaks, reset = width + w, breaks + b, reset or r
        return width, breaks, reset

    eff = {}
    for pn in facts:
        width, breaks, reset = total(pn, frozenset())
        if reset:
            eff[pn] = ("reset",)
        elif width:
            eff[pn] = ("tag", width) if breaks else ("insert", width)
        elif breaks:
            eff[pn] = ("break", breaks)
        else:
            eff[pn] = ("none",)
    return eff


def _call_num(call):
    return av._num(call, 1) if len(call) > 1 else None


def _start(data, toks, i, proc, insert, effects):
    """Where a message starts: (continues, lines, column, need, located).  Looking
    back from the message to the last text, or to a page end or frame
    reset (the message-end procedure, A6, AA, or a procedure that does
    those), and then forward over what lies between:

    * a line break (A5, or a procedure of breaks) moves to the next line;
    * a speaker's name tag (a procedure printing text and ending its line)
      prints on the line, then moves to the next;
    * a procedure printing text without a break (the hero's name: the
      name procedure with its inline flag set, insert: (call bytes, flag
      bytes, columns); or a fixed text) moves along the line.

    After text the message continues that text's page (continues: True):
    lines down from where the text ended, at column (column: past where
    it ended when lines is 0); need is what is printed on that text's
    last line before the first line change, which the text leaves room
    for.  Where the text before is in another branch of a block this
    pages sooner than needed, never later.  After a page end the message
    starts lines down a fresh page.  located: (x, y) of a cursor
    placement (A7 x y) that comes first: the text is placed on the screen
    there."""
    gap, stop = _gap(data, toks, i, -1, proc, insert, effects)
    lines, cols, need = _layout(data, gap, insert, effects)
    located = None
    for y, (k, s, _e) in enumerate(gap):
        if k == "cmd" and data[s] == 0xA7:
            nums = [t for t in gap[y + 1:y + 3] if t[0] == "num"]
            located = tuple(_num(data, t[1]) for t in nums) if len(nums) == 2 else (None, None)
    return stop == "text", lines, cols, need, located


def _menu_follows(data, toks, j):
    """Whether a menu (AD/AE) comes after a text run before more text."""
    for k, s, _e in toks[j:j + 24]:
        if k in TEXT:
            return False
        if k == "cmd" and data[s] in (0xAD, 0xAE):
            return True
    return False


def _line_cols(data, toks, i, j):
    """The widest line of a text run's Japanese, in half-width columns."""
    widest, start = 0, i
    for x in range(i, j + 1):
        if x == j or (toks[x][0] == "cmd" and data[toks[x][1]] == 0xA5):
            widest = max(widest, 2 * unit_cells(data, toks, start, x))
            start = x + 1
    return widest


def _after(data, toks, j, proc, insert, effects):
    """What follows a text run up to the next text or page end: (need,
    lines, text follows) as in _start, read forward."""
    gap, stop = _gap(data, toks, j, 1, proc, insert, effects)
    lines, _cols, need = _layout(data, gap, insert, effects)
    return need, lines, stop == "text" and not any(k == "cmd" and data[s] == 0xA7 for k, s, _e in gap)


def _gap(data, toks, at, step, proc, insert, effects):
    """The tokens from at (back from before it, or on from it) to the
    nearest text or page end: (tokens in order, "text"/"reset"/None)."""
    gap, x, stop = [], at - 1 if step < 0 else at, None
    while 0 <= x < len(toks) and abs(x - at) <= 32:
        k, s, _e = toks[x]
        if k in TEXT:
            stop = "text"
            break
        if k == "cmd" and data[s] in (0xA6, 0xAA, 0xAB):
            stop = "reset"
            break
        if k == "cmd" and data[s] == 0xBA and x + 1 < len(toks) and toks[x + 1][0] == "num":
            call = bytes(data[s:toks[x + 1][2]])
            if call == proc or (not (insert and call == insert[0])
                                and effects.get(_call_num(call), ("none",))[0] == "reset"):
                stop = "reset"
                break
        gap.append(toks[x])
        x += step
    if step < 0:
        gap.reverse()
    return gap, stop


def _layout(data, gap, insert, effects):
    """(lines, column, need) after what a gap prints: see _start."""
    lines, cols, need, flag = 0, 0, 0, False

    def advance(width, down):
        nonlocal lines, cols, need
        if not lines:
            need += width
        if down:
            lines, cols = lines + down, 0
        else:
            cols += width

    for y, (k, s, e) in enumerate(gap):
        if insert and bytes(data[s:e]) == insert[1]:
            flag = True
        elif k == "cmd" and data[s] == 0xA5:
            advance(0, 1)
        elif k == "cmd" and data[s] == 0xBA and y + 1 < len(gap):
            call = bytes(data[s:gap[y + 1][2]])
            eff = effects.get(_call_num(call), ("none",))
            if insert and call == insert[0]:
                if flag:
                    advance(insert[2], 0)
                else:
                    advance(eff[1] if eff[0] == "tag" else 0, 1)
                flag = False
            elif eff[0] == "insert":
                advance(eff[1], 0)
            elif eff[0] == "tag":
                advance(eff[1], 1)
            elif eff[0] == "break":
                advance(0, eff[1])
    return lines, cols, need


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img, cfg = _image(cfg, src)
    vol = img.volumes[0]
    by_ref, ids, warn = {}, {}, []
    for e in doc["strings"]:
        text = e["en"]
        if mode == "pseudo":
            fixed = e["kind"] in ("item", "var", "engine")
            text = pseudo(e["id"], 2 * e["max_cells"], 1.0 if fixed else 2.5)
            if fixed:
                text = text[:2 * e["max_cells"]]
        if not text:
            continue
        for r in e["refs"]:
            by_ref[r] = text
            ids[r] = e["id"]
    extraop = cfg.get("extraop", False)
    for _name, path in _files(vol, cfg["game_dir"]):
        data = vol.read(path)
        moved = strip_drives(data, extraop, cfg.get("drive_prefix"))
        if moved != data:
            vol.write(path, moved)
    # the scripts run before the scenes, in order (the startup script and
    # what it chains to): their procedures are in force in every scene
    # that does not define its own
    base = [n.upper() for n in cfg.get("base_scripts", [start_script(vol, cfg["game_dir"], extraop)])]
    name_cols = cfg.get("name_cols", cfg.get("name_insert", {}).get("cols", 0))
    fit = mode == "pseudo"
    default_frame = tuple(cfg["default_frame"]) if cfg.get("default_frame") else None
    # procedures defined only in other files: each number's widest
    # definition anywhere, under the base scripts'
    anywhere, frames_anywhere = {}, {}
    for oname, opath in _files(vol, cfg["game_dir"]):
        odata = vol.read(opath)
        otoks = av.tokenize(odata, extraop)
        for pn, f in proc_effects(odata, otoks, oname, "", by_ref, None, name_cols).items():
            if pn not in anywhere or f["width"] > anywhere[pn]["width"]:
                anywhere[pn] = f
        frames_anywhere.update({pn: f for pn, f in proc_frames(odata, otoks).items() if f})
    start_eff, base_nums = dict(anywhere), set()
    for bname in base:
        bdata = vol.read(mes_path(vol, cfg["game_dir"], bname))
        btoks = av.tokenize(bdata, extraop)
        base_nums |= set(procs(bdata, btoks))
        frames_anywhere.update(proc_frames(bdata, btoks))
        plain = resolve_effects([start_eff, proc_effects(bdata, btoks, bname, "", by_ref, None, name_cols)])
        start_eff.update(proc_effects(bdata, btoks, bname, "", by_ref, end_proc(bdata, btoks, plain), name_cols))
    table = (cfg["proc_slot"], cfg["proc_slots"], base_nums) if "proc_slot" in cfg else None
    # a file that ends its messages neither with a procedure nor written
    # out pages with a wait and the game's usual text reset (AA n), which
    # needs no procedure (a file run at startup may not have them yet)
    resets = collections.Counter()
    for _oname, opath in _files(vol, cfg["game_dir"]):
        odata = vol.read(opath)
        otoks = av.tokenize(odata, extraop)
        for x, (k, s2, _e) in enumerate(otoks[:-1]):
            if k == "cmd" and odata[s2] == 0xAA and otoks[x + 1][0] == "num":
                resets[bytes(odata[s2:otoks[x + 1][2]])] += 1
    wait = bytes.fromhex(cfg["wait"]) if "wait" in cfg else WAIT
    game_break = wait + resets.most_common(1)[0][0] if resets else None
    ins = cfg.get("name_insert")
    insert = (bytes.fromhex(ins["call"]), bytes.fromhex(ins["flag"]), ins["cols"]) if ins else None
    variables = var_strings(vol, cfg["game_dir"], extraop, name_cols)
    rooms = mec_rooms(vol, cfg["game_dir"], extraop)
    for name, path in _programs(vol, cfg["game_dir"]):
        exe = vol.read(path)
        runs = program_strings(exe)
        values = {}
        for s, e, _t in runs:
            ref = "%s:%04x" % (name, s)
            if ref in by_ref:
                values[s] = _plain(" ".join(by_ref[ref].split("\n")))
        new, cut = engine_strings.apply(exe, runs, values)
        for s, need, room in cut:
            warn.append("%s: %d bytes, the program has room for %d" % (ids["%s:%04x" % (name, s)], need, room))
        if new != exe:
            vol.write(path, new)
    for name, path in _files(vol, cfg["game_dir"]):
        data = vol.read(path)
        out, pos = bytearray(), 0
        for n, (s, e, _t, room, pad) in enumerate(variables.get(name, [])):
            ref = "%s:v%d" % (name, n)
            if ref not in by_ref:
                continue
            raw = _plain(" ".join(by_ref[ref].split("\n"))).replace(b"'", "’".encode("cp932")).replace(
                b'"', "”".encode("cp932"))
            if len(raw) > room:
                if not fit:
                    raise SystemExit("%s: %d bytes, the variable holds %d; shorten it" % (ids[ref], len(raw), room))
                raw = raw[:room]
            out += data[pos:s] + (raw.ljust(e - s) if pad else raw)
            pos = e
        data = bytes(out + data[pos:])
        def rebuild(texts):
            streams = _streams(data, extraop)
            plain = resolve_effects([start_eff, proc_effects(data, streams[0][2], name, "", texts, None,
                                                             name_cols)])
            proc = end_proc(data, streams[0][2], plain)
            nums = table[:2] + (set(),) if table and name.upper() in base else table
            effects = resolve_effects([start_eff, proc_effects(data, streams[0][2], name, "", texts, proc,
                                                                    name_cols)])
            frames = {**frames_anywhere, **proc_frames(data, streams[0][2])}
            new = patch_stream(data, streams[0][2], "", name, texts, ids, proc, warn, nums, insert, fit, effects,
                               frames, game_break, cfg.get("menu_fullwidth", False), default_frame, wait)
            if len(streams) > 1:
                # the tails: re-encrypt each rebuilt tail in place of the old one
                toks = av.tokenize(new, extraop)
                crypts = [t for t in toks if t[0] == "crypt"]
                out, pos = bytearray(), 0
                for (tag, inner, itoks), (_k, s, e) in zip(streams[1:], crypts):
                    key = _num(new, [t for t in toks if t[2] == s][0][1])
                    effects = resolve_effects([start_eff, proc_effects(inner, itoks, name, tag, texts, proc,
                                                                            name_cols)])
                    rebuilt = patch_stream(inner, itoks, tag, name, texts, ids,
                                           end_proc(inner, itoks, effects) or proc, warn, nums, insert, fit, effects,
                                           {**frames, **proc_frames(inner, itoks)}, game_break,
                                           cfg.get("menu_fullwidth", False), default_frame, wait)
                    out += new[pos:s] + av.encrypt(rebuilt, key)
                    pos = e
                new = bytes(out + new[pos:])
            return new

        new = rebuild(by_ref)
        room = rooms.get(name.upper())
        if room and len(new) > room:
            mine = sorted({ids[r] for r in by_ref if r.startswith(name + ":")})
            if not fit:
                raise SystemExit("%s: %d bytes with the English, its place in the engine's MEC buffer holds %d "
                                 "(strings %s); shorten them" % (name, len(new), room, ", ".join(mine)))
            # the --pseudo filler: this file's texts cut until it fits
            for scale in (0.8, 0.6, 0.45, 0.3, 0.2, 0.1, 0):
                texts = {r: t for r, t in by_ref.items() if not r.startswith(name + ":")}
                if scale:
                    texts.update({r: t[:max(1, int(len(t) * scale))] for r, t in by_ref.items()
                                  if r.startswith(name + ":")})
                new = rebuild(texts)
                if len(new) <= room:
                    break
        if new != vol.read(path):
            vol.write(path, new)
    note = MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii")
    try:
        vol.find(cfg["game_dir"] + "/MTL_NOTE.TXT")
        vol.write(cfg["game_dir"] + "/MTL_NOTE.TXT", note)
    except FileNotFoundError:
        vol.create(cfg["game_dir"] + "/MTL_NOTE.TXT", note)
    img.save(dst)
    for w in warn:
        print("warning: " + w)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
