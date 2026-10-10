"""Silky's "General Message system-1" games (Be-Yond): the script out to
strings.json and the English patch (the formats are in pc98tl/silky.py).

The game is laid out on a DOS hard disk the way its own installer does
(game.json "hdd", see pc98tl/illusion_game.py): every disk's archive in
the game folder.

English is drawn by the engine itself: a text statement in mode 2 takes
single-byte characters and draws them half-width (8x16, the font ROM's),
which the game uses for its half-width katakana sound effects.  So each
message is written as 4Ah 02, its letters, 00, the lines wrapped between
words to the text window with 04 (a new line) where the next word would
pass the window's right edge; the engine starts a new page by itself when
a line would pass the window's bottom.  The window is the last one 46h
set (its left and right columns: the first and third arguments), the
game's message box before any (game.json "message_window": its left and
right columns, set where the scripts cannot be read for it, by the system
library; Be-Yond's 17-62 where it is not given).  The cursor's column goes
on from one text statement to the next and back to 0 at a new line (04),
at 49h, 4Fh and 50h (the box cleared) and at 46h.

String variable values (45h's inline strings: FFh, the mode, the text,
NUL; names and menu labels the script keeps in a variable and shows with
4Bh) are written as FFh 02, the letters (an even number of them: 4Bh
copies the string a word at a time up to a zero word) and NUL, within the
variable's 32-byte slot (a string variable, type 0Eh; another kind keeps
the Japanese's bytes).  4Bh's string is printed where the script prints
it: in a message, {N} (the text statements around it are one string), and
the patcher keeps NAME_COLS columns for it as it wraps (the hero's name
from the name entry, whose kana and kanji grid stays Japanese).

The programs' own Japanese (game.json "program_files": SL.EXE's error
messages, MUSIC.COM's notices) is rewritten in place (pc98tl/
engine_strings.py), each DOS message ($-ended) a string of its own, its
room the Japanese's bytes; SL.EXE is unpacked for it and packed again with
its own EXEPACK unpacker.

A script is loaded at SS:0000 and the system library after it (6Eh loads
it at SS:7918h in Be-Yond, read off SL.EXE): a script may not reach it, so
a build whose script outgrows that room is refused, naming the script's
strings (the --pseudo filler is cut instead until it fits).
"""
import json
import os
import re
import struct

from . import silky
from .alice_sys2_tl import sha256

MAIN_WINDOW = (17, 62)
# the columns a variable's string printed with 4Bh takes (the hero's name, from the name entry)
NAME_COLS = 12
# a string variable's slot (type 0Eh: 20h bytes apart, SL.EXE's variable table)
STRING_SLOT = 32
SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "♥": "<3"}
PREFIX = {"msg": "m", "var": "v", "engine": "e"}


def _install(cfg, src):
    """(the image to patch, its config): the game's own hard-disk image, or
    its floppies laid out on one (cfg "hdd")."""
    if not cfg.get("hdd"):
        from .disk import DiskImage
        return DiskImage(src), cfg
    from .illusion_game import _hdd_install
    return _hdd_install(cfg, src)


def script_room(exe):
    """Where 6Eh loads the system library in SS (push ss / pop es / mov di, n / call; the
    scripts' own loads are at 0), read off SL.EXE (unpacked)."""
    found = {struct.unpack("<H", m)[0] for m in re.findall(rb"\x16\x07\xbf(..)\xe8", exe, re.S)} - {0}
    if len(found) != 1:
        raise SystemExit("SL.EXE: the system library's place is not found once")
    return found.pop()


def _sl_exe(vol, game_dir, program="SL.EXE"):
    from . import exepack
    e = vol.read(game_dir + "/" + program)
    u = exepack.unpack(e) if exepack.is_packed(e) else e
    return u[struct.unpack_from("<H", u, 8)[0] * 16:]


def archives(vol, game_dir):
    """The game folder's archives (DISKA...), by name."""
    return sorted(e["name"] for e in vol.listdir(vol.find(game_dir)["cluster"])
                  if re.fullmatch(r"DISK[A-Z]", e["name"].upper()))


def _const_args(d, s, e):
    """The constants of an argument list s..e (each a one-item expression), None for any other."""
    out, i = [], s
    while i < e and d[i] != 0:
        if 1 <= d[i] <= 2 and d[i + 1 + d[i]] == 0:
            out.append(int.from_bytes(d[i + 1:i + 1 + d[i]], "little"))
            i += 2 + d[i]
        else:
            return None
    return out


def _is_text(d, s):
    return d[s] == 0x4A and d[s + 1] == 1


def _is_copy(d, s, e):
    """45h copying a variable into a variable (not an inline string)."""
    return d[s] == 0x45 and d[silky._var(d, s + 1) + 1] >= 5


def groups(d, toks):
    """[[token indexes of the text statements]] of the runs of text that
    print a variable's string between them (text, then any number of: a
    variable copied (45h), 4Bh printing it, text): one message with the
    name in it."""
    out, k = [], 0
    while k < len(toks):
        if not _is_text(d, toks[k][0]):
            k += 1
            continue
        run = [k]
        j = k + 1
        while True:
            m = j
            while m < len(toks) and _is_copy(d, *toks[m][:2]):
                m += 1
            if m + 1 < len(toks) and d[toks[m][0]] == 0x4B and _is_text(d, toks[m + 1][0]):
                run.append(m + 1)
                j = m + 2
            else:
                break
        out.append(run)
        k = run[-1] + 1
    return out


def units(d, toks):
    """[(kind, start, end, jp, window width, text statement starts)] of a
    script: "msg" a run of text statements in mode 1 (see groups; {N} where
    a variable's string is printed), "var" 45h's inline string (start..end
    its string)."""
    dic = silky.dictionary(d)
    first = {run[0]: run for run in groups(d, toks)}
    win = MAIN_WINDOW
    out = []
    for k, (s, e, _w) in enumerate(toks):
        op = d[s]
        if op == 0x46:
            args = _const_args(d, s + 1, e)
            if args and len(args) >= 3:
                win = (args[0], args[2])
        elif k in first:
            run = first[k]
            jp = "{N}".join(silky.text_of(d, toks[m][0], toks[m][1], dic) for m in run)
            if jp.replace("{N}", "").strip("　 \n"):
                out.append(("msg", s, toks[run[-1]][1], jp, win[1] - win[0] + 1, [toks[m][0] for m in run]))
        elif op == 0x45:
            j = silky._var(d, s + 1)
            if d[j] == 0xFF and d[j + 1] == 1:
                end = d.index(bytes(1), j)
                jp = d[j + 2:end].decode("cp932", "replace")
                if jp.strip("　 "):
                    # (a string variable (type 0Eh) is a 32-byte slot: FFh, the mode, the letters, NUL;
                    # another kind keeps the Japanese's bytes)
                    room = STRING_SLOT - 4 if d[s + 1] == 0x0E else end - j - 2
                    out.append(("var", j, end, jp, room, []))
    return out


def _ascii(text):
    """English as the engine's single-byte characters (ASCII, half-width
    katakana); anything else as ?."""
    out = bytearray()
    for c in "".join(SUBST.get(c, c) for c in text):
        try:
            b = c.encode("cp932")
        except UnicodeEncodeError:
            b = b"?"
        out += b if len(b) == 1 and b not in (b"\x00", b"\x04") else b"?"
    return bytes(out)


def wrap(text, width, col):
    """(the bytes of a mode-2 text: letters and 04 new lines, wrapped
    between words at width columns from column col, the column it ends at)"""
    out = bytearray()
    for n, para in enumerate(text.split("\n")):
        if n:
            out.append(4)
            col = 0
        words = para.split(" ")
        for k, word in enumerate(words):
            w = _ascii(word)
            lead = b" " if k and col else b""
            if col and col + len(lead) + len(w) > width:
                out.append(4)
                col, lead = 0, b""
            while len(w) > width:
                # (a word longer than a line: cut at the edge)
                room = width - col
                out += w[:room] + b"\x04"
                w, col = w[room:], 0
            out += lead + w
            col += len(lead) + len(w)
    return bytes(out), col


def rebuild(d, toks, values):
    """The script with English in values ({start of a unit: text})."""
    us = {s: (kind, e, jp, w) for kind, s, e, jp, w, _p in units(d, toks)}
    # (each text statement of a translated message: its piece of the English, split at {N})
    piece = {}
    for kind, s, _e, _jp, _w, parts in units(d, toks):
        if kind == "msg" and s in values:
            texts = values[s].split("{N}")
            texts = texts[:len(parts) - 1] + ["".join(texts[len(parts) - 1:])]
            texts += [""] * (len(parts) - len(texts))
            piece.update(zip(parts, texts))
    new = {}
    dic = silky.dictionary(d)
    col = 0
    win_w = MAIN_WINDOW[1] - MAIN_WINDOW[0] + 1
    for s, e, _w in toks:
        op = d[s]
        if op == 0x46:
            args = _const_args(d, s + 1, e)
            if args and len(args) >= 3:
                win_w = args[2] - args[0] + 1
            col = 0
        elif op in (0x49, 0x4F, 0x50):
            col = 0
        elif op == 0x4B:
            # (a variable's string printed: the longest the game puts there)
            col += NAME_COLS
        elif op == 0x4A:
            if s in piece:
                body, col = wrap(piece[s], win_w, col)
                new[s] = b"\x4a\x02" + body + b"\x00"
            else:
                jp = silky.text_of(d, s, e, dic) if d[s + 1] == 1 else ""
                for c in jp:
                    col = 0 if c == "\n" else col + 2
        elif op == 0x45:
            j = silky._var(d, s + 1)
            if j in values and j in us:
                kind, end, jp, room = us[j]
                name = _ascii(" ".join(values[j].split("\n")))
                name = name[:room]
                if len(name) % 2:
                    name = name + b" " if len(name) < room else name[:-1]
                new[s] = d[s:j] + b"\xff\x02" + name + d[end:e]
    return silky.rebuild(d, toks, new)


def _scripts(vol, cfg):
    """[(ref name, archive, member)] of every script in the game's archives."""
    out = []
    for arc_name in archives(vol, cfg["game_dir"]):
        arc = silky.Archive(vol.read(cfg["game_dir"] + "/" + arc_name))
        out += [("%s/%s" % (arc_name, n), arc_name, n) for n in arc.names() if n.upper().endswith(".MES")]
    return out


def _program(vol, path):
    """(the file as it is, its load image or the file itself, the header size)"""
    from . import exepack
    raw = vol.read(path)
    if not exepack.is_packed(raw):
        return raw, raw, 0
    u = exepack.unpack(raw)
    hdr = struct.unpack_from("<H", u, 8)[0] * 16
    return raw, u[hdr:], hdr


def program_strings(data):
    """[(start, end, text)] of a program's Japanese, each $-ended DOS message on its own."""
    from . import engine_strings
    out = []
    for s, e, text in engine_strings.find(data):
        pos = s
        for part in data[s:e].split(b"$"):
            if part.strip():
                out.append((pos, pos + len(part), part.decode("cp932", "replace")))
            pos += len(part) + 1
    return out


def _write_program(vol, path, raw, data, hdr):
    from . import exepack
    if hdr:
        vol.write(path, exepack.pack(raw, bytes(data)))
    else:
        vol.write(path, bytes(data))


def _set_window(cfg):
    """The message box before any 46h: game.json "message_window" [left, right], else Be-Yond's."""
    global MAIN_WINDOW
    MAIN_WINDOW = tuple(cfg.get("message_window", (17, 62)))


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    _set_window(cfg)
    img, cfg2 = _install(cfg, src)
    vol = img.volumes[0]
    merged, order = {}, []
    arcs = {}
    for ref_name, arc_name, member in _scripts(vol, cfg2):
        arc = arcs.setdefault(arc_name, silky.Archive(vol.read(cfg2["game_dir"] + "/" + arc_name)))
        d = arc.read(member)
        toks = silky.tokenize(d)
        if silky.rebuild(d, toks, {}) != d:
            raise SystemExit("%s does not rebuild byte for byte" % ref_name)
        for kind, s, _e, jp, cells, _parts in units(d, toks):
            key = (kind, jp)
            ref = "%s:%04x" % (ref_name, s)
            if key in merged:
                merged[key]["refs"].append(ref)
                merged[key]["max_cells"] = min(merged[key]["max_cells"], cells)
                continue
            merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells}
            order.append(key)
    for name in cfg.get("program_files", []):
        _raw, data, _hdr = _program(vol, cfg2["game_dir"] + "/" + name)
        for s, e, text in program_strings(data):
            key = ("engine", text)
            if key not in merged:
                merged[key] = {"kind": "engine", "jp": text, "en": "", "refs": [], "max_cells": (e - s) // 2}
                order.append(key)
            merged[key]["refs"].append("%s:%04x" % (name, s))
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
                if "note" in prev:
                    e["note"] = prev["note"]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _cut(text, ratio):
    """text cut to ratio of its length (at least four letters), its closing new line kept."""
    body = text[:-1] if text.endswith("\n") else text
    return body[:max(min(len(body), 4), int(len(body) * ratio))] + text[len(body):]


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    _set_window(cfg)
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img, cfg2 = _install(cfg, src)
    vol = img.volumes[0]
    room = script_room(_sl_exe(vol, cfg2["game_dir"], cfg.get("program", "SL.EXE")))
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        if mode == "pseudo":
            # (each piece between the names its own filler, the names kept)
            text = "{N}".join(pseudo(e["id"], 2 * len(p.replace("\n", ""))) + ("\n" if p.endswith("\n") else "")
                              if p.strip("　 \n") else p for p in e["jp"].split("{N}"))
            if e["kind"] in ("var", "engine"):
                text = text[:e["max_cells"] * (2 if e["kind"] == "engine" else 1)]
        else:
            text = e["en"]
        for r in e["refs"]:
            f, a = r.rsplit(":", 1)
            ids[(f, int(a, 16))] = e["id"]
            if text:
                by_ref[(f, int(a, 16))] = text
    warn, done = [], 0
    arcs, changed = {}, {}
    for ref_name, arc_name, member in _scripts(vol, cfg2):
        arc = arcs.setdefault(arc_name, silky.Archive(vol.read(cfg2["game_dir"] + "/" + arc_name)))
        d = arc.read(member)
        toks = silky.tokenize(d)
        values = {a: t for (f, a), t in by_ref.items() if f == ref_name}
        if not values:
            continue
        new = rebuild(d, toks, values)
        if len(new) > room and mode != "pseudo":
            raise SystemExit("%s: %d bytes, a script may take %d (the system library follows it); "
                             "shorten these strings: %s" % (ref_name, len(new), room, ", ".join(
                                 sorted({ids[(ref_name, a)] for a in values}))))
        cut = 0
        while len(new) > room:
            # (the --pseudo filler: every string cut in proportion until the script fits)
            total = sum(len(v) for v in values.values())
            ratio = max(0.0, 1 - (len(new) - room) * 1.1 / max(1, total))
            before = total
            values = {a: _cut(v, ratio) for a, v in values.items()}
            after = sum(len(v) for v in values.values())
            if after >= before:
                raise SystemExit("%s: the script does not fit even with its filler cut" % ref_name)
            cut += before - after
            new = rebuild(d, toks, values)
        if cut:
            warn.append("%s: the filler was cut by %d letters to fit the script's room" % (ref_name, cut))
        silky.tokenize(new)
        changed.setdefault(arc_name, {})[member] = new
        done += 1
    for name in cfg.get("program_files", []):
        from . import engine_strings
        path = cfg2["game_dir"] + "/" + name
        raw, data, hdr = _program(vol, path)
        runs = program_strings(data)
        values = {s: _ascii(" ".join(by_ref[(name, s)].split("\n")))
                  for s, _e, _t in runs if (name, s) in by_ref}
        if values:
            new, cut = engine_strings.apply(data, runs, values)
            for s, need, room in cut:
                warn.append("%s: %d bytes, the program has room for %d" % (ids[(name, s)], need, room))
            _write_program(vol, path, raw, new, hdr)
    for arc_name, members in changed.items():
        vol.write(cfg2["game_dir"] + "/" + arc_name, arcs[arc_name].rebuilt(members))
    for w in warn:
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
