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
            slot holds), "proc_slots" (slots in the table), "name_insert"
            ({"call": hex of the hero's name procedure call, "flag": hex of
            the register set that makes it print inline, "cols": the
            widest name part it prints}), "boot_steps"}
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


def units(data, toks):
    """[(first, end, kind, frame)] of the text runs: token index range,
    "msg" or "item", and the text frame (x1, y1, x2, y2) in force."""
    out, frame, i = [], None, 0
    menu_depth, proc_depth, depth = [], [], 0      # depths of open menu item / procedure blocks
    pending_menu = pending_proc = False
    while i < len(toks):
        k, s, e = toks[i]
        if k == "cmd" and data[s] == 0xA6:
            nums = [t for t in toks[i + 1:i + 5] if t[0] == "num"]
            if len(nums) == 4:
                frame = tuple(_num(data, t[1]) for t in nums)
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
    procedure in force (this file's or START.MES's)."""
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


def end_proc(data, toks):
    """The file's message-end procedure: the BA call that most often
    follows a message within a few tokens; None when there is none."""
    seen = collections.Counter()
    for _i, j, kind, _f in units(data, toks):
        if kind != "msg":
            continue
        for x in range(j, min(j + 12, len(toks) - 1)):
            k, s, _e = toks[x]
            if k == "cmd" and data[s] == 0xBA:
                if toks[x + 1][0] == "num":
                    seen[bytes(data[s:toks[x + 1][2]])] += 1
                break
            if k in TEXT:
                break
    return max((c, b) for b, c in seen.items())[1] if seen else None


def _files(vol, game_dir):
    """The MES folder's scripts: [(name, path)]."""
    d = vol.find(game_dir + "/MES")
    return [(e["name"], game_dir + "/MES/" + e["name"]) for e in vol.listdir(d["cluster"])
            if not e["is_dir"] and e["name"].upper().endswith((".MES", ".MEC"))]


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
    for sub in ("", "/TCM"):
        try:
            d = vol.find(game_dir + sub)
        except FileNotFoundError:
            continue
        out += [((sub[1:] + "/" if sub else "") + e["name"], game_dir + sub + "/" + e["name"])
                for e in vol.listdir(d["cluster"]) if not e["is_dir"] and e["name"].upper().endswith(PROGRAM_EXT)]
    return out


def _is_table(text):
    """A character table the name entry picks from by position (kana,
    full-width letters and Japanese punctuation, no kanji)."""
    body = [c for c in text if c != "　"]
    return len(body) >= 20 and all("、" <= c <= "ヿ" or "！" <= c <= "～" for c in body)


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


def var_strings(vol, game_dir, extraop, entry_cols):
    """{file name: [(start, end, text, room, pad)]}: the values the scripts give
    string variables (@n='...' in an argument: the hero's default name,
    item names, picture titles), and the name entry's defaults (an
    argument holding just one of them).  room is the bytes a value may
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
            if bytes(data[s + 1:e - 1]) in values:
                spans.append((s + 1, e - 1))
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


# ---- extraction ------------------------------------------------------------------------------
def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
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
                                            cfg["name_insert"]["cols"]).items()
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
    vol = DiskImage(src).volumes[0]
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


def build(text, kind, frame, cells, proc, warn, sid, start=(0, 0), reserve=0):
    """English for a text run: (the bytes to put in its place, the (line,
    column) it ends at).  A message starts at start (line, column) of its
    page and leaves reserve columns at its end for what is printed after
    it on its line."""
    size = frame_size(frame)
    if kind in ("item", "inline") or not size or size[1] == 1:
        # text in a one-line frame often has more drawn after it on the
        # line (an input field, numbers), so it keeps its Japanese width
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
        if kind == "item":
            flat = flat.ljust(room)
        return _encode(flat), None
    cols, rows = size
    row, col = start
    if col >= cols:
        row, col = row + 1, 0
    if row >= rows:
        row = 0
    lines = wrap(text, cols, col)
    # the first page has the lines left below the start row
    first = rows - row
    pages = [lines[:first]] + [lines[k:k + rows] for k in range(first, len(lines), rows)]
    pages = [p for p in pages if p]
    if len(pages) > 1 and proc is None:
        warn.append("%s: %d lines, the frame shows %d and this file has no message-end procedure to page with"
                    % (sid, len(lines), rows))
        pages = [lines]
    end_row = (row if len(pages) == 1 else 0) + len(pages[-1]) - 1
    end_col = _width(pages[-1][-1]) + (col if len(pages) == 1 and len(pages[-1]) == 1 else 0)
    body = [b"\xa5".join(_encode(ln) if ln else b"" for ln in page) for page in pages]
    out = (WAIT + proc).join(body) if proc else body[0]
    if reserve and end_col + reserve > cols:
        # what follows on this line (the hero's name) goes to the next one
        if end_row + 1 < rows or not proc:
            out, end_row, end_col = out + b"\xa5", end_row + 1, 0
        else:
            out, end_row, end_col = out + WAIT + proc, 0, 0
    return out, (end_row, end_col)


def patch_stream(data, toks, tag, name, by_ref, ids, proc, warn, table, insert=None, fit=False):
    """The stream with its text runs replaced.  table: (slot bytes, slot
    count, START.MES's procedure numbers).  A procedure body may grow to
    the larger of its own length and its room in the procedure table;
    past that it would overwrite a procedure in force, so the build is
    refused, or with fit (the --pseudo filler) the body's texts are cut
    to fit."""
    slot, slots, start_nums = table
    defs = procs(data, toks)
    room = proc_room(defs, start_nums, slot, slots)
    limit = {n: max(e - s, room[n]) for n, (s, e) in defs.items()}
    reps = {}
    us = units(data, toks)
    starts = [_start(data, toks, i, proc, insert) for i, _j, _k, _f in us]
    end = None                          # where the last message replaced ended
    for n, (i, j, kind, frame) in enumerate(us):
        ref = "%s:%s%d" % (name, tag, n)
        text = by_ref.get(ref)
        if text is None:
            end = None
            continue
        cont, row, col = starts[n]
        # a message that continues the last one's line starts where it ended
        start = (end[0], end[1] + col) if cont and end else (row, col)
        nxt = starts[n + 1] if n + 1 < len(us) else (False, 0, 0)
        reserve = nxt[2] if nxt[0] and us[n + 1][2] == "msg" else 0
        s, e = toks[i][1], toks[j - 1][2]
        new, end = build(text, kind, frame, unit_cells(data, toks, i, j), proc, warn, ids.get(ref, ref),
                         start, reserve)
        reps[s] = (e, ids.get(ref, ref), new)
    for pn, (bs, be) in defs.items():
        inside = sorted(s for s in reps if bs <= s < be)
        grown = (be - bs) + sum(len(reps[s][2]) - (reps[s][0] - s) for s in inside)
        if grown <= limit[pn]:
            continue
        if not fit:
            raise SystemExit("%s%s: procedure %d would be %d bytes, its slots hold %d (strings %s); shorten them"
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


def _start(data, toks, i, proc, insert):
    """Where a message starts: (continues, line, column).  Looking back
    from the message to the last text, page end, frame or procedure call:

    * a call of the name procedure with its inline flag set (insert:
      (call bytes, flag bytes, columns)) prints the hero's name on the line,
      so the message starts that many columns on; right after text, with
      only such calls and variable sets between, it continues that text's
      line (continues: True);
    * any other call but the message-end one prints a speaker's name tag,
      which ends its line, so the message starts on the second line."""
    gap, x, stop = [], i - 1, None
    while x >= 0 and i - x <= 24:
        k, s, _e = toks[x]
        if k in TEXT:
            stop = "text"
            break
        if k == "cmd" and data[s] in (0xA6, 0xAA, 0xA5):
            stop = "reset"
            break
        if k == "cmd" and data[s] == 0xBA and x + 1 < len(toks) and x + 1 < i:
            call = bytes(data[s:toks[x + 1][2]])
            if not insert or call != insert[0]:
                stop = "end" if call == proc else "tag"
                break
        gap.append(toks[x])
        x -= 1
    gap.reverse()
    cols, flag, tagged, clean = 0, False, stop == "tag", True
    for y, (k, s, e) in enumerate(gap):
        if insert and bytes(data[s:e]) == insert[1]:
            flag = True
        elif k == "cmd" and data[s] == 0xBA:
            if flag:
                cols += insert[2]
            else:
                cols, tagged, clean = 0, True, False
            flag = False
        elif k not in ("reg", "var", "num"):
            clean = False
    if stop == "text" and clean:
        return True, 0, cols
    return False, (1 if tagged else 0), cols


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
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
    start = vol.read(cfg["game_dir"] + "/MES/START.MES")
    table = (cfg["proc_slot"], cfg["proc_slots"], set(procs(start, av.tokenize(start, extraop))))
    fit = mode == "pseudo"
    ins = cfg.get("name_insert")
    insert = (bytes.fromhex(ins["call"]), bytes.fromhex(ins["flag"]), ins["cols"]) if ins else None
    variables = var_strings(vol, cfg["game_dir"], extraop, cfg["name_insert"]["cols"])
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
        streams = _streams(data, extraop)
        proc = end_proc(data, streams[0][2])
        nums = table if name.upper() != "START.MES" else table[:2] + (set(),)
        new = patch_stream(data, streams[0][2], "", name, by_ref, ids, proc, warn, nums, insert, fit)
        if len(streams) > 1:
            # the tails: re-encrypt each rebuilt tail in place of the old one
            toks = av.tokenize(new, extraop)
            crypts = [t for t in toks if t[0] == "crypt"]
            out, pos = bytearray(), 0
            for (tag, inner, itoks), (_k, s, e) in zip(streams[1:], crypts):
                key = _num(new, [t for t in toks if t[2] == s][0][1])
                rebuilt = patch_stream(inner, itoks, tag, name, by_ref, ids, end_proc(inner, itoks) or proc, warn,
                                       nums, insert, fit)
                out += new[pos:s] + av.encrypt(rebuilt, key)
                pos = e
            new = bytes(out + new[pos:])
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
