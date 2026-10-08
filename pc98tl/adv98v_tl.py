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
* Pieces of text with only look-and-pace commands between them (colour,
  text speed, pauses, palette fades: A8, A9, AC, C4) are one message; the
  English replaces the whole of it, without those effects.
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
            pc98tl/illusion_game.py), "engine": "advh" (ADVH, the engine
            before Adv98V: see pc98tl/advh.py), "line_h" (line height in
            dots, 22 in ADVH), "menu_fullwidth" (an engine whose
            menus take Shift-JIS only), "text_files" ([files, relative to
            the game folder, of plain text the engine shows as it is: an
            opening roll]), "text_fullwidth" (the module that shows them
            draws Shift-JIS only: their lines in full-width letters),
            "program_files" ([other modules, relative to the game
            folder, whose strings are shown: a name entry module]),
            "program_fullwidth" (those modules draw Shift-JIS only: their
            strings in full-width letters), "data_files" ([data files,
            relative to the game folder, of names the engine shows: item,
            monster and enemy tables; see data_strings]) and
            "data_fullwidth" (their names in full-width letters),
            "table_files" ([string table files, relative to the game
            folder: a list box's lines, the load window's notes; see
            table_parse]) and "table_fullwidth" (their text in full-width
            letters),
            "program_fixes" ([{"file", "find",
            "replace", "why"}]: same-length byte-signature fixes in the
            engine's programs, e.g. a disk check that a hard-disk layout
            cannot pass), "default_frame" (the message box
            the startup script sets, in force where a script sets none),
            "wait" (hex of the pause put before the message-end
            procedure; see default_wait), "marker_cols" (columns at the
            right of the message box where the message end draws its wait
            marker, kept free of text), "page_break" (hex of the
            break between pages where a file has no message end of its
            own, in place of a key wait and the game's text reset: the
            oldest engines' and ADVH's 81 90, a key wait that clears the
            box), "script_room" (bytes the engine's script buffer holds,
            read off its memory: from where a script is loaded to the
            procedure table after it; a script that would outgrow it is
            refused), "keep_flag" (hex of the register set a script puts right
            before the message-end procedure where the next text goes on
            on the same page: the procedure waits for the key and skips
            its reset), "proc_fullwidth" (an engine that hangs on an ASCII
            string in a procedure body: the text of procedures, the
            speakers' name tags, is written in full-width letters),
            "var_cols" ({"n": columns}: what "DISP @n" shows where the
            engine shows more than the variable's own values, e.g. a
            surname shown with the given name after it), "boot_steps"}
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
from . import adv98v as av, advh, engine_strings

TEXT = ("chr1", "chr2", "str")
LINE_H, GLYPH_H = 20, 16
# the engine being patched (set by run_patch from game.json): "advh" for
# ADVH's half-width codes, "line_h" its line height in dots
ENGINE = {"advh": False, "line_h": LINE_H, "keep_flag": None, "proc_fullwidth": False,
          "var_cols": {}, "name_cols": 0}
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
            while j < len(toks):
                if toks[j][0] in TEXT or (_cmd(data, toks[j], 0xA5) and j + 1 < len(toks)
                                          and toks[j + 1][0] in TEXT):
                    j += 1
                    continue
                n = _effects(data, toks, j)
                if n and j + n < len(toks) and toks[j + n][0] in TEXT:
                    j += n
                    continue
                break
            # menu items keep their box; text in a procedure (a name tag) is
            # printed inline by its callers, so it is not wrapped or paged
            # (an item's text may sit in a block of its own inside the menu,
            # a flag picking one of two labels: still a menu item)
            kind = "item" if menu_depth and (not proc_depth or proc_depth[-1] < menu_depth[-1]) \
                else "inline" if proc_depth else "msg"
            out.append((i, j, kind, frame))
            i = j
            continue
        i += 1
    # a message run with a menu item's very text is that item drawn again
    # (the highlight of a menu the script draws itself): an item too
    items = {_bare(unit_text(data, toks, i, j)) for i, j, kind, _f in out if kind == "item"}
    return [(i, j, "item" if kind == "msg" and _bare(unit_text(data, toks, i, j)) in items else kind, f)
            for i, j, kind, f in out]


def _bare(text):
    """A label without the spaces that centre it."""
    return text.strip("\u3000 ")


def redraws(data, toks, us=None):
    """{unit index: (item text, columns)} of the runs that draw a menu item
    again (its highlight, with the item's centring spaces left out and
    placed past them): the item's text, and how many columns of leading
    spaces the item has that the run lacks."""
    us = us if us is not None else units(data, toks)
    texts = [unit_text(data, toks, i, j) for i, j, _k, _f in us]
    items = {}
    for n, (_i, _j, kind, _f) in enumerate(us):
        if kind == "item":
            items.setdefault(_bare(texts[n]), texts[n])
    out = {}
    for n, (_i, _j, kind, _f) in enumerate(us):
        item = items.get(_bare(texts[n]))
        if kind == "item" and item is not None and item != texts[n]:
            def lead(t):
                return 2 * (len(t) - len(t.lstrip("\u3000"))) + (len(t.lstrip("\u3000")) - len(t.lstrip("\u3000 ")))
            out[n] = (item, lead(item) - lead(texts[n]))
    return out


# commands that only change how text looks or how fast it comes (colour,
# text speed, a pause, a palette fade, the switch around the game's own
# symbols) and their number count: between two
# pieces of text they belong to one message
EFFECTS = {0xA8: 1, 0xA9: 1, 0xAC: 1, 0xC4: 2, 0xCB: 2}


def _effects(data, toks, j):
    """The token count of a run of look-and-pace commands at j (0: none)."""
    n = j
    while n < len(toks) and toks[n][0] == "cmd" and data[toks[n][1]] in EFFECTS:
        arity = EFFECTS[data[toks[n][1]]]
        if not all(n + 1 + q < len(toks) and toks[n + 1 + q][0] == "num" for q in range(arity)):
            break
        n += 1 + arity
    return n - j


def procs(data, toks):
    """{number: (body start, body end)} of the procedures a file defines
    (B9 n A2 ... A3): the body is what the engine copies to the
    procedure's slot, from after the A2 to its matching A3, both ends
    included.  A number defined more than once (a speaker's tag set anew
    for each speaker) gives its last definition; proc_defs lists them
    all."""
    return {n: (bs, be) for n, bs, be in proc_defs(data, toks)}


def proc_defs(data, toks):
    """[(number, body start, body end)] of every procedure definition in
    a file, in order (see procs)."""
    out, x = [], 0
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
            out.append((_num(data, toks[x + 1][1]), toks[y][2], toks[z][2]))
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
        if k == "num" or (k == "cmd" and data[s] != 0xA5):
            continue                    # look-and-pace commands inside a message
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
    text and prints nothing counts (a game may call one that prints an
    ellipsis first, or a scene effect that resets the box and prints the
    next speaker's tag, which a page break must not repeat)."""
    seen = collections.Counter()
    for _i, j, kind, _f in units(data, toks):
        if kind != "msg":
            continue
        for x in range(j, min(j + 12, len(toks) - 1)):
            k, s, _e = toks[x]
            if k == "cmd" and data[s] == 0xBA and toks[x + 1][0] == "num":
                call = bytes(data[s:toks[x + 1][2]])
                eff = effects.get(_call_num(call), ("none",)) if effects is not None else None
                if eff is not None and (eff[0] != "reset" or eff[1]):
                    continue
                seen[call] += 1
                break
            if k in TEXT:
                break
    return max((c, b) for b, c in seen.items())[1] if seen else None


def _subdir(vol, game_dir, kind):
    """The game folder's subfolder for scripts or modules ("MES", "TCM"):
    named so, or ending in "_MES" ("GIBO_MES"), or else ending in "MES"
    ("IREGMES"); None if there is none."""
    dirs = [e["name"] for e in vol.listdir(_cluster(vol, game_dir)) if e["is_dir"]]
    for name in dirs:
        if name.upper() == kind or name.upper().endswith("_" + kind):
            return _join(game_dir, name)
    for name in dirs:
        if name.upper().endswith(kind):
            return _join(game_dir, name)
    return None


def _cluster(vol, folder):
    """A folder's first cluster ("" is the root)."""
    return vol.find(folder)["cluster"] if folder else 0


def _join(folder, name):
    return folder + "/" + name if folder else name


def _full_name(vol, game_dir, name):
    """A script's _files name (upper case) from its own name: START.MES,
    or MES_1/START.MES where it sits in another script folder."""
    names = [n.upper() for n, _p in _files(vol, game_dir)]
    return name.upper() if name.upper() in names else [n for n in names if n.split("/")[-1] == name.upper()][0]


def mes_path(vol, game_dir, name):
    files = dict((n.upper(), p) for n, p in _files(vol, game_dir))
    if name.upper() in files:
        return files[name.upper()]
    # (a script in a numbered folder, MES_1/START.MES, by its own name)
    return [p for n, p in files.items() if n.split("/")[-1] == name.upper()][0]


KEY = bytes([0xAB])          # wait for a key or click


def default_wait(vol, game_dir, extraop):
    """The short pause the games put before the message-end procedure
    (which waits for the key itself): D1 1 3 0 where the game's D1 takes three
    numbers (the later builds), else none (the earlier builds' D1 takes
    two)."""
    counts = collections.Counter()
    for _name, path in _files(vol, game_dir):
        data = vol.read(path)
        toks = av.tokenize(data, extraop)
        for x, (k, s, _e) in enumerate(toks[:-3]):
            if k == "cmd" and data[s] == 0xD1:
                n = 0
                while n < 3 and toks[x + 1 + n][0] == "num":
                    n += 1
                counts[n] += 1
    return WAIT if counts[3] > counts[2] else b""


def end_gap(data, toks, us, proc, effects):
    """What the file writes after a message from its message-end call to
    the next text, as most often: the call, then the text resets (AA) and
    the frame or reset procedures that follow it, up to the next name tag,
    name or other text.  A page break repeats it, so the next page is in
    the same cleared frame as the next message would be.  None where the
    file has no message that ends with the call (the caller uses the
    game's usual one)."""
    seen = collections.Counter()
    for _i, j, kind, _f in us:
        if kind != "msg" or j + 1 >= len(toks):
            continue
        k, s, _e = toks[j]
        if not (k == "cmd" and data[s] == 0xBA and bytes(data[s:toks[j + 1][2]]) == proc):
            continue
        x = j + 2
        while x < len(toks):
            k, s, _e = toks[x]
            if k == "cmd" and data[s] == 0xAA:
                x += 2 if x + 1 < len(toks) and toks[x + 1][0] == "num" else 1
                continue
            if k == "cmd" and data[s] == 0xBA and x + 1 < len(toks) and toks[x + 1][0] == "num" and                     effects.get(_num(data, toks[x + 1][1]), ("none",))[0] == "reset":
                x += 2
                continue
            break
        seen[bytes(data[toks[j][1]:toks[x - 1][2]])] += 1
    return max((c, b) for b, c in seen.items())[1] if seen else None


def inline_end(data, toks, us=None):
    """A file's message end written out after its messages instead of a
    procedure call: the commands most often right after a message, up to
    and including a text reset (AA n); starting with the key wait (AB) or
    a timed pause (AC n) they pace themselves, else a key wait goes first.  None
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
    # (one that starts with its own wait or a timed pause, as in a timed
    # opening that takes no keys, stays as it is)
    return seq if seq[0] in (0xAB, 0xAC) else KEY + seq


def _files(vol, game_dir):
    """The scripts: [(name, path)], from the MES folder and, where the
    game keeps its MEC files apart, the MEC folder; and any in the game
    folder itself (a startup script kept beside the engine)."""
    out = [(e["name"], _join(game_dir, e["name"])) for e in vol.listdir(_cluster(vol, game_dir))
           if not e["is_dir"] and e["name"].upper().endswith(".MES")]
    main = [_subdir(vol, game_dir, kind) for kind in ("MES", "MEC")]
    for folder in main:
        if folder:
            out += [(e["name"], folder + "/" + e["name"]) for e in vol.listdir(vol.find(folder)["cluster"])
                    if not e["is_dir"] and e["name"].upper().endswith((".MES", ".MEC"))]
    # (more script folders beside the main one: MES_02, MES_T1 (Custom Mate 3), or numbered ones
    # instead of it, MES_1 to MES_7 (Hatsukoi Monogatari); their files are named FOLDER/FILE, as a
    # name may repeat between folders)
    for e in vol.listdir(_cluster(vol, game_dir)):
        folder = _join(game_dir, e["name"])
        if e["is_dir"] and e["name"].upper().startswith("MES") and folder not in main:
            out += [(e["name"] + "/" + f["name"], folder + "/" + f["name"]) for f in vol.listdir(e["cluster"])
                    if not f["is_dir"] and f["name"].upper().endswith((".MES", ".MEC"))]
    return out


def _script_name(arg, names):
    """The _files name a script's file argument ("mes_t1\\t1111.mec",
    "b:\\mes\\open.mes") points to: FOLDER/FILE where that is a name, else
    the file's own name."""
    parts = arg.replace("\\", "/").split(":")[-1].strip("/").split("/")
    two = "/".join(parts[-2:]).upper()
    return two if two in names else parts[-1].upper()


def start_script(vol, game_dir, extraop):
    """The script the engine runs first: the one the game's INI (itself a
    script, its tail often encrypted; in the game folder or one below)
    names, else START.MES."""
    inis = []
    for e in vol.listdir(_cluster(vol, game_dir)):
        if e["is_dir"] and e["name"] not in (".", "..", "DOS", "TOOLS"):
            inis += [_join(game_dir, e["name"]) + "/" + f["name"] for f in vol.listdir(e["cluster"])
                     if not f["is_dir"] and f["name"].upper().endswith(".INI")]
        elif e["name"].upper().endswith(".INI"):
            inis.insert(0, _join(game_dir, e["name"]))
    for ini in inis:
        # (every build's INI has its encrypted tail after D5, which the
        # scripts of the earliest builds otherwise never use)
        raw = vol.read(ini)
        toks = av.tokenize(raw, True)
        # (the decrypted tail is only searched, not tokenized: some builds
        # keep code after its end mark)
        for data in [raw] + [av.decrypt(raw[s:e], _num(raw, [t for t in toks if t[2] == s][0][1]))
                             for k, s, e in toks if k == "crypt"]:
            m = re.search(rb'"(?:[a-z]:)?\\?(?:\w*mes\\)?([^"\\]+\.mes)"', data, re.I)
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


DOS_PROGRAMS = {"COMMAND.COM", "IO.SYS", "MSDOS.SYS"}     # the base disk's own, beside a root install
PROGRAM_EXT = (".COM", ".EXE", ".OV1", ".OVL", ".TCM")
_HERO = re.compile(rb"@\d+='([^']+)'")


def _programs(vol, game_dir, extra=()):
    """The engine's program files (the game folder's and its TCM modules',
    and extra: game.json's "program_files", other modules relative to the
    game folder): [(name, path)]."""
    out = [(name, _join(game_dir, name)) for name in extra]
    tcm = _subdir(vol, game_dir, "TCM")
    for folder in [game_dir] + ([tcm] if tcm else []):
        prefix = folder[len(game_dir) + 1 if game_dir else 0:] + "/" if folder != game_dir else ""
        out += [(prefix + e["name"], _join(folder, e["name"])) for e in vol.listdir(_cluster(vol, folder))
                if not e["is_dir"] and e["name"].upper().endswith(PROGRAM_EXT)
                and not (folder == "" and e["name"].upper() in DOS_PROGRAMS)]
    return out


def _is_table(text):
    """A character table the name entry picks from by position: kana,
    full-width letters and Japanese punctuation without kanji, or kana in
    code order (a stray code byte may sit before it)."""
    body = [c for c in text if c != "　"]
    if len(body) >= 20 and all("、" <= c <= "ヿ" or "！" <= c <= "～" for c in body):
        return True
    # (a typing table's run of full-width letters, digits and symbols)
    if len(body) >= 2 and all("！" <= c <= "～" or c in "‘’“”" for c in body):
        return True
    # tables list kana in code order: six or more rising kana in a row
    run = best = 0
    for prev, c in zip([""] + body, body):
        kana = "ぁ" <= c <= "ヶ"
        run = run + 1 if kana and prev and "ぁ" <= prev <= "ヶ" and c > prev else (1 if kana else 0)
        best = max(best, run)
    return best >= 6


def _swapped_table(exe, s, e):
    """A run that is really part of a character table stored as
    little-endian words (a name entry's kana keys, 0xa0 0x82 for あ): read
    as byte-swapped words from s or from the byte before it, every word in
    it is kana or a full-width letter or digit."""
    for at in (s, s - 1):
        words = [exe[k + 1] << 8 | exe[k] for k in range(max(at, 0), e - 1, 2)]
        if len(words) >= 3 and all(0x824F <= w <= 0x82F1 or 0x8340 <= w <= 0x8396 for w in words):
            return True
    return False


def table_parse(data):
    """A string table file (game.json "table_files": a list box's lines,
    the load window's chapter notes): a table of little-endian word
    offsets to NUL-ended Shift-JIS strings (CR for a line break), either
    with the count first (count, offset...) or without (offset..., the
    lowest offset giving the count).  Returns (head bytes before the
    table, [offsets]) or None."""
    words = lambda n, at: [data[at + 2 * k] | data[at + 2 * k + 1] << 8 for k in range(n)]
    if len(data) < 4:
        return None
    first = words(1, 0)[0]
    for head, n in ((2, first), (0, first // 2)):
        if not n or head + 2 * n > len(data):
            continue
        offs = words(n, head)
        # (entries may share a string, so the offsets need not rise)
        if min(offs) == head + 2 * n and max(offs) < len(data) and all(b"\x00" in data[at:] for at in offs):
            return data[:head], offs
    return None


def table_strings(data):
    """[(index, text)] of a string table's strings with text, each under
    the first entry that points to it (see table_parse); a CR is a line
    break (\\n)."""
    head, offs = table_parse(data)
    out, seen = [], set()
    for n, at in enumerate(offs):
        if at in seen:
            continue
        seen.add(at)
        # (a CR ending the string stays the patch's to write back: not part of the text)
        text = _line_text(data[at:data.index(b"\x00", at)].rstrip(b"\r")).replace("\r", "\n")
        if text.strip(" 　\n"):
            out.append((n, text))
    return out


def patch_table(data, texts, sids, warn, fullwidth):
    """The string table rebuilt with the English (texts: {index: text},
    index as table_strings gives it), the strings in their old order and
    every offset moved to match.  It is loaded into a buffer of the
    file's size, so it may not grow: the strings that would overrun it
    are kept in Japanese and reported."""
    head, offs = table_parse(data)
    starts = sorted(set(offs))
    old = {at: data[at:data.index(b"\x00", at)] for at in starts}
    new = dict(old)
    for n, text in texts.items():
        ends = len(old[offs[n]]) - len(old[offs[n]].rstrip(b"\r"))
        new[offs[n]] = b"\r".join(_line_bytes(line, fullwidth) for line in text.split("\n")) + b"\r" * ends
    size = lambda: len(data) + sum(len(new[at]) - len(old[at]) for at in starts)
    for n in sorted(texts, reverse=True):
        if size() <= len(data):
            break
        warn.append("%s: the table outgrows its file (%d bytes), kept in Japanese" % (sids[n], len(data)))
        new[offs[n]] = old[offs[n]]
    pos, moved, body = len(head) + 2 * len(offs), {}, b""
    for k, at in enumerate(starts):
        # (bytes between one string's NUL and the next string, and after the last, go along)
        gap = data[at + len(old[at]) + 1:starts[k + 1] if k + 1 < len(starts) else len(data)]
        moved[at] = pos
        body += new[at] + b"\x00" + gap
        pos += len(new[at]) + 1 + len(gap)
    out = head + b"".join(bytes([moved[at] & 0xFF, moved[at] >> 8]) for at in offs) + body
    return out.ljust(len(data), b"\x00")


_DRUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]| )+")


def data_strings(data):
    """[(start, end, text)] of the names in a data file (game.json
    "data_files": item, monster and enemy tables, a battle prompt): runs
    of whole Shift-JIS characters and spaces, split at ＠ (the engine's
    blank, which pads fixed-width fields).  start..end is the room the
    English may take: the run with the spaces around the name and the ＠
    padding after it; text is the name without them."""
    out = []
    for m in _DRUN.finditer(data):
        pos, pieces, at, piece = m.start(), [], m.start(), ""
        raw = m.group()
        i = 0
        while i < len(raw):
            if raw[i] == 0x20:
                ch, n = " ", 1
            else:
                try:
                    ch, n = raw[i:i + 2].decode("cp932"), 2
                except UnicodeDecodeError:
                    ch, n = None, 2
            if ch == "＠":
                if piece.strip(" 　"):
                    pieces.append([at, pos, piece])
                if pieces and pieces[-1][1] == pos:
                    pieces[-1][1] = pos + n        # the padding is the field's room
                at, piece = pos + n, ""
            elif ch is None:
                if piece.strip(" 　"):
                    pieces.append([at, pos, piece])
                at, piece = pos + n, ""
            else:
                piece += ch
            pos += n
            i += n
        if piece.strip(" 　"):
            pieces.append([at, pos, piece])
        for s, e, text in pieces:
            body = text.strip(" 　")
            if all("぀" <= c <= "ヿ" or "一" <= c <= "鿿" or "！" <= c <= "～" or c in " 　、。・ー★☆〜「」『』"
                   for c in body):
                out.append((s, e, body))
    return out


def _data_field(data, s, e, text, wide, warn, sid):
    """A data file name's bytes for its field s..e (see data_strings): the
    English (full-width letters, wide) cut to the room in whole letters
    and padded as the field was: with ＠ where its padding was ＠, else
    with the NUL or FF that ends it, else spaces."""
    enc = _fullwidth(text, None) if wide else _plain(text)
    if len(enc) > e - s:
        warn.append("%s: %d bytes, the field has room for %d" % (sid, len(enc), e - s))
        enc = enc[:(e - s) // 2 * 2] if wide else enc[:e - s]
    if data[e - 2:e] == "＠".encode("cp932"):
        fill = "＠".encode("cp932") * ((e - s - len(enc)) // 2) + b" " * ((e - s - len(enc)) % 2)
    elif e < len(data) and data[e] in (0x00, 0xFF):
        fill = bytes([data[e]]) * (e - s - len(enc))
    else:
        fill = (b"\x81\x40" if wide else b" ") * ((e - s - len(enc)) // (2 if wide else 1))
        fill += b" " * (e - s - len(enc) - len(fill))
    return enc + fill


def program_strings(exe):
    """[(start, end, text)] of the Japanese in a program, with rows of
    labels split at their full-width spaces so each label keeps its place
    (the name window picks a label by where it is clicked), and fields
    padded with ＠ (the engine's blank, a data file's fixed-width names)
    split at it."""
    out = []
    for s, e, text in engine_strings.find(exe):
        if _is_table(text) or _swapped_table(exe, s, e):
            continue
        pos, piece, at = s, "", s
        while pos <= e:
            ch, n = engine_strings.char_at(exe, pos) if pos < e else ("　", 0)
            if ch in "　＠":
                if piece.strip():
                    out.append((at, pos, piece))
                piece, at = "", pos + n
            else:
                piece += ch
            pos += n or 1
    return out


def _all_japanese(raw):
    """An argument that is Japanese text only (a name entry's default)."""
    try:
        text = raw.decode("cp932")
    except UnicodeDecodeError:
        return False
    return bool(text) and all(ord(c) >= 0x3000 for c in text)


_SET = re.compile(rb"@(\d+)='([^']*)'")


def variable_widths(vol, game_dir, extraop, name_cols):
    """{n: columns}: the widest value the scripts give string variable @n
    (@n='...').  The English of a value keeps to its byte length (see
    var_strings), so that is its width on screen; a name the player
    enters is up to name_cols."""
    out = {}
    for _name, path in _files(vol, game_dir):
        data = vol.read(path)
        for k, s, e in av.tokenize(data, extraop):
            if k != "arg":
                continue
            for m in _SET.finditer(data[s:e]):
                n = int(m.group(1))
                out[n] = max(out.get(n, 0), len(m.group(2)), name_cols)
    return out


def text_file_lines(data):
    """A plain Shift-JIS text file the engine shows as it is (CR LF lines,
    ended by 1A): [(line text, byte length)] of its lines with text."""
    body = data.split(b"\x1a")[0]
    return [(_line_text(raw), len(raw)) for raw in body.split(b"\r\n")
            if raw.decode("cp932", "replace").strip("\u3000 ")]


def _line_text(raw):
    """A line of Shift-JIS, a PC-98 own character (a lead byte from EB, or
    one cp932 lacks) as {Uxxxx}, as in the scripts."""
    out, i = [], 0
    while i < len(raw):
        b = raw[i]
        if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < len(raw):
            pair = raw[i:i + 2]
            out.append("{U%s}" % pair.hex() if b >= 0xEB or _undecodable(pair) else pair.decode("cp932"))
            i += 2
        else:
            out.append(raw[i:i + 1].decode("cp932", "replace"))
            i += 1
    return "".join(out)


def _line_bytes(text, fullwidth):
    """A text file line's bytes: {Uxxxx} as those bytes, the rest ASCII (or
    full-width letters, fullwidth) and Shift-JIS."""
    out = b""
    for n, part in enumerate(_UTOK.split(" ".join(text.split("\n")))):
        out += bytes.fromhex(part) if n % 2 else (_fullwidth(part, None) if fullwidth else _plain(part))
    return out


def patch_text_file(data, texts, sids, warn, fullwidth=False):
    """The file with its text lines replaced (None: kept).  It is loaded
    into a fixed place in memory, so it keeps its size: each line is cut
    to its Japanese byte length and padded with spaces to it.  fullwidth:
    the module that shows it draws Shift-JIS only, so the letters are
    written full-width (two bytes each)."""
    body = data.split(b"\x1a")[0]
    tail = data[len(body):]
    out, n = [], 0
    for raw in body.split(b"\r\n"):
        if not raw.decode("cp932", "replace").strip("\u3000 "):
            out.append(raw)
            continue
        text = texts[n]
        if text is None:
            out.append(raw)
        else:
            enc = _line_bytes(text, fullwidth)
            if len(enc) > len(raw):
                warn.append("%s: %d bytes, the line holds %d" % (sids[n], len(enc), len(raw)))
                enc = enc[:len(raw) // 2 * 2] if fullwidth else enc[:len(raw)]
            out.append(enc.ljust(len(raw)))
        n += 1
    return b"\r\n".join(out) + tail


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
                try:
                    text = raw.decode("cp932")
                except UnicodeDecodeError:
                    continue            # a PC-98 symbol of its own, not text
                if not text.strip("　 "):
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
                    target = _script_name(arg, sizes)
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


def tight_files(vol, game_dir, extraop):
    """The file names whose room in the MEC buffer is their own size (the
    only file loaded there, or one packed against the next), so they may
    not grow: their menu items keep their byte length (item_budget)."""
    rooms = mec_rooms(vol, game_dir, extraop)
    return {name.upper() for name, path in _files(vol, game_dir)
            if rooms.get(name.upper()) == len(vol.read(path))}


def item_budget(nbytes):
    """The letters a menu item of nbytes takes when it keeps its length:
    the ASCII string's 21 and 00 come out of it."""
    return max(0, nbytes - 2)


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
    floppy drives) mapped as installed (game.json "drive_prefix"),
    wherever a path starts in an argument (its start, or after a space or
    comma: "prog.exe b:\\x.prs,5")."""
    if not prefixes:
        return data
    out, pos = bytearray(), 0
    for k, s, e in av.tokenize(data, extraop):
        if k != "arg":
            continue
        inner = bytes(data[s + 1:e - 1])
        moved = inner
        for old, new in prefixes.items():
            moved = re.sub(rb"(?i)(^|[ ,])" + re.escape(old.encode("ascii")),
                           lambda m: m.group(1) + new.encode("ascii"), moved)
        if moved != inner:
            out += data[pos:s + 1] + moved
            pos = e - 1
    return bytes(out + data[pos:])


# ---- extraction ------------------------------------------------------------------------------
def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    img, cfg = _image(cfg, src)
    vol = img.volumes[0]
    merged, order, caps = {}, [], {}
    tight = tight_files(vol, cfg["game_dir"], cfg.get("extraop", False))
    for name, path in _files(vol, cfg["game_dir"]):
        data = vol.read(path)
        for tag, d, toks in _streams(data, cfg.get("extraop", False)):
            again = redraws(d, toks)
            for n, (i, j, kind, frame) in enumerate(units(d, toks)):
                jp = unit_text(d, toks, i, j)
                if not jp.strip():
                    continue
                cells = unit_cells(d, toks, i, j)
                if n in again:
                    # a menu item drawn again: the item's own string
                    jp = again[n][0]
                    cells = -(-sum(2 if ord(c) > 0x7F else 1 for c in _UTOK.sub("　", jp)) // 2)
                key = (kind, jp)
                if kind == "item" and name.upper() in tight:
                    # a menu item in a file that may not grow keeps its bytes
                    cap = item_budget(toks[j - 1][2] - toks[i][1]) // 2
                    caps[key] = min(caps.get(key, cap), cap)
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
    for name in cfg.get("text_files", []):
        lines = text_file_lines(vol.read(_join(cfg["game_dir"], name)))
        extra += [("file", name, "%d" % n, 0, 0, text, raw_len // 2) for n, (text, raw_len) in enumerate(lines)]
    for name, path in _programs(vol, cfg["game_dir"], cfg.get("program_files", ())):
        extra += [("engine", name, "%04x" % s, s, e, text, (e - s) // 2)
                  for s, e, text in program_strings(vol.read(path))]
    for name in cfg.get("data_files", []):
        extra += [("engine", name, "%04x" % s, s, e, text, (e - s) // 2)
                  for s, e, text in data_strings(vol.read(_join(cfg["game_dir"], name)))]
    for name in cfg.get("table_files", []):
        found = table_strings(vol.read(_join(cfg["game_dir"], name)))
        # (the window's width: its widest Japanese line; the strings share the file's bytes)
        wide = max(_width(line) for _n, text in found for line in text.split("\n")) // 2
        extra += [("file", name, "%d" % n, 0, 0, text, wide) for n, text in found]
    for kind, name, at, _s, _e, jp, cells in extra:
        key = (kind, jp)
        if key not in merged:
            merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [], "max_cells": cells}
            order.append(key)
        merged[key]["refs"].append("%s:%s" % (name, at))
        merged[key]["max_cells"] = min(merged[key]["max_cells"], cells)
    for key, cap in caps.items():
        merged[key]["max_cells"] = min(merged[key]["max_cells"], cap)
    prefix = {"msg": "m", "item": "i", "inline": "n", "var": "v", "engine": "e", "file": "t"}
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
    padded to cells (None: as long as the text)."""
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
    return (out if cells is None else out[:cells].ljust(cells, "　")).encode("cp932")


def _num_bytes(n):
    """A number in the script's encoding (adv98v._num reads it)."""
    if n <= 4:
        return bytes([0x23 + n])
    if n < 256:
        return bytes([0x28, n])
    return bytes([0x29 + n // 0x4000, n % 0x4000 // 0x80, n % 0x80])


def _encode(text):
    """A line as a 21 string: ASCII as it is, {Uxxxx} as those SJIS bytes,
    anything else as SJIS.  For ADVH (ENGINE["advh"]) the letters are its
    half-width codes (pc98tl/advh.py), not a string."""
    out = b""
    for n, part in enumerate(_UTOK.split(text)):
        if n % 2:
            out += bytes.fromhex(part)
        elif ENGINE["advh"]:
            out += advh.encode("".join(_SUBST.get(c, c) for c in part))
        else:
            out += _plain(part)
    return out if ENGINE["advh"] else b"\x21" + out + b"\x00"


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
    return x2 - x1, max(1, (y2 - y1 - GLYPH_H) // ENGINE["line_h"] + 1)


def build(text, kind, frame, cells, brk, warn, sid, start=(0, 0), reserve=0, down=0, max_cols=None,
          max_rows=None, fullwidth=False, pages_ok=False, marker=0, budget=None):
    """English for a text run: (the bytes to put in its place, the (line,
    column) it ends at).  A message starts at start (line, column) of its
    page and leaves reserve columns at its end for what is printed after
    it on its line; down: the lines what follows moves on before the next
    text (which must stay inside the frame); max_cols, max_rows: a
    narrower width and fewer lines than the frame's to keep to;
    marker: columns kept free at the right of the box for the wait
    marker; pages_ok: a message in a one-line frame that ends with a key wait
    or the message end, so it pages a line at a time (else it keeps its
    Japanese width: a prompt with a field after it); fullwidth: menu
    items written as full-width characters (older
    engines draw a menu from Shift-JIS only, and crash on an ASCII
    string in one); budget: the letters a menu item may take in a file
    that may not grow (see tight_files)."""
    size = frame_size(frame)
    if kind in ("item", "inline", "label") or not size or (size[1] == 1 and not (pages_ok and brk)
                                                                    and not (ENGINE["advh"] and brk)):
        # text in a one-line frame often has more drawn after it on the
        # line (an input field, numbers), so it keeps its Japanese width
        # (a label placed on the screen, too)
        room = 2 * cells if kind == "item" or not size else size[0] if kind == "inline" else min(size[0], 2 * cells)
        if kind == "item" and budget is not None:
            room = min(room, budget)
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
    if marker and kind == "msg":
        cols -= marker      # the message end's wait marker sits at the box's right edge
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
                 frames=None, fallback=None, fullwidth=False, default_frame=None, wait=WAIT, marker=0,
                 forced_break=None, tight=False, game_gap=None):
    """The stream with its text runs replaced.  table: (slot bytes, slot
    count, the startup script's procedure numbers).  A procedure body may grow to
    the larger of its own length and its room in the procedure table;
    past that it would overwrite a procedure in force, so the build is
    refused, or with fit (the --pseudo filler) the body's texts are cut
    to fit.  With no table (a game whose procedures hold no text, so it
    was not measured) a procedure may not grow.  tight: a file that may
    not grow (tight_files), whose menu items keep their byte length.
    game_gap: {message-end call: the game's usual message end after it},
    for a file whose own messages never end with the call."""
    defs = procs(data, toks)
    every = proc_defs(data, toks)
    room = proc_room(defs, table[2], table[0], table[1]) if table else {}
    reps = {}
    us = units(data, toks, frames, default_frame)
    again = redraws(data, toks, us)
    # the oldest engines' key wait clears the box: a page end
    clears = (forced_break or fallback) == KEY_WAIT
    starts = [_start(data, toks, i, proc, insert, effects or {}, clears) for i, _j, _k, _f in us]
    # a page break: a wait and the message-end procedure, or the file's
    # own message end where it has none
    # (the message-end procedure waits for the key itself, as after every
    # original message: only the build's short pause goes before it)
    own = end_gap(data, toks, us, proc, effects or {}) if proc else None
    if proc and (not own or own == proc):
        # (a bare call does not clear the box: the game's usual end does,
        # up to its clears; the frame it sets after them is a speaker's)
        usual = (game_gap or {}).get(proc, proc)
        gt, keep = av.tokenize(usual, False), len(proc)
        for gk, gs, ge in gt:
            if gs >= len(proc) and gk == "cmd" and usual[gs] != 0xAA:
                break
            keep = max(keep, ge)
        own = usual[:keep]
    brk = (wait + own) if proc else         inline_end(data, toks, us) or forced_break or fallback
    end = None                          # where the last message replaced ended
    for n, (i, j, kind, frame) in enumerate(us):
        ref = "%s:%s%d" % (name, tag, n)
        text = by_ref.get(ref)
        cont, down, col, _need, located = starts[n]
        if text is None:
            # a run kept as it is (blank padding that centres a line, or
            # one left untranslated): on one line, what follows starts
            # past its Japanese width
            if any(k == "cmd" and data[s2] == 0xA5 for k, s2, _e in toks[i:j]):
                end = None
            else:
                at = ((end[0] + down, col) if down else (end[0], end[1] + col)) if cont and end else (down, col)
                end = (at[0], at[1] + 2 * unit_cells(data, toks, i, j))
            continue
        # a message after text on its page starts where that text ended,
        # moved on by what was printed between
        start = ((end[0] + down, col) if down else (end[0], end[1] + col)) if cont and end else (down, col)
        # room for what is printed after it on its line (a name, an
        # ellipsis), and the lines that moves on before more text
        reserve, down, follows = _after(data, toks, j, proc, insert, effects or {}, clears)
        down = down if follows else 0
        s, e = toks[i][1], toks[j - 1][2]
        # a question with a menu after it keeps to its Japanese lines'
        # width: the menu's window is drawn over the frame's right side
        # and its Japanese line count (the menu may sit on the frame's next
        # line; longer English pages first)
        narrow = _line_cols(data, toks, i, j) if _menu_follows(data, toks, j) else None
        # (its Japanese line count from the line it starts on)
        lines = start[0] + 1 + sum(1 for k, s2, _e in toks[i:j] if k == "cmd" and data[s2] == 0xA5) \
            if narrow else None
        if n + 1 < len(us) and starts[n + 1][0] and frame and kind == "msg":
            # text placed next on this page (A7) at a line of the frame:
            # this message keeps above that line (pages sooner if need be)
            spot = starts[n + 1][4]
            if spot and spot[0] is not None and spot[0] >= frame[0] and spot[1] > frame[1]:
                above = (spot[1] - frame[1]) // ENGINE["line_h"]
                if above > 0:
                    lines = min(lines, above) if lines else above
        bkind = kind
        if located and kind == "inline":
            bkind = "label"         # a marker placed by a procedure (the wait arrow)
        if kind == "inline" and any(bs <= s < be and any(k2 == "cmd" and data[s2] == 0xA6 and s2 >= toks[j - 1][2]
                                                          and s2 < be for k2, s2, _e2 in toks[j:j + 8])
                                    for _pn, bs, be in every):
            # procedure text the procedure then sets a frame after (a
            # quote mark before the message's frame): it keeps its width
            bkind = "label"
        if located and kind == "msg":
            # placed text: a label at its Japanese width, or, with lines
            # of its own, a message starting where it is placed
            x, y = located
            if lines is None and any(k == "cmd" and data[s2] == 0xA5 for k, s2, _e in toks[i:j]) and frame                     and x is not None and x >= frame[0] and y >= frame[1]:
                start = ((y - frame[1]) // ENGINE["line_h"], x - frame[0])
            else:
                bkind = "label"
        # a page break whose procedure sets another frame (the file's usual
        # message end, from a full-screen scene) goes on in this message's
        page_brk = brk
        if brk and frame and len(frame) == 4 and frames:
            set_by = [frames.get(_num(brk, t[1])) for x2, t in enumerate(av.tokenize(brk, False))
                      if t[0] == "num" and x2 and brk[av.tokenize(brk, False)[x2 - 1][1]] == 0xBA]
            if any(isinstance(f2, tuple) and len(f2) == 4 and f2 != tuple(frame) for f2 in set_by):
                page_brk = brk + b"\xa6" + b"".join(_num_bytes(c) for c in frame)
        j2 = j
        while j2 < len(toks) and toks[j2][0] == "cmd" and data[toks[j2][1]] == 0xA5:
            j2 += 1                     # (line breaks the message ends with)
        if j2 + 2 < len(toks) and toks[j2][0] == "cmd" and data[toks[j2][1]] == 0xAB \
                and toks[j2 + 1][0] == "cmd" and data[toks[j2 + 1][1]] == 0xAA and toks[j2 + 2][0] == "num":
            # the message ends with its own key wait and clear: its pages
            # end the same way (not with a procedure other messages call)
            page_brk = bytes(data[toks[j2][1]:toks[j2 + 2][2]])
        elif page_brk and not proc:
            # a written-out page end clears the box the way this message's
            # own box was set up (the nearest AA n before it), not with the
            # file's or game's most common clear (which may paint a panel)
            own_aa = None
            for x2 in range(i - 1, max(-1, i - 64), -1):
                k2, s2, _e2 = toks[x2]
                if k2 == "cmd" and data[s2] == 0xAA and x2 + 1 < len(toks) and toks[x2 + 1][0] == "num":
                    own_aa = bytes(data[s2:toks[x2 + 1][2]])
                    break
                if k2 in TEXT or (k2 == "cmd" and data[s2] == 0xA6):
                    break
            bt = av.tokenize(page_brk, False)
            for x2, (k2, s2, _e2) in enumerate(bt):
                if own_aa and k2 == "cmd" and page_brk[s2] == 0xAA and x2 + 1 < len(bt) and bt[x2 + 1][0] == "num":
                    page_brk = page_brk[:s2] + own_aa + page_brk[bt[x2 + 1][2]:]
                    break
        new, end = build(text, bkind, frame, unit_cells(data, toks, i, j),
                         page_brk, warn, ids.get(ref, ref), start, reserve, down, narrow, lines, fullwidth,
                         _waits_after(data, toks, j, proc), marker,
                         item_budget(e - s) if tight else None)
        if end is None and bkind == "label" and located and frame and located[0] is not None \
                and located[0] >= frame[0] and located[1] >= frame[1]:
            # a label placed in the frame (A7): what follows it on its
            # line starts where it ends
            shown = sum(max(0, (e2 - s2) - 2) for k2, s2, e2 in av.tokenize(new, False) if k2 == "str")
            shown += sum(2 for k2, _s2, _e2 in av.tokenize(new, False) if k2 in ("chr1", "chr2"))
            end = ((located[1] - frame[1]) // ENGINE["line_h"], located[0] - frame[0] + shown)
        if ENGINE["proc_fullwidth"] and any(bs <= s < be for _pn, bs, be in every):
            # the engine hangs on an ASCII string in a procedure body
            new = _fullwidth(" ".join(text.split("\n")), None)
        reps[s] = (e, ids.get(ref, ref), new)
        if n in again and again[n][1]:
            # a menu item drawn again, placed past the item's centring
            # spaces, which the English item does not have: placed at the
            # item's own column
            for x2 in range(i - 1, max(-1, i - 24), -1):
                k2, s2, _e2 = toks[x2]
                if k2 in TEXT:
                    break
                if k2 == "cmd" and data[s2] == 0xA7 and x2 + 1 < len(toks) and toks[x2 + 1][0] == "num":
                    xs, xe = toks[x2 + 1][1], toks[x2 + 1][2]
                    col = _num(data, xs) - again[n][1]
                    if col >= 0 and xs not in reps:
                        reps[xs] = (xe, ids.get(ref, ref), _num_bytes(col))
    # every definition of a procedure is copied to its slot when it runs
    for pn, bs, be in every:
        limit = max(be - bs, room.get(pn, 0))
        inside = sorted(s for s in reps if bs <= s < be)
        grown = (be - bs) + sum(len(reps[s][2]) - (reps[s][0] - s) for s in inside)
        if grown <= limit:
            continue
        if not fit:
            raise SystemExit("%s%s: procedure %d would be %d bytes, it may take %d (strings %s); shorten them"
                             % (name, tag and " " + tag, pn, grown, limit, ", ".join(reps[s][1] for s in inside)))
        # each text gets its old bytes and an even share of the room left
        spare = limit - (be - bs)
        for s in inside:
            e, sid, new = reps[s]
            keep = max(1, (e - s) + spare // len(inside) - 2)
            if ENGINE["proc_fullwidth"] or ENGINE["advh"]:
                reps[s] = (e, sid, new[:max(2, keep) // 2 * 2])
            else:
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
    a procedure sets (the last A6 in the body), ("call", [numbers]) when it
    sets none itself but calls others (resolved by resolve_frames), or
    None (so a definition that sets none replaces one from another file
    that does)."""
    out = {}
    for pn, (bs, be) in procs(data, toks).items():
        out[pn], calls = None, []
        for x, (k, s, _e) in enumerate(toks):
            if not bs <= s < be or k != "cmd":
                continue
            if data[s] == 0xA6:
                nums = [t for t in toks[x + 1:x + 5] if t[0] == "num"]
                if len(nums) == 4:
                    out[pn] = tuple(_num(data, t[1]) for t in nums)
            elif data[s] == 0xBA and x + 1 < len(toks) and toks[x + 1][0] == "num":
                calls.append(_num(data, toks[x + 1][1]))
        if out[pn] is None and calls:
            out[pn] = ("call", calls)
    return out


def resolve_frames(frames):
    """The frames in force: a procedure that sets none itself takes the
    frame of what it calls (the last call that sets one; where it picks
    one of several by a flag, they set the same box)."""
    def frame(pn, seen):
        f = frames.get(pn)
        if isinstance(f, tuple) and f and f[0] == "call":
            got = [frame(c, seen | {pn}) for c in f[1] if c not in seen]
            got = [g for g in got if g]
            return got[-1] if got else None
        return f
    return {pn: frame(pn, frozenset()) for pn in frames}


def proc_effects(data, toks, name, tag, by_ref, proc, name_cols=0, var_cols=None):
    """{number: facts} of the procedures a stream defines, read off their
    bodies, for resolve_effects: the columns of text they print (the
    Japanese's or the English's, the wider; a string variable shown with
    "DISP @n" counts as its variable's widest value, var_cols {n:
    columns}, or as a name of name_cols), their line breaks (A5),
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
        width, free = 0, 0
        placed = [toks[y][1] for y in body if toks[y][0] == "cmd" and data[toks[y][1]] == 0xA7]
        for y in body:
            if toks[y][0] == "arg":
                m = _DISP.match(bytes(data[toks[y][1]:toks[y][2]]))
                if m:
                    # a variable shown: as wide as its longest value, or a name
                    width += var_cols.get(int(m.group(1)), name_cols) if var_cols else name_cols
        for n, (i, j, _kind, _f) in enumerate(us):
            if bs <= toks[i][1] < be:
                en = by_ref.get("%s:%s%d" % (name, tag, n))
                flat = " ".join(en.split("\n")) if en else ""
                # (written full-width there, each letter two columns)
                wide = 2 * len(flat) if ENGINE["proc_fullwidth"] else _width(flat)
                width += max(2 * unit_cells(data, toks, i, j), wide)
                if not any(at < toks[i][1] for at in placed):
                    free += max(2 * unit_cells(data, toks, i, j), wide)
        out[pn] = {"width": width, "free": free, "breaks": cmds.count(0xA5),
                   "reset": bool(set(cmds) & {0xA6, 0xAA, 0xAB}) or (proc is not None and proc in calls),
                   "calls": [_call_num(c) for c in calls]}
    return out


_DISP = re.compile(rb'^"DISP @(\d+)"$')


def resolve_effects(layers):
    """{number: effect} in force on the text cursor, from layers of
    proc_effects facts (later ones over earlier ones), with what a
    procedure calls counted as its own: ("tag", columns) prints text and
    ends its line (a speaker's name tag); ("insert", columns) prints text
    on the line; ("reset", columns) sets the frame or clears the text
    (columns: what it prints as well on the text cursor, a name tag after
    a flash; a wait marker placed with A7 does not count); ("break",
    n) only breaks the line n times; ("none",) leaves the cursor alone
    (pictures, sounds, flags)."""
    facts = {}
    for layer in layers:
        facts.update(layer)

    def total(pn, seen):
        f = facts.get(pn)
        if f is None or pn in seen:
            return 0, 0, False, 0
        width, breaks, reset, free = f["width"], f["breaks"], f["reset"], f.get("free", f["width"])
        for c in f["calls"]:
            w, b, r, fr = total(c, seen | {pn})
            width, breaks, reset, free = width + w, breaks + b, reset or r, free + fr
        return width, breaks, reset, free

    eff = {}
    for pn in facts:
        width, breaks, reset, free = total(pn, frozenset())
        if reset:
            # (free: what it prints on the text cursor, not a marker
            # placed at a fixed spot with A7)
            eff[pn] = ("reset", free, breaks)
        elif width:
            eff[pn] = ("tag", width) if breaks else ("insert", width)
        elif breaks:
            eff[pn] = ("break", breaks)
        else:
            eff[pn] = ("none",)
    return eff


def _call_num(call):
    return av._num(call, 1) if len(call) > 1 else None


def _start(data, toks, i, proc, insert, effects, clears=False):
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
    gap, stop = _gap(data, toks, i, -1, proc, insert, effects, clears)
    lines, cols, need = _layout(data, gap, insert, effects)
    located = None
    for y, (k, s, _e) in enumerate(gap):
        if k == "cmd" and data[s] == 0xA7:
            nums = [t for t in gap[y + 1:y + 3] if t[0] == "num"]
            located = tuple(_num(data, t[1]) for t in nums) if len(nums) == 2 else (None, None)
    return stop == "text", lines, cols, need, located


def _waits_after(data, toks, j, proc):
    """Whether a text run is followed by a key wait (81 90) or the
    message-end procedure call."""
    if j >= len(toks):
        return False
    k, s, e = toks[j]
    if k == "ctrl" and bytes(data[s:e]) == b"\x81\x90":
        return True
    return bool(proc) and k == "cmd" and data[s] == 0xBA and j + 1 < len(toks) and         bytes(data[s:toks[j + 1][2]]) == proc


KEY_WAIT = bytes([0x81, 0x90])


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


def _after(data, toks, j, proc, insert, effects, clears=False):
    """What follows a text run up to the next text or page end: (need,
    lines, text follows) as in _start, read forward."""
    gap, stop = _gap(data, toks, j, 1, proc, insert, effects, clears)
    lines, _cols, need = _layout(data, gap, insert, effects)
    return need, lines, stop == "text" and not any(k == "cmd" and data[s] == 0xA7 for k, s, _e in gap)


def _gap(data, toks, at, step, proc, insert, effects, clears=False):
    """The tokens from at (back from before it, or on from it) to the
    nearest text or page end: (tokens in order, "text"/"reset"/None).
    clears: a key wait (81 90) is a page end too."""
    gap, x, stop = [], at - 1 if step < 0 else at, None
    while 0 <= x < len(toks) and abs(x - at) <= 32:
        k, s, _e = toks[x]
        if k in TEXT:
            stop = "text"
            break
        if (k == "cmd" and data[s] in (0xA6, 0xAA, 0xAB)) or (k == "ctrl" and clears
                                                               and bytes(data[s:_e]) == KEY_WAIT):
            stop = "reset"
            break
        if k == "cmd" and data[s] == 0xBA and x + 1 < len(toks) and toks[x + 1][0] == "num":
            call = bytes(data[s:toks[x + 1][2]])
            # the register set that makes the message end keep the page
            kept = (ENGINE["keep_flag"] and x > 0 and toks[x - 1][0] == "reg"
                    and bytes(data[toks[x - 1][1]:toks[x - 1][2]]) == ENGINE["keep_flag"])
            if not kept and (call == proc or (not (insert and call == insert[0])
                                              and effects.get(_call_num(call), ("none",))[0] == "reset")):
                stop = "reset"
                eff = effects.get(_call_num(call), ("none",))
                if step < 0 and call != proc and len(eff) > 2 and eff[2]:
                    # a reset that then prints a speaker's tag and breaks
                    # the line: the text after it starts lines down
                    gap.append(toks[x])
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
        elif k == "arg" and _DISP.match(bytes(data[s:e])):
            # a variable shown on the line: as wide as its widest value
            advance(ENGINE["var_cols"].get(int(_DISP.match(bytes(data[s:e])).group(1)), ENGINE["name_cols"]), 0)
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
            elif eff[0] == "reset" and len(eff) > 2 and eff[2]:
                advance(eff[1], eff[2])
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
            fixed = e["kind"] in ("item", "var", "engine", "file")
            text = pseudo(e["id"], 2 * e["max_cells"], 1.0 if fixed else 2.5)
            if fixed:
                text = text[:2 * e["max_cells"]]
        if not text:
            continue
        for r in e["refs"]:
            by_ref[r] = text
            ids[r] = e["id"]
    extraop = cfg.get("extraop", False)
    ENGINE["advh"] = cfg.get("engine") == "advh"
    ENGINE["line_h"] = cfg.get("line_h", LINE_H)
    ENGINE["keep_flag"] = bytes.fromhex(cfg["keep_flag"]) if "keep_flag" in cfg else None
    ENGINE["proc_fullwidth"] = cfg.get("proc_fullwidth", False)
    if ENGINE["advh"]:
        exe_path = _join(cfg["game_dir"], "ADVH.EXE")
        vol.write(exe_path, advh.patch(vol.read(exe_path)))
    for fix in cfg.get("program_fixes", []):
        # (byte-signature fixes in the engine's programs, the same length)
        path = _join(cfg["game_dir"], fix["file"])
        exe = vol.read(path)
        find, repl = bytes.fromhex(fix["find"]), bytes.fromhex(fix["replace"])
        if exe.count(find) != 1 or len(find) != len(repl):
            raise SystemExit("%s: the signature for '%s' is not found once" % (fix["file"], fix["why"]))
        vol.write(path, exe.replace(find, repl))
    for _name, path in _files(vol, cfg["game_dir"]):
        data = vol.read(path)
        moved = strip_drives(data, extraop, cfg.get("drive_prefix"))
        if moved != data:
            vol.write(path, moved)
    # the scripts run before the scenes, in order (the startup script and
    # what it chains to): their procedures are in force in every scene
    # that does not define its own
    base = [_full_name(vol, cfg["game_dir"], n)
            for n in cfg.get("base_scripts", [start_script(vol, cfg["game_dir"], extraop)])]
    name_cols = cfg.get("name_cols", cfg.get("name_insert", {}).get("cols", 0))
    var_cols = variable_widths(vol, cfg["game_dir"], extraop, name_cols)
    var_cols.update({int(n): cols for n, cols in cfg.get("var_cols", {}).items()})
    ENGINE["var_cols"], ENGINE["name_cols"] = var_cols, name_cols
    fit = mode == "pseudo"
    default_frame = tuple(cfg["default_frame"]) if cfg.get("default_frame") else None
    # procedures defined only in other files: each number's widest
    # definition anywhere, under the base scripts'
    anywhere, frames_anywhere = {}, {}
    for oname, opath in _files(vol, cfg["game_dir"]):
        odata = vol.read(opath)
        otoks = av.tokenize(odata, extraop)
        for pn, f in proc_effects(odata, otoks, oname, "", by_ref, None, name_cols, var_cols).items():
            if pn not in anywhere or f["width"] > anywhere[pn]["width"]:
                anywhere[pn] = f
        frames_anywhere.update({pn: f for pn, f in proc_frames(odata, otoks).items()
                                if f and f[0] != "call"})
    start_eff, base_nums = dict(anywhere), set()
    for bname in base:
        bdata = vol.read(mes_path(vol, cfg["game_dir"], bname))
        btoks = av.tokenize(bdata, extraop)
        base_nums |= set(procs(bdata, btoks))
        frames_anywhere.update(proc_frames(bdata, btoks))
        plain = resolve_effects([start_eff, proc_effects(bdata, btoks, bname, "", by_ref, None, name_cols, var_cols)])
        start_eff.update(proc_effects(bdata, btoks, bname, "", by_ref, end_proc(bdata, btoks, plain), name_cols, var_cols))
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
    wait = bytes.fromhex(cfg["wait"]) if "wait" in cfg else default_wait(vol, cfg["game_dir"], extraop)
    game_break = KEY + resets.most_common(1)[0][0] if resets else None
    forced = bytes.fromhex(cfg["page_break"]) if "page_break" in cfg else None
    ins = cfg.get("name_insert")
    insert = (bytes.fromhex(ins["call"]), bytes.fromhex(ins["flag"]), ins["cols"]) if ins else None
    variables = var_strings(vol, cfg["game_dir"], extraop, name_cols)
    rooms = mec_rooms(vol, cfg["game_dir"], extraop)
    tight = tight_files(vol, cfg["game_dir"], extraop)
    # each message-end call's usual message end across the game's files,
    # for a file that only pages with it (a question before a menu)
    gaps = collections.defaultdict(collections.Counter)
    for oname, opath in _files(vol, cfg["game_dir"]):
        odata = vol.read(opath)
        otoks = av.tokenize(odata, extraop)
        oeff = resolve_effects([start_eff, proc_effects(odata, otoks, oname, "", {}, None, name_cols, var_cols)])
        oproc = end_proc(odata, otoks, oeff)
        if oproc:
            ogap = end_gap(odata, otoks, units(odata, otoks), oproc, oeff)
            if ogap:
                gaps[oproc][ogap] += 1
    game_gap = {c: g.most_common(1)[0][0] for c, g in gaps.items()}
    for name in cfg.get("text_files", []):
        path = _join(cfg["game_dir"], name)
        old_file = vol.read(path)
        new_file = patch_text_file(old_file, [by_ref.get("%s:%d" % (name, n))
                                              for n in range(len(text_file_lines(old_file)))],
                                   [ids.get("%s:%d" % (name, n), "%s:%d" % (name, n))
                                    for n in range(len(text_file_lines(old_file)))], warn,
                                   cfg.get("text_fullwidth", False))
        if new_file != old_file:
            vol.write(path, new_file)
    for name in cfg.get("table_files", []):
        path = _join(cfg["game_dir"], name)
        old_file = vol.read(path)
        found = table_strings(old_file)
        texts = {n: by_ref["%s:%d" % (name, n)] for n, _t in found if "%s:%d" % (name, n) in by_ref}
        new_file = patch_table(old_file, texts, {n: ids.get("%s:%d" % (name, n)) for n, _t in found}, warn,
                               cfg.get("table_fullwidth", False))
        if new_file != old_file:
            vol.write(path, new_file)
    # (program_fullwidth applies to the program_files modules, data_fullwidth to the data files)
    written = [(name, path, program_strings, cfg.get("program_fullwidth") and name in cfg.get("program_files", ()))
               for name, path in _programs(vol, cfg["game_dir"], cfg.get("program_files", ()))]
    written += [(name, _join(cfg["game_dir"], name), data_strings, cfg.get("data_fullwidth", False))
                for name in cfg.get("data_files", [])]
    for name, path, finder, wide in written:
        exe = vol.read(path)
        runs = finder(exe)
        values = {}
        for s, e, _t in runs:
            ref = "%s:%04x" % (name, s)
            if ref in by_ref:
                flat = " ".join(by_ref[ref].split("\n"))
                if finder is data_strings:
                    values[s] = _data_field(exe, s, e, flat, wide, warn, ids[ref])
                elif wide:
                    # (cut and padded to whole characters here: the module reads two bytes a letter)
                    whole = _fullwidth(flat, None)
                    values[s] = _fullwidth(flat, (e - s) // 2)
                    if len(whole) > e - s:
                        warn.append("%s: %d bytes, the program has room for %d" % (ids[ref], len(whole), e - s))
                else:
                    values[s] = _plain(flat)
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
                                                             name_cols, var_cols)])
            proc = end_proc(data, streams[0][2], plain)
            nums = table[:2] + (set(),) if table and name.upper() in base else table
            effects = resolve_effects([start_eff, proc_effects(data, streams[0][2], name, "", texts, proc,
                                                                    name_cols, var_cols)])
            frames = resolve_frames({**frames_anywhere, **proc_frames(data, streams[0][2])})
            new = patch_stream(data, streams[0][2], "", name, texts, ids, proc, warn, nums, insert, fit, effects,
                               frames, game_break, cfg.get("menu_fullwidth", False), default_frame, wait,
                               cfg.get("marker_cols", 0), forced, name.upper() in tight, game_gap)
            if len(streams) > 1:
                # the tails: re-encrypt each rebuilt tail in place of the old one
                toks = av.tokenize(new, extraop)
                crypts = [t for t in toks if t[0] == "crypt"]
                out, pos = bytearray(), 0
                for (tag, inner, itoks), (_k, s, e) in zip(streams[1:], crypts):
                    key = _num(new, [t for t in toks if t[2] == s][0][1])
                    effects = resolve_effects([start_eff, proc_effects(inner, itoks, name, tag, texts, proc,
                                                                            name_cols, var_cols)])
                    rebuilt = patch_stream(inner, itoks, tag, name, texts, ids,
                                           end_proc(inner, itoks, effects) or proc, warn, nums, insert, fit, effects,
                                           resolve_frames({**frames, **proc_frames(inner, itoks)}), game_break,
                                           cfg.get("menu_fullwidth", False), default_frame, wait,
                                           cfg.get("marker_cols", 0), forced, name.upper() in tight, game_gap)
                    out += new[pos:s] + av.encrypt(rebuilt, key)
                    pos = e
                new = bytes(out + new[pos:])
            return new

        new = rebuild(by_ref)
        room = rooms.get(name.upper())
        where = "its place in the engine's MEC buffer"
        if not room and cfg.get("script_room"):
            # a script is run from the engine's script buffer, which ends
            # where the procedure table starts
            room, where = cfg["script_room"], "the engine's script buffer"
        if room and len(new) > room:
            mine = sorted({ids[r] for r in by_ref if r.startswith(name + ":")})
            if not fit:
                raise SystemExit("%s: %d bytes with the English, %s holds %d "
                                 "(strings %s); shorten them" % (name, len(new), where, room, ", ".join(mine)))
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
