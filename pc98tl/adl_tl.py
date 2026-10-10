"""D.O.'s ADL games (DOR Part 1-3) and ADL5 games (Yuu Disk Vol. 5): the
scripts, the name and command tables and the program's own strings out to
strings.json, and the English patch (the formats and the program patches
are in pc98tl/adl.py and pc98tl/adl5.py; game.json "version": "adl5" picks
the later one).

The patch works on the image game.json names (a hard-disk release, or a
floppy holding the program and its scripts), the game in "game_dir" ("" the
disk's root), the program "program" (ADL.EXE where it is not given).

Strings:

* "msg": a run of text: a text statement's runs, and the statements after
  it that go on along the same line (the one before ends with its text:
  a colour change between words), unless one is the target of an entry.
  The controls between its runs are {X1}, {X2}... (each kept once, in any
  order; the note says what each does).
* "name": a name table's names (NAME_Fn.EDT, NA_*.EDT: 8 letters, the 9-byte
  slot; ADL5: twice the length the 19h loading the table gives, its slot one
  more).
* "cmd": a command table's items (KOM_Fn.EDT, COM_*.EDT: 16 letters, the
  17-byte slot; ADL5: twice the length the 18h loading the table gives, and
  within the menu boxes (12h) the scripts draw while it is loaded; the
  menus' save/load and numbered items).
* "engine": the program's own strings: ADL.EXE's save slots' names (16
  letters, the 17-byte slot); ADL5.EXE's messages (runs of text, each
  within the Japanese's bytes, a character the program rewrites (the drive
  letter) {X1}, kept at its place) and its movement commands (8 letters).
* ADL5's 71h (a run of text drawn at a place of its own) is a "msg" too,
  one line from its place to the screen's right edge.
* "engine" also: the lines of the helper programs game.json "program_files"
  names (PCMSET2.EXE, the voice speed setting, drawn by ADL5's graphics
  drawer: pc98tl/adl5.py patch_graph), each within its own bytes, the
  characters the program rewrites (digits) {X1}... kept at their places.

English in a run of text is written as 20h, then ASCII (pc98tl/adl.py:
the helper draws it half-width), wrapped between words with a new line
(0Ah) where the next word would reach the text window's last cell (a line
that filled the window would be wrapped by the engine, and a new line (06)
after it would leave an empty one); the engine pages by itself at the
window's bottom.  The cursor is followed
from statement to statement: the window last set (ADL's 71h, ADL5's 82h:
its text's width; a script that draws before it sets one, the window its
loader set), the name's indent (game.json "name_cells", 10 where it is not
given, after 04 n, to 03 clears or a 00 after a control), new lines (06),
and the Japanese runs left as they are (two cells a character).

A menu's text window (the last window set before its choices, the text
statements after 10h; in ADL the 82h frame before it with it) is as wide
as the longest Japanese choice: it is widened to the longest English
choice, up to the screen's right edge, so each choice stays one line.

A script is read into a 64 KB segment: a build whose script outgrows it is
refused, naming the script's strings (the --pseudo filler is cut instead
until it fits).
"""
import json
import os
import re
import struct

from . import adl, adl5
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
             6: "a new line", 7: "animation %d on", 8: "animation %d off", 9: "an effect", 10: "an effect",
             11: "window %d", 12: "control 0Ch (%d)", 13: "control 0Dh (%d)"}
F = adl                         # the script format: pc98tl/adl.py or adl5.py (game.json "version")


def _set_format(cfg):
    global F, INDENT
    F = adl5 if cfg.get("version") in ("adl5", "adl5a", "adl98", "adl98s", "adl98u", "adl21", "adl3a", "adl3b") else adl
    if F is adl5:
        adl5.set_variant(cfg["version"])
    else:
        adl.set_variant(cfg.get("version", "adl"))
    INDENT = cfg.get("name_cells", 10)


ARCHIVE = {}                    # game.json "archive" (ADL98S's EDT00; Yuu Disk Vol. 4's EDT00 and EDT01):
                                # {"arcs": [[path, Archive, {name: changed bytes}]], "where": {name: its archive}}


def _open_store(vol, cfg):
    """The scripts' and tables' store: the game folder, or the archive(s) game.json "archive" names (a
    name or a list of names; a member's name is looked up in the first archive that holds it)."""
    ARCHIVE.clear()
    names = cfg.get("archive")
    if names:
        arcs, where = [], {}
        for a in ([names] if isinstance(names, str) else names):
            path = _path(cfg, a)
            arcs.append([path, adl5.Archive(vol.read(path)), {}])
            for n in arcs[-1][1].names():
                where.setdefault(n, arcs[-1])
        ARCHIVE.update(arcs=arcs, where=where)


def _file_read(vol, cfg, name):
    return ARCHIVE["where"][name][1].read(name) if ARCHIVE else vol.read(_path(cfg, name))


def _file_write(vol, cfg, name, data):
    if ARCHIVE:
        ARCHIVE["where"][name][2][name] = data
    else:
        vol.write(_path(cfg, name), data)


def _close_store(vol):
    for path, arc, changed in ARCHIVE.get("arcs", []):
        if changed:
            vol.write(path, arc.rebuilt(changed))


def _read_script(vol, cfg, name):
    """(how it is coded, the script as the engine reads it: ADL98's are coded)."""
    return F.decode(_file_read(vol, cfg, name))


def _path(cfg, name):
    return cfg["game_dir"] + "/" + name if cfg["game_dir"] else name


def _image(cfg, src):
    from .disk import DiskImage
    return DiskImage(src)


def _game_files(vol, cfg):
    if ARCHIVE:
        return sorted(ARCHIVE["where"])
    cluster = vol.find(cfg["game_dir"])["cluster"] if cfg["game_dir"] else 0
    return sorted(e["name"] for e in vol.listdir(cluster) if not e["is_dir"])


def scripts(vol, cfg):
    """The game folder's scripts (*.EDT but the tables)."""
    extra = {n.upper() for n in cfg.get("tables", [])}
    return [n for n in _game_files(vol, cfg)
            if n.upper().endswith(".EDT") and not re.match(TABLE_RE, n.upper()) and n.upper() not in extra]


# (the tables: names (NAME_, DOR Special Edition '93's NA_) and commands (KOM_, its COM_))
TABLE_RE = r"(NAME|NA|KOM|COM)_\w*\.EDT$"


def tables(vol, cfg):
    """The name and command tables: by their names (TABLE_RE), and those game.json "tables" names
    (Crystal Rinal's POWER.EDT, a command table 18h loads)."""
    extra = {n.upper() for n in cfg.get("tables", [])}
    return [n for n in _game_files(vol, cfg) if re.match(TABLE_RE, n.upper()) or n.upper() in extra]


def _table_kind(name, slots):
    """"name" or "cmd": by the statement that loads the table (19h names, 18h commands), else by its
    name."""
    if name.upper() in slots:
        return "name" if slots[name.upper()][0] == 0x19 else "cmd"
    return "name" if name.upper().startswith("NA") else "cmd"


def _program(vol, cfg):
    exe = vol.read(_path(cfg, cfg.get("program", "ADL.EXE")))
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
    targets = set(F.entries(d).values())
    out, k = [], 0
    while k < len(toks):
        s, e = toks[k]
        if d[s] != 0x70 and not (F is adl5 and d[s] == 0x71):
            k += 1
            continue
        group = [k]
        while d[s] == 0x70 and _ends_on_text(F.items(d, *toks[group[-1]])) and group[-1] + 1 < len(toks) \
                and d[toks[group[-1] + 1][0]] == 0x70 and toks[group[-1] + 1][0] not in targets                 and toks[group[-1] + 1][0] == toks[group[-1]][1]:
            group.append(group[-1] + 1)
        runs = []
        for m in group:
            runs += [(a, b) for kind, a, b in F.items(d, *toks[m]) if kind == "text"]
        if runs:
            # (the bytes between one run's 00 and the next run's mark (0Fh, ADL5's FFh))
            between = [d[runs[i][1] + 1:runs[i + 1][0] - 1] for i in range(len(runs) - 1)]
            out.append((s, [toks[m][0] for m in group], runs, between))
        k = group[-1] + 1
    return out


def _describe(ctrl):
    """What the control bytes between two runs do (for the string's note)."""
    out, j = [], 0
    while j < len(ctrl):
        b = ctrl[j]
        if F.ctrl_len(b) == 2:
            out.append(CTRL_NOTE[b] % ctrl[j + 1])
            j += 2
        elif b in CTRL_NOTE:
            out.append(CTRL_NOTE[b])
            j += F.ctrl_len(b)
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
    """{start of a menu's text window (the last window set before its choices): (ADL's 82h frame just
    before it or None, [starts of the choices: the text statements right after 10h])}."""
    out = {}
    for k, (s, _e) in enumerate(toks):
        if d[s] != 0x10:
            continue
        # (the window and its frame come before the menu, or right after it: 10h, 80h, 82h, 71h)
        first = k + 1
        while first < len(toks) and d[toks[first][0]] in (0x80, 0x82, 0x71):
            first += 1
        w = next((j for j in range(first - 1, -1, -1) if d[toks[j][0]] == F.WINDOW_OP), None)
        if w is None:
            continue
        frame = toks[w - 1][0] if F is adl and w and d[toks[w - 1][0]] == 0x82 else None
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
    x, w = F.window(d, s)
    most = SCREEN - x - (32 if F is adl5 else 0)
    if frame is not None:
        fx, _fy, fw, _fh = struct.unpack_from(">4H", d, frame + 1)
        most = min(most, SCREEN - fx - (fw - w))
    # (a multiple of 16 dots: the key-wait mark is drawn at its middle, which must be a whole cell)
    return most // 16 * 16


def _boxes(d, toks):
    """{a menu box's start (12h: x, y, width): [the starts of its items]}: Crystal Rinal's menus, a box
    and its items as runs of text drawn at their own places (71h) right after it (text statements
    with no text, the colour, between them).  The box's width is the highlight's, and its background
    is drawn into the picture behind it, so the box keeps its width."""
    out = {}
    for k, (s, _e) in enumerate(toks):
        if d[s] != 0x12:
            continue
        items, j = [], k + 1
        while j < len(toks):
            s2 = toks[j][0]
            if d[s2] == 0x71:
                items.append(s2)
            elif not (d[s2] == 0x70 and not any(it[0] == "text" for it in F.items(d, s2, toks[j][1]))):
                break
            j += 1
        if items:
            out[s] = items
    return out


def _box_cells(d, s):
    """The letters a menu box (12h at s: x, y, width, big-endian words) holds: its items are drawn
    8 dots in from its left edge, and as far from its right."""
    return max(1, (struct.unpack_from(">H", d, s + 5)[0] - 16) // 8)


def _window(d, s):
    """(x, y, w, h) of ADL's 71h at s."""
    return struct.unpack_from(">4H", d, s + 1)


def split_tokens(text, n, sid):
    """[the text between the tokens] in the order of {X1}..{Xn-1} kept, and the order of the tokens."""
    found = [int(t) for t in TOKEN.findall(text)]
    if sorted(found) != list(range(1, n)):
        raise SystemExit("%s: the English must keep each of %s once (has %s)" % (
            sid, ", ".join("{X%d}" % i for i in range(1, n)) or "no tokens",
            ", ".join("{X%d}" % i for i in found) or "none"))
    return TOKEN.split(text)[0::2], found


# ADL5's (and ADL98's) flow: 28h goto, 2Bh call, 43h / 44h (a condition, or a menu item, then the
# entry), 10h a menu (its items at an entry), the entry the last two bytes name (big-endian); 91h
# returns, 28h, 50h and 51h (another script) do not go on to the next statement
FLOW_TARGET = {0x28, 0x2B, 0x43, 0x44, 0x11}
FLOW_STOP = {0x28, 0x91, 0x50, 0x51}


def flow_widths(d, toks, start_width):
    """{statement start: the narrowest text window (cells) any path to it set} of an ADL5 script,
    following its gotos, calls and menus from its start (start_width before any window; a statement
    no path reaches, or none sets a window before, is left out)."""
    ents = F.entries(d)
    index = {s: k for k, (s, _e) in enumerate(toks)}
    succ = []
    for k, (s, e) in enumerate(toks):
        out = [] if d[s] in FLOW_STOP or e not in index else [index[e]]
        if d[s] in FLOW_TARGET or d[s] == 0x10:
            n = struct.unpack_from(">H", d, (s + 1) if d[s] == 0x10 else (e - 2))[0]
            if n in ents and ents[n] in index:
                out.append(index[ents[n]])
        succ.append(out)
    state = {0: start_width or None}
    work = [0]
    while work:
        k = work.pop()
        w = state[k]
        s, e = toks[k]
        if d[s] == F.WINDOW_OP:
            w = F.window(d, s)[1] // 8
        for j in succ[k]:
            old = state.get(j, "unseen")
            new = w if old == "unseen" else (old if w is None else (w if old is None else min(old, w)))
            if new != old:
                state[j] = new
                work.append(j)
    return {toks[k][0]: w for k, w in state.items() if w}


def start_widths(vol, cfg):
    """{script: the text window's width (cells) it starts with}: a script that draws text before it
    sets a window draws in the one its loader set.  The scripts each load (50h, 51h: a name,
    .EDT added) are followed from script to script; where several load one, the narrowest; the
    first script (and one no script loads) none (0)."""
    loads = {}
    for name in scripts(vol, cfg):
        how, d = _read_script(vol, cfg, name)
        toks = F.tokenize(d)
        width, out = None, []
        for s, e in toks:
            if d[s] == F.WINDOW_OP:
                width = F.window(d, s)[1] // 8
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
    flow = flow_widths(d, toks, start_width) if F is adl5 else {}
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
        x, w = F.window(d, s)
        need = max([len(_ascii(p)) * 8 for c in choices if c in plan for p in plan[c][0]] or [0])
        if need > w:
            widen[s] = max(w, min(_widest(d, s, frame), (need + 15) // 16 * 16))
    k = 0
    while k < len(toks):
        s, e = toks[k]
        op = d[s]
        if op == F.WINDOW_OP:
            x, w = F.window(d, s)
            if s in widen:
                w = widen[s]
                new[s] = F.set_window_width(d, s, w)
                f = menus[s][0]
                if f is not None:
                    fx, fy, fw, fh = struct.unpack_from(">4H", d, f + 1)
                    new[f] = d[f:f + 1] + struct.pack(">4H", fx, fy, max(fw, w + (fw - F.window(d, s)[1])), fh)
            width, col, indent = w // 8, 0, 0
            k += 1
            continue
        if s in flow and op in (0x70, 0x71):
            width = flow[s]
        if op == 0x71 and F is adl5:
            # (a run drawn at a place of its own: one line to the screen's edge)
            if s in plan:
                x = struct.unpack_from(">H", d, s + 1)[0]
                runs, between = us[s][2], us[s][3]
                pieces, order = plan[s]
                seq = [pieces[0]] + [x2 for i, t in enumerate(order) for x2 in (t, pieces[i + 1])]
                body = bytearray()
                for i, x2 in enumerate(seq):
                    if i % 2 == 0:
                        body += adl.encode_ascii(" ".join(_ascii(x2).split("\n"))[:(SCREEN - x) // 8])
                    else:
                        body += b"\x00" + between[x2 - 1] + bytes([F.TEXT_MARK])
                new[s] = d[s:runs[0][0]] + bytes(body) + d[runs[-1][1]:e]
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
                    if F is adl5:
                        # (ADL5's helper wraps between words itself, at the window's edge)
                        text = _ascii(x)
                    else:
                        text, col = wrap(x, max(width - 1, indent + 1), col, indent, max(width, indent + 1))
                    body += adl.encode_ascii(text)
                else:
                    ctrl = between[x - 1]
                    body += b"\x00" + ctrl + bytes([F.TEXT_MARK])
                    col, indent = _ctrl_effect(ctrl, col, indent)
            col, indent = _ctrl_effect(tail, col, indent)
            new[s] = head + bytes(body) + tail
            for s2, _e2 in stmts[1:]:
                new[s2] = b""
        else:
            for s2, e2 in stmts:
                at = s2
                for kind, a, b in F.items(d, s2, e2):
                    if kind == "text":
                        col, indent = _ctrl_effect(d[at:a], col, indent)
                        col = _jp_advance(adl.text_of(d[a:b], table), max(width, 1), col, indent)
                        at = b
                col, indent = _ctrl_effect(d[at:e2], col, indent)
        k += n_stmt
    return F.rebuild(d, toks, new)


def _ctrl_effect(raw, col, indent):
    """(col, indent) after a text statement's bytes other than its runs' characters: controls, the
    runs' marks (0Fh, ADL5's FFh) and 00, statement starts (70h).  A 00 straight after a control moves the cursor to the
    window's left edge and drops the name's indent (the engine's control loop reads it); a 00 after
    a run or at a statement's start only ends the statement."""
    j, ctrl = 0, False
    while j < len(raw):
        b = raw[j]
        if b in (0, F.TEXT_MARK, 0x70):
            if b == 0 and ctrl:
                col, indent = 0, 0
            ctrl = False
            j += 1
            continue
        if b == 4:
            col = indent = INDENT
        elif b in (3, 6):
            col = indent
        j += F.ctrl_len(b)
        ctrl = True
    return col, indent


# ---- tables

def table_rooms(vol, cfg):
    """(name room, command room): the letters a table's slot holds.  ADL: 8 and 16.  ADL5 copies
    each table's strings into slots of twice the length 19h (names) and 18h (commands) give (a byte
    before the table's name), and one more: the shortest any script sets; None for a table no script
    loads (Zatsuon Ryouiki's commands: never shown)."""
    if F is not adl5:
        return NAME_CELLS, CMD_CELLS
    rooms = {0x19: [], 0x18: []}
    for name in scripts(vol, cfg):
        how, d = _read_script(vol, cfg, name)
        for s, _e in F.tokenize(d):
            if d[s] in rooms:
                rooms[d[s]].append(2 * d[s + 1])
    return min(rooms[0x19] or [None]), min(rooms[0x18] or [None])


def table_slots(vol, cfg):
    """{TABLE.EDT: (19h or 18h, the letters its slot holds, the narrowest menu box (12h) a script
    draws while the table is loaded, or None)} for ADL5's tables a script loads (the shortest slot any
    load gives); {} for ADL."""
    if F is not adl5:
        return {}
    out = {}
    for name in scripts(vol, cfg):
        how, d = _read_script(vol, cfg, name)
        cur = None
        for s, _e in F.tokenize(d):
            if d[s] in (0x18, 0x19):
                t = d[s + 2:d.index(0, s + 2)].decode("cp932", "replace").upper() + ".EDT"
                op, room, box = out.get(t, (d[s], None, None))
                out[t] = (op, min(x for x in (room, 2 * d[s + 1]) if x is not None), box)
                if d[s] == 0x18:
                    cur = t
            elif d[s] == 0x12 and cur:
                op, room, box = out[cur]
                out[cur] = (op, room, min(x for x in (box, _box_cells(d, s)) if x is not None))
    return out


def _table_strings(raw):
    parts, _tail = adl.table_read(raw)
    return [p.decode("cp932", "replace") for p in parts]


def _program_runs(exe):
    """[(start, end, kind, fixed, text)] of the program's own strings (file offsets): ADL5.EXE's
    (pc98tl/adl5.py), ADL.EXE's save slots' names ("slot")."""
    if F is adl5:
        table = adl.kana_table(exe)
        out = []
        for s, e, kind, fixed in adl5.program_strings(exe):
            raw = exe[s:e]
            if kind == "run":
                text = _text_with_fixed(raw, fixed, table)
            else:
                text = raw.rstrip(b"\x00").decode("cp932", "replace")
            out.append((s, e, kind, fixed, text))
        return out
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    return [(hdr + at, hdr + at + SLOT_CELLS, "slot", [], jp) for at, jp in _slots(exe[hdr:])]


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
    _set_format(cfg)
    _open_store(vol, cfg)
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
    name_room, cmd_room = table_rooms(vol, cfg)
    menu_cells = cmd_room or CMD_CELLS
    starts = start_widths(vol, cfg)
    for name in scripts(vol, cfg):
        how, d = _read_script(vol, cfg, name)
        toks = F.tokenize(d)
        menu_cells = min([menu_cells] + [_box_cells(d, s) for s, _e in toks if d[s] == 0x12])
        if F.rebuild(d, toks, {}) != d:
            raise SystemExit("%s does not rebuild byte for byte" % name)
        width = starts.get(name.upper(), 0)
        flow = flow_widths(d, toks, width) if F is adl5 else {}
        choice_cells = {c: _widest(d, w, f) // 8 for w, (f, cs) in _menus(d, toks).items() for c in cs}
        box_items = {c: struct.unpack_from(">H", d, b + 1)[0] + struct.unpack_from(">H", d, b + 5)[0] - 8
                     for b, cs in _boxes(d, toks).items() for c in cs}
        firsts = {u[0]: u for u in units(d, toks)}
        for s, _e in toks:
            if d[s] == F.WINDOW_OP:
                width = F.window(d, s)[1] // 8
            if s in flow:
                width = flow[s]
            if s in firsts:
                _s, _starts, runs, between = firsts[s]
                jp = unit_text(d, runs, table)
                if not jp.replace("　", "").strip() or re.fullmatch(r"(\{X\d+\})*", jp.replace("　", "")):
                    continue
                note = "; ".join("{X%d}: %s" % (i + 1, _describe(c)) for i, c in enumerate(between)) or None
                cells = choice_cells.get(s, width)
                if d[s] == 0x71:
                    # (one line from its place to the screen's edge; a menu box's item, to the box's right
                    # edge less its margin)
                    cells = (box_items.get(s, SCREEN) - struct.unpack_from(">H", d, s + 1)[0]) // 8
                add("msg", jp, "%s:%04x" % (name, s), cells, note)
    slots = table_slots(vol, cfg)
    for name in tables(vol, cfg):
        kind = _table_kind(name, slots)
        if (name_room if kind == "name" else cmd_room) is None:
            continue
        if name.upper() in slots:
            _op, room, box = slots[name.upper()]
            cells = room if kind == "name" else min(room, box or menu_cells)
        else:
            cells = name_room if kind == "name" else menu_cells
        for i, jp in enumerate(_table_strings(_file_read(vol, cfg, name))):
            if jp.replace("　", "").strip():
                add(kind, jp, "%s:%d" % (name, i), cells)
    prog = cfg.get("program", "ADL.EXE")
    for s, e, kind, fixed, jp in _program_runs(exe):
        if kind == "slot":
            # (refs: offsets in the load image, as before)
            add("engine", jp, "%s:%04x" % (prog, s - hdr), SLOT_CELLS)
        else:
            note = "; ".join("{X%d}: a character the program writes there (the drive letter, the disk's number)"
                             % (n + 1) for n in range(len(fixed))) or None
            add("engine", jp, "%s:%04x" % (prog, s), (e - s) - 1 - 2 * len(fixed) if kind == "run" else 8, note)
    for pname in cfg.get("program_files", []):
        raw = vol.read(_path(cfg, pname))
        for s, e, fixed in adl5.graph_strings(raw):
            if not raw[s:e].decode("cp932", "replace").strip("　 ▼"):
                continue
            note = "; ".join("{X%d}: a character the program writes there (a digit)" % (n + 1)
                             for n in range(len(fixed))) or None
            add("engine", _text_with_fixed(raw[s:e], fixed, table), "%s:%04x" % (pname, s),
                (e - s) - 2 * len(fixed), note)
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


def _text_with_fixed(raw, fixed, table):
    """A run's or line's text, the characters at fixed (offsets) as {X1}, {X2}..."""
    text, at = "", 0
    for n, f in enumerate(fixed):
        text += adl.text_of(raw[at:f], table) + "{X%d}" % (n + 1)
        at = f + 2
    return text + adl.text_of(raw[at:], table)


def _fixed_line(text, raw, fixed, sid):
    """(a helper program's line in its own bytes: ASCII (one column each, the drawer's own space 20h),
    the characters the program rewrites kept at their places, NUL after; whether it was cut)."""
    room = len(raw)
    parts = TOKEN.split(text)[0::2] if fixed else [text]
    if len(parts) != len(fixed) + 1:
        raise SystemExit("%s: the English must keep %s" % (sid, ", ".join("{X%d}" % (i + 1) for i in range(len(fixed)))))
    out, cut = bytearray(), False
    for n, part in enumerate(parts):
        enc = _fixed(part, room)
        limit = fixed[n] if n < len(fixed) else room
        if len(out) + len(enc) > limit:
            enc, cut = enc[:max(0, limit - len(out))], True
        out += enc
        if n < len(fixed):
            out += b"\x20" * (fixed[n] - len(out)) + raw[fixed[n]:fixed[n] + 2]
    return bytes(out + bytes(room - len(out))), cut


def _fixed_run(text, raw, fixed, sid):
    """(a program message's run in its own bytes: 20h, the letters (7Fh a space), the characters the
    program rewrites ({X1}...) kept at their places, the rest 20h (each switching the half-width mode,
    drawing nothing); whether the English was cut)."""
    room = len(raw)
    parts = TOKEN.split(text)[0::2] if fixed else [text]
    if len(parts) != len(fixed) + 1:
        raise SystemExit("%s: the English must keep %s" % (sid, ", ".join("{X%d}" % (i + 1) for i in range(len(fixed)))))
    out, cut = bytearray(b"\x20"), False
    for n, part in enumerate(parts):
        enc = adl.encode_ascii(" ".join(_ascii(part).split("\n")))[1:]
        limit = fixed[n] if n < len(fixed) else room
        if len(out) + len(enc) > limit:
            enc, cut = enc[:max(0, limit - len(out))], True
        out += enc
        if n < len(fixed):
            pad = fixed[n] - len(out)
            if pad % 2:
                # (an odd number of 20h would leave the half-width mode off: one drawn space instead)
                out.append(0x7F)
                pad -= 1
            out += b"\x20" * pad
            out += raw[fixed[n]:fixed[n] + 2]
    return bytes(out + b"\x20" * (room - len(out))), cut


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(cfg, src)
    vol = img.volumes[0]
    _set_format(cfg)
    _open_store(vol, cfg)
    exe, hdr = _program(vol, cfg)
    table = adl.kana_table(exe[hdr:])
    prog = cfg.get("program", "ADL.EXE")
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        if mode == "pseudo":
            if e["kind"] == "msg":
                text = "".join(pseudo(e["id"], 2 * len(p)) if i % 2 == 0 and p.strip("　 ") else
                               ("{X%s}" % p if i % 2 else p) for i, p in enumerate(TOKEN.split(e["jp"])))
            elif TOKEN.search(e["jp"]):
                # (each piece its own filler, as long as the Japanese's bytes; the patcher cuts it to its room)
                text = "".join(pseudo(e["id"], 2 * len(p))[:2 * len(p)] if i % 2 == 0 else "{X%s}" % p
                               for i, p in enumerate(TOKEN.split(e["jp"])))
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
        path = _path(cfg, name)
        how, d = _read_script(vol, cfg, name)
        toks = F.tokenize(d)
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
        F.tokenize(new)
        _file_write(vol, cfg, name, F.encode(how, new))
        done += 1
    rooms = table_rooms(vol, cfg)
    slots = table_slots(vol, cfg)
    for name in tables(vol, cfg):
        parts, tail = adl.table_read(_file_read(vol, cfg, name))
        kind = _table_kind(name, slots)
        room = rooms[0] if kind == "name" else rooms[1]
        if room is not None and name.upper() in slots:
            room = slots[name.upper()][1]
        if room is None:
            continue
        changed = False
        for i in range(len(parts)):
            if (name, i) in by_ref:
                b = _fixed(by_ref[(name, i)], room)
                if len(_ascii(by_ref[(name, i)])) > room:
                    warn.append("%s: cut to %d letters (the table's slot)" % (ids[(name, i)], room))
                parts[i] = b
                changed = True
        if changed:
            _file_write(vol, cfg, name, adl.table_write(parts, tail))
    _close_store(vol)
    out_exe = bytearray(exe)
    for s, e, kind, fixed, jp in _program_runs(exe):
        key = (prog, s - hdr) if kind == "slot" else (prog, s)
        if key not in by_ref:
            continue
        if kind == "slot":
            b = _fixed(by_ref[key], SLOT_CELLS)
            out_exe[s:s + 17] = b + bytes(17 - len(b))
        elif kind == "word":
            b = _fixed(by_ref[key], 8)
            out_exe[s:e] = b + bytes(8 - len(b))
        else:
            b, cut = _fixed_run(by_ref[key], exe[s:e], fixed, ids[key])
            if cut:
                warn.append("%s: cut to the program's room (%d bytes)" % (ids[key], e - s))
            out_exe[s:e] = b
    vol.write(_path(cfg, prog), (F.patch_exe(bytes(out_exe), prog) if F is adl5 else F.patch_exe(bytes(out_exe))))
    for pname in cfg.get("program_files", []):
        raw = vol.read(_path(cfg, pname))
        out = bytearray(raw)
        for s, e, fixed in adl5.graph_strings(raw):
            if (pname, s) in by_ref:
                b, cut = _fixed_line(by_ref[(pname, s)], raw[s:e], fixed, ids[(pname, s)])
                if cut:
                    warn.append("%s: cut to the program's room (%d bytes)" % (ids[(pname, s)], e - s))
                out[s:e] = b
        vol.write(_path(cfg, pname), adl5.patch_graph(bytes(out), pname))
    for w in warn:
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
