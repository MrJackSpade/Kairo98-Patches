"""D.O.'s ADL games (DOR Part 2): the scripts, the name and command tables
and ADL.EXE's own strings out to strings.json, and the English patch (the
formats and the ADL.EXE patch are in pc98tl/adl.py).

The patch works on the game's hard-disk release (game.json "image", the
game in "game_dir").

Strings:

* "msg": a run of text: a text statement's runs, and the statements after
  it that go on along the same line (the one before ends with its text:
  a colour change between words), unless one is the target of an entry.
  The controls between its runs are {X1}, {X2}... (each kept once, in any
  order; the note says what each does).
* "name": a name table's names (NAME_Fn.EDT: 8 letters, the 9-byte slot).
* "cmd": a command table's items (KOM_Fn.EDT: 16 letters, the 17-byte slot;
  the menus' save/load and numbered items).
* "engine": ADL.EXE's save slots' names (16 letters, the 17-byte slot).

English in a run of text is written as 20h, then ASCII (pc98tl/adl.py:
the helper draws it half-width), wrapped between words with a new line
(0Ah) where the next word would reach the text window's last cell (a line
that filled the window would be wrapped by the engine, and a new line (06)
after it would leave an empty one); the engine pages by itself at the
window's bottom.  The cursor is followed
from statement to statement: the window 71h last set (its width; 0 at
the start), the name's indent (10 cells after 04 n, to 03 clears or a 00
after a control), new lines (06), and the Japanese runs left as they are
(two cells a character).

A menu's text window (71h after the 82h frame, then 12h and the menu,
10h) is as wide as the longest Japanese choice: it is widened (with its
frame) to the longest English choice, up to the screen's right edge, so
each choice stays one line.

A script is read into a 64 KB segment: a build whose script outgrows it is
refused, naming the script's strings (the --pseudo filler is cut instead
until it fits).
"""
import json
import os
import re
import struct

from . import adl
from .alice_sys2_tl import sha256

PREFIX = {"msg": "m", "name": "n", "cmd": "c", "engine": "e"}
SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "♥": "<3"}
NAME_CELLS = 8
CMD_CELLS = 16                  # a command's slot (the bytes the patch takes; its room is the menu boxes')
SLOT_CELLS = 16
INDENT = 10                     # the cells after a name (04 n: 80 dots)
SCREEN = 640
TOKEN = re.compile(r"\{X(\d+)\}")
CTRL_NOTE = {1: "colour %d", 2: "a key wait", 3: "the window cleared", 4: "speaker %d's name", 5: "the picture redrawn",
             6: "a new line", 7: "animation %d on", 8: "animation %d off"}


def _image(cfg, src):
    from .disk import DiskImage
    return DiskImage(src)


def _game_files(vol, cfg):
    d = vol.find(cfg["game_dir"])
    return sorted(e["name"] for e in vol.listdir(d["cluster"]) if not e["is_dir"])


def scripts(vol, cfg):
    """The game folder's scripts (*.EDT but the tables)."""
    return [n for n in _game_files(vol, cfg)
            if n.upper().endswith(".EDT") and not re.match(r"(NAME|KOM)_F", n.upper())]


def tables(vol, cfg):
    return [n for n in _game_files(vol, cfg) if re.match(r"(NAME|KOM)_F\d+\.EDT$", n.upper())]


def _program(vol, cfg):
    exe = vol.read(cfg["game_dir"] + "/ADL.EXE")
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    return exe, hdr


# ---- messages

def _ends_on_text(its):
    """Whether a statement's items end with its text (the next one goes on along the line)."""
    if not its:
        return False
    if its[-1][0] == "text":
        return True
    return its[-1][0] == "end" and len(its) > 1 and its[-2][0] == "text"


def units(d, toks):
    """[(start of the first statement, [statement starts], [(run start, run end)], [control bytes between
    the runs])] of a script's runs of text."""
    targets = set(adl.entries(d).values())
    out, k = [], 0
    while k < len(toks):
        s, e = toks[k]
        if d[s] != 0x70:
            k += 1
            continue
        group = [k]
        while _ends_on_text(adl.items(d, *toks[group[-1]])) and group[-1] + 1 < len(toks) \
                and d[toks[group[-1] + 1][0]] == 0x70 and toks[group[-1] + 1][0] not in targets:
            group.append(group[-1] + 1)
        runs = []
        for m in group:
            runs += [(a, b) for kind, a, b in adl.items(d, *toks[m]) if kind == "text"]
        if runs:
            # (the bytes between one run's 00 and the next run's 0Fh)
            between = [d[runs[i][1] + 1:runs[i + 1][0] - 1] for i in range(len(runs) - 1)]
            out.append((s, [toks[m][0] for m in group], runs, between))
        k = group[-1] + 1
    return out


def _describe(ctrl):
    """What the control bytes between two runs do (for the string's note)."""
    out, j = [], 0
    while j < len(ctrl):
        b = ctrl[j]
        if b in adl.CTRL_ARG:
            out.append(CTRL_NOTE[b] % ctrl[j + 1])
            j += 2
        elif b in CTRL_NOTE:
            out.append(CTRL_NOTE[b])
            j += 1
        else:
            j += 1
    return ", ".join(out) or "none (the text goes on)"


def unit_text(d, runs, table):
    jp = ""
    for i, (a, b) in enumerate(runs):
        if i:
            jp += "{X%d}" % i
        jp += adl.text_of(d[a:b], table)
    return jp


# ---- the patcher's wrap

def _ascii(text):
    return "".join(SUBST.get(c, c) for c in text)


def wrap(text, width, col, indent, edge=None):
    """(the run's text with new lines where the next word would pass width
    cells, from column col, lines after a new line starting at indent; the
    column it ends at).  A word longer than a line is cut at the edge.  edge: the window's own width,
    where the engine wraps by itself (width, unless the lines are kept shorter)."""
    edge = width if edge is None else edge
    out = ""
    for n, para in enumerate(_ascii(text).split("\n")):
        if n:
            out += "\n"
            col = indent
        for k, word in enumerate(para.split(" ")):
            lead = " " if k and col > indent else ""
            if col > indent and col + len(lead) + len(word) > width:
                out += "\n"
                col, lead = indent, ""
            while len(word) > width - indent:
                room = width - col
                out += lead + word[:room] + "\n"
                word, col, lead = word[room:], indent, ""
            out += lead + word
            col += len(lead) + len(word)
            if col >= edge:
                # (the engine has wrapped by itself)
                col = indent
    return out, col


def _jp_advance(text, width, col, indent):
    for _c in text:
        if col + 2 > width:
            col = indent
        col += 2
        if col >= width:
            col = indent
    return col


def _menus(d, toks):
    """{start of a menu's text window (the last 71h before its choices): (the 82h frame just before it or
    None, [starts of the choices: the text statements right after 10h])}."""
    out = {}
    for k, (s, _e) in enumerate(toks):
        if d[s] != 0x10:
            continue
        # (the window and its frame come before the menu, or right after it: 10h, 80h, 82h, 71h)
        first = k + 1
        while first < len(toks) and d[toks[first][0]] in (0x80, 0x82, 0x71):
            first += 1
        w = next((j for j in range(first - 1, -1, -1) if d[toks[j][0]] == 0x71), None)
        if w is None:
            continue
        frame = toks[w - 1][0] if w and d[toks[w - 1][0]] == 0x82 else None
        choices = []
        for s2, _e2 in toks[first:]:
            if d[s2] != 0x70:
                break
            choices.append(s2)
        entry = out.setdefault(toks[w][0], (frame, []))
        entry[1].extend(choices)
    return out


def _widest(d, s, frame):
    """The widest a menu's text window at s may be (dots): it and its frame within the screen."""
    x, _y, w, _h = _window(d, s)
    most = SCREEN - x
    if frame is not None:
        fx, _fy, fw, _fh = struct.unpack_from(">4H", d, frame + 1)
        most = min(most, SCREEN - fx - (fw - w))
    # (a multiple of 16 dots: the key-wait mark is drawn at its middle, which must be a whole cell)
    return most // 16 * 16


def _box_cells(d, s):
    """The letters a menu box (12h at s: x, y, width, big-endian words) holds: its items are drawn
    8 dots in from its left edge, and as far from its right."""
    return max(1, (struct.unpack_from(">H", d, s + 5)[0] - 16) // 8)


def _window(d, s):
    """(x, y, w, h) of 71h at s."""
    return struct.unpack_from(">4H", d, s + 1)


def split_tokens(text, n, sid):
    """[the text between the tokens] in the order of {X1}..{Xn-1} kept, and the order of the tokens."""
    found = [int(t) for t in TOKEN.findall(text)]
    if sorted(found) != list(range(1, n)):
        raise SystemExit("%s: the English must keep each of %s once (has %s)" % (
            sid, ", ".join("{X%d}" % i for i in range(1, n)) or "no tokens",
            ", ".join("{X%d}" % i for i in found) or "none"))
    return TOKEN.split(text)[0::2], found


def start_widths(vol, cfg):
    """{script: the text window's width (cells) it starts with}: a script that draws text before it
    sets a window (71h) draws in the one its loader set.  The scripts each load (50h, 51h: a name,
    .EDT added) are followed from script to script; where several load one, the narrowest; the
    first script (and one no script loads) none (0)."""
    loads = {}
    for name in scripts(vol, cfg):
        d = vol.read(cfg["game_dir"] + "/" + name)
        toks = adl.tokenize(d)
        width, out = None, []
        for s, e in toks:
            if d[s] == 0x71:
                width = _window(d, s)[2] // 8
            elif d[s] in (0x50, 0x51):
                target = d[s + 1:d.index(0, s + 1)].decode("ascii", "replace").upper() + ".EDT"
                out.append((target, width))
        loads[name.upper()] = out
    start = {}
    for _round in range(len(loads) + 1):
        new = {}
        for name, out in loads.items():
            for target, width in out:
                w = width if width is not None else start.get(name)
                if w:
                    new[target] = min(new.get(target, w), w)
        if new == start:
            break
        start = new
    return start


def rebuild(d, toks, values, table, ids, start_width=0):
    """The script with English in values ({unit start: text}); start_width: the window's width (cells)
    before the script sets one."""
    us = {u[0]: u for u in units(d, toks)}
    menus = _menus(d, toks)
    new = {}
    width, col, indent = start_width, 0, 0
    # (each translated unit's statements: rebuilt from the English pieces)
    plan = {}
    for s, (start, starts, runs, between) in us.items():
        if s not in values:
            continue
        pieces, order = split_tokens(values[s], len(runs), ids.get(s, "%x" % s))
        plan[s] = (pieces, order)
    widen = {}
    # (a menu's text window: as wide as the longest English choice, up to the screen's edge)
    for s, (frame, choices) in menus.items():
        x, _y, w, _h = _window(d, s)
        need = max([len(_ascii(p)) * 8 for c in choices if c in plan for p in plan[c][0]] or [0])
        if need > w:
            widen[s] = max(w, min(_widest(d, s, frame), (need + 15) // 16 * 16))
    k = 0
    while k < len(toks):
        s, e = toks[k]
        op = d[s]
        if op == 0x71:
            x, y, w, h = _window(d, s)
            if s in widen:
                w = widen[s]
                new[s] = d[s:s + 1] + struct.pack(">4H", x, y, w, h)
                f = menus[s][0]
                if f is not None:
                    fx, fy, fw, fh = struct.unpack_from(">4H", d, f + 1)
                    new[f] = d[f:f + 1] + struct.pack(">4H", fx, fy, max(fw, w + (fw - _window(d, s)[2])), fh)
            width, col, indent = w // 8, 0, 0
            k += 1
            continue
        if op != 0x70:
            k += 1
            continue
        u = us.get(s)
        group = u[1] if u else [s]
        n_stmt = len(group)
        stmts = toks[k:k + n_stmt]
        if u and s in plan:
            pieces, order = plan[s]
            runs, between = u[2], u[3]
            # (the run's English, wrapped as the cursor goes)
            seq = [pieces[0]] + [x for i, t in enumerate(order) for x in (t, pieces[i + 1])]
            # (the bytes before the first run and after the last, as they are)
            head = d[s:runs[0][0]]
            tail = d[runs[-1][1]:stmts[-1][1]]
            body = bytearray()
            col, indent = _ctrl_effect(head, col, indent)
            for i, x in enumerate(seq):
                if i % 2 == 0:
                    # (a cell short of the edge: a line that fills the window is wrapped by the engine,
                    # and the script's own new line after it would leave an empty one)
                    text, col = wrap(x, max(width - 1, indent + 1), col, indent, max(width, indent + 1))
                    body += adl.encode_ascii(text)
                else:
                    ctrl = between[x - 1]
                    body += b"\x00" + ctrl + b"\x0f"
                    col, indent = _ctrl_effect(ctrl, col, indent)
            col, indent = _ctrl_effect(tail, col, indent)
            new[s] = head + bytes(body) + tail
            for s2, _e2 in stmts[1:]:
                new[s2] = b""
        else:
            for s2, e2 in stmts:
                at = s2
                for kind, a, b in adl.items(d, s2, e2):
                    if kind == "text":
                        col, indent = _ctrl_effect(d[at:a], col, indent)
                        col = _jp_advance(adl.text_of(d[a:b], table), max(width, 1), col, indent)
                        at = b
                col, indent = _ctrl_effect(d[at:e2], col, indent)
        k += n_stmt
    return adl.rebuild(d, toks, new)


def _ctrl_effect(raw, col, indent):
    """(col, indent) after a text statement's bytes other than its runs' characters: controls, the
    runs' 0Fh and 00, statement starts (70h).  A 00 straight after a control moves the cursor to the
    window's left edge and drops the name's indent (the engine's control loop reads it); a 00 after
    a run or at a statement's start only ends the statement."""
    j, ctrl = 0, False
    while j < len(raw):
        b = raw[j]
        if b in (0, 0x0F, 0x70):
            if b == 0 and ctrl:
                col, indent = 0, 0
            ctrl = False
            j += 1
            continue
        if b == 4:
            col = indent = INDENT
        elif b in (3, 6):
            col = indent
        j += 2 if b in adl.CTRL_ARG else 1
        ctrl = True
    return col, indent


# ---- tables

def _table_strings(raw):
    parts, _tail = adl.table_read(raw)
    return [p.decode("cp932", "replace") for p in parts]


def _slots(img):
    """[(start, text)] of ADL.EXE's save slots' names (17-byte slots in the data segment)."""
    at = img.find("エ　リ　ア".encode("cp932"))
    if at < 0:
        return []
    out = []
    while img[at:at + 2] == "エ".encode("cp932"):
        end = img.index(0, at)
        out.append((at, img[at:end].decode("cp932")))
        at += 17
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    img = _image(cfg, src)
    vol = img.volumes[0]
    exe, hdr = _program(vol, cfg)
    table = adl.kana_table(exe[hdr:])
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
    menu_cells = CMD_CELLS
    starts = start_widths(vol, cfg)
    for name in scripts(vol, cfg):
        d = vol.read(cfg["game_dir"] + "/" + name)
        toks = adl.tokenize(d)
        menu_cells = min([menu_cells] + [_box_cells(d, s) for s, _e in toks if d[s] == 0x12])
        if adl.rebuild(d, toks, {}) != d:
            raise SystemExit("%s does not rebuild byte for byte" % name)
        width = starts.get(name.upper(), 0)
        choice_cells = {c: _widest(d, w, f) // 8 for w, (f, cs) in _menus(d, toks).items() for c in cs}
        firsts = {u[0]: u for u in units(d, toks)}
        for s, _e in toks:
            if d[s] == 0x71:
                x, _y, w, _h = _window(d, s)
                width = w // 8
            if s in firsts:
                _s, _starts, runs, between = firsts[s]
                jp = unit_text(d, runs, table)
                if not jp.replace("　", "").strip() or re.fullmatch(r"(\{X\d+\})*", jp.replace("　", "")):
                    continue
                note = "; ".join("{X%d}: %s" % (i + 1, _describe(c)) for i, c in enumerate(between)) or None
                add("msg", jp, "%s:%04x" % (name, s), choice_cells.get(s, width), note)
    for name in tables(vol, cfg):
        kind = "name" if name.upper().startswith("NAME") else "cmd"
        for i, jp in enumerate(_table_strings(vol.read(cfg["game_dir"] + "/" + name))):
            if jp.replace("　", "").strip():
                add(kind, jp, "%s:%d" % (name, i), NAME_CELLS if kind == "name" else menu_cells)
    for at, jp in _slots(exe[hdr:]):
        add("engine", jp, "ADL.EXE:%04x" % at, SLOT_CELLS)
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
                if "note" in prev and "note" not in e:
                    e["note"] = prev["note"]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _cut(text, ratio):
    """text cut to ratio of its length (at least four letters), its tokens kept."""
    parts = TOKEN.split(text)
    out = ""
    for i, p in enumerate(parts):
        out += p[:max(min(len(p), 4), int(len(p) * ratio))] if i % 2 == 0 else "{X%s}" % p
    return out


def _fixed(text, room):
    """Table and slot English: ASCII (one byte a letter), cut to room bytes."""
    out = bytearray()
    for c in _ascii(" ".join(text.split("\n"))):
        if 0x20 <= ord(c) < 0x7F:
            out.append(ord(c))
        else:
            try:
                b = c.encode("cp932")
            except UnicodeEncodeError:
                b = b"?"
            out += b if len(b) == 2 else b"?"
    return bytes(out[:room])


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(cfg, src)
    vol = img.volumes[0]
    exe, hdr = _program(vol, cfg)
    table = adl.kana_table(exe[hdr:])
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        if mode == "pseudo":
            if e["kind"] == "msg":
                text = "".join(pseudo(e["id"], 2 * len(p)) if i % 2 == 0 and p.strip("　 ") else
                               ("{X%s}" % p if i % 2 else p) for i, p in enumerate(TOKEN.split(e["jp"])))
            else:
                text = pseudo(e["id"], 2 * len(e["jp"]))[:e["max_cells"]]
        else:
            text = e["en"]
        for r in e["refs"]:
            f, a = r.rsplit(":", 1)
            key = (f, int(a, 16) if e["kind"] in ("msg", "engine") else int(a))
            ids[key] = e["id"]
            if text:
                by_ref[key] = text
    warn, done = [], 0
    starts = start_widths(vol, cfg)
    for name in scripts(vol, cfg):
        path = cfg["game_dir"] + "/" + name
        d = vol.read(path)
        toks = adl.tokenize(d)
        values = {a: t for (f, a), t in by_ref.items() if f == name}
        if not values:
            continue
        sids = {a: ids[(name, a)] for a in values}
        new = rebuild(d, toks, values, table, sids, starts.get(name.upper(), 0))
        if len(new) > 0x10000 and mode != "pseudo":
            raise SystemExit("%s: %d bytes, a script may take 65536 (its segment); shorten these strings: %s" % (
                name, len(new), ", ".join(sorted(set(sids.values())))))
        cut = 0
        while len(new) > 0x10000:
            total = sum(len(v) for v in values.values())
            ratio = max(0.0, 1 - (len(new) - 0x10000) * 1.1 / max(1, total))
            values = {a: _cut(v, ratio) for a, v in values.items()}
            after = sum(len(v) for v in values.values())
            if after >= total:
                raise SystemExit("%s: the script does not fit even with its filler cut" % name)
            cut += total - after
            new = rebuild(d, toks, values, table, sids, starts.get(name.upper(), 0))
        if cut:
            warn.append("%s: the filler was cut by %d letters to fit the script's segment" % (name, cut))
        adl.tokenize(new)
        vol.write(path, new)
        done += 1
    for name in tables(vol, cfg):
        path = cfg["game_dir"] + "/" + name
        parts, tail = adl.table_read(vol.read(path))
        room = NAME_CELLS if name.upper().startswith("NAME") else CMD_CELLS
        changed = False
        for i in range(len(parts)):
            if (name, i) in by_ref:
                b = _fixed(by_ref[(name, i)], room)
                if len(_ascii(by_ref[(name, i)])) > room:
                    warn.append("%s: cut to %d letters (the table's slot)" % (ids[(name, i)], room))
                parts[i] = b
                changed = True
        if changed:
            vol.write(path, adl.table_write(parts, tail))
    exe_img = bytearray(exe[hdr:])
    for at, jp in _slots(bytes(exe_img)):
        if ("ADL.EXE", at) in by_ref:
            b = _fixed(by_ref[("ADL.EXE", at)], SLOT_CELLS)
            exe_img[at:at + 17] = b + bytes(17 - len(b))
    vol.write(cfg["game_dir"] + "/ADL.EXE", adl.patch_exe(exe[:hdr] + bytes(exe_img)))
    for w in warn:
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
