"""English for Sogna's SGS (pc98tl/sgs.py): strings.json in, a patched image out.

Strings (refs SCRIPT:offset of the text):

* "msg": a message (op 02): any length.  The patcher breaks its lines between words at the window's
  edge (op 03 sets the window: its width; op 4E the indent of the lines after the first), going on
  from where the message before left the line; the window scrolls by itself.  `\\n` in the English
  forces a new line.
* "item": a menu's item (op 00): one line in the menu's box, `max_cells` the menu's widest Japanese
  item (past it reported).
* "name": a string op 26 sets, the messages insert (a speaker's name before a message, whose lines
  after the first start after it, op 4E): `max_cells` the Japanese's; the program keeps 48 bytes
  (a letter one, a full-width character two, two more for the half-width letters' start and end):
  past them cut and reported.
* "system": a system message (op 1B: the disk prompts): `max_cells` the program's room (79 bytes);
  past it cut and reported.
* "console": a line SGS.COM prints through DOS before the game starts (its mode, memory, a missing
  file; refs SGS.COM:address): in place, `max_cells` its room in bytes (a letter one, a full-width
  character two); past it cut and reported.

`{C1}`-style tokens are the commands inside a string (key waits, colours, inserted names, pictures)
and must be kept.  English is ASCII, drawn half-width; another character is written full-width in
JIS when it has one, else `?`.  A script with its English may take the program's read (16 KB) less
the helper's bytes at its end; a longer build is refused and names the script.  Every script is
written with the helper at the end of its room (sgs.helper_at).  The scripts are the game
directory's *.SIL, or game.json's "scripts" where the disk keeps one the program does not run (V6
RS: VC2.SIL, V6's, which no script of its loads).
"""
import fnmatch
import json
import os
import re
import struct

from . import sgs
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "item": "i", "name": "n", "system": "s", "console": "c"}
ROOM = {"name": 48, "system": 79}
TOKEN = re.compile(r"\{C(\d+)\}|\{X([0-9A-F]{4})\}")
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}
NEWLINE = b"\x21\x6f"


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def _path(cfg, name):
    return cfg["game_dir"] + "/" + name


def _char(r):
    try:
        return bytes([r[0] | 0x80, r[1] | 0x80]).decode("euc_jp")
    except UnicodeDecodeError:
        return "{X%s}" % r.hex().upper()


def atoms(raw, cmds, var=False):
    """[(kind, text, bytes)]: "c" a command, "n" a new line, "t" a character, "a" a half-width
    letter (the patch's, between 7Fh marks); cmds the build's message commands (None: a menu's
    item, characters only)."""
    out, i, half = [], 0, False
    while i < len(raw):
        b = raw[i]
        if b == sgs.HALF:
            half = not half
            out.append(("c", "", raw[i:i + 1]))
            i += 1
            continue
        if half:
            out.append(("a", chr(b), raw[i:i + 1]))
            i += 1
            continue
        if var and b == 0xFF:
            out.append(("c", "", raw[i:i + 5]))
            i += 5
            continue
        if b & 0x80 and cmds is not None:
            out.append(("c", "", raw[i:i + 7]))
            i += 7
            continue
        w = b << 8 | raw[i + 1]
        r = raw[i:i + 2]
        i += 2
        if cmds and w == 0x2143:
            # the two bytes after it drawn as a character
            out.append(("t", _char(raw[i:i + 2]), r + raw[i:i + 2]))
            i += 2
        elif cmds and w == 0x216F:
            out.append(("n", "\n", r))
        elif cmds and w in cmds:
            out.append(("c", "", r + raw[i:i + cmds[w]]))
            i += cmds[w]
        else:
            out.append(("t", _char(r), r))
    return out


def split(raw, cmds, var=False):
    """(prefix bytes, visible text, suffix bytes, [inner command bytes])."""
    at = atoms(raw, cmds, var)
    a, b = 0, len(at)
    while a < b and at[a][0] in "cn":
        a += 1
    while b > a and at[b - 1][0] in "cn":
        b -= 1
    inner, vis = [], ""
    for kind, ch, r in at[a:b]:
        if kind == "c":
            inner.append(r)
            vis += "{C%d}" % len(inner)
        else:
            vis += ch
    return b"".join(r for _k, _c, r in at[:a]), vis, b"".join(r for _k, _c, r in at[b:]), inner


def cells(text):
    t = TOKEN.sub(lambda m: ".." if m.group(2) else "", text)
    return sum(1 if ord(c) < 0x80 else 2 for c in t)


def _jis(ch):
    try:
        e = ch.encode("euc_jp")
    except UnicodeEncodeError:
        return None
    return bytes([e[0] & 0x7F, e[1] & 0x7F]) if len(e) == 2 and e[0] >= 0xA1 else None


def encode(text, inner):
    """English as text bytes: ASCII between 7Fh marks, another character a JIS pair, a new line
    216F, the tokens their commands."""
    out, half = bytearray(), False

    def close():
        nonlocal half
        if half:
            out.append(sgs.HALF)
            half = False
    pos = 0
    pieces = []
    for m in TOKEN.finditer(text):
        pieces.append(("s", text[pos:m.start()]))
        pieces.append(("k", m))
        pos = m.end()
    pieces.append(("s", text[pos:]))
    for kind, v in pieces:
        if kind == "k":
            close()
            if v.group(1):
                k = int(v.group(1)) - 1
                if 0 <= k < len(inner):
                    out += inner[k]
            else:
                out += bytes.fromhex(v.group(2))
            continue
        for ch in "".join(SUBST.get(c, c) for c in v):
            if ch == "\n":
                close()
                out += NEWLINE
            elif " " <= ch <= "~":
                if not half:
                    out.append(sgs.HALF)
                    half = True
                out.append(ord(ch))
            else:
                j = _jis(ch)
                close()
                out += j if j else b"\x21\x29"
    close()
    return bytes(out)


def scripts(vol, cfg):
    """The game's scripts: game.json "scripts" (names, `*` and `?` as wildcards; *.SIL when it has
    none) in its directory."""
    pats = cfg.get("scripts", ["*.SIL"])
    for path, e in vol.walk():
        if not e["is_dir"] and path.upper().startswith(cfg["game_dir"].upper() + "/") and \
                any(fnmatch.fnmatchcase(path.rsplit("/", 1)[-1].upper(), p.upper()) for p in pats):
            yield path, vol.read(path)


def console_split(raw):
    """A console line: (prefix bytes, its text, suffix bytes), the controls (CR, LF, bell) the
    prefix and suffix."""
    a, b = 0, len(raw)
    while a < b and raw[a] in b"\x07\x0a\x0d":
        a += 1
    while b > a and raw[b - 1] in b"\x07\x0a\x0d":
        b -= 1
    return raw[:a], raw[a:b].decode("cp932"), raw[b:]


def console_encode(text):
    out = bytearray()
    for ch in "".join(SUBST.get(c, c) for c in text):
        if " " <= ch <= "~" and ch != "$":
            out.append(ord(ch))
        else:
            try:
                out += ch.encode("cp932")
            except UnicodeEncodeError:
                out += b"?"
    return bytes(out)


def patch_console(prog, by_ref, ids, cfg, warn):
    """The program with its console lines' English in place (the room: the Japanese's bytes)."""
    prog = bytearray(prog)
    for s, e in sgs.console(prog):
        ref = "%s:%04x" % (cfg["program"], s + 0x100)
        en = by_ref.get(ref)
        if en is None:
            continue
        pre, _vis, suf = console_split(bytes(prog[s:e]))
        room = e - s - len(pre) - len(suf)
        b = console_encode(en)
        if len(b) > room:
            warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), room))
            while len(b) > room:
                en = en[:-1]
                b = console_encode(en)
        prog[s:e + 1] = (pre + b + suf + b"$").ljust(e + 1 - s, b"$")
    return bytes(prog)


def script_texts(build, d):
    ops = sgs.walk(d, build)
    return ops, sgs.texts(d, ops)


def _cmds(build, kind):
    return None if kind == "item" else build.cmds


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    build = sgs.Build(vol.read(_path(cfg, cfg["program"])))
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
    prog = vol.read(_path(cfg, cfg["program"]))
    for s, e in sgs.console(prog):
        _p, vis, _s = console_split(prog[s:e])
        if vis.strip("　 "):
            add("console", vis, "%s:%04x" % (cfg["program"], s + 0x100), len(prog[s:e]) - len(_p) - len(_s),
                "a line the program prints before the game starts: `max_cells` its room in bytes (a letter "
                "one, a full-width character two); past it cut and reported")
    for path, d in scripts(vol, cfg):
        name = path.rsplit("/", 1)[-1]
        ops, tx = script_texts(build, d)
        menus = {}
        for a, kind, s, e in tx:
            if kind == "item":
                menus[a] = max(menus.get(a, 0), cells(split(d[s:e], None)[1]))
        for a, kind, s, e in tx:
            _p, vis, _s, _i = split(d[s:e], _cmds(build, kind), kind == "var")
            if not vis.strip("　 \n"):
                continue
            ref = "%s:%04x" % (name, s)
            if kind == "msg":
                add("msg", vis, ref, cfg["window_cells"])
            elif kind == "item":
                add("item", vis, ref, menus[a], "a menu's item: one line in its box (the menu's widest "
                    "Japanese item)")
            elif kind == "var":
                add("name", vis, ref, cells(vis), "a string the messages insert (a speaker's name before "
                    "the message, whose next lines start after it): `max_cells` the Japanese's; the program "
                    "keeps %d bytes" % ROOM["name"])
            else:
                add("system", vis, ref, ROOM["system"], "a system message (a disk prompt): %d bytes" %
                    ROOM["system"])
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


class Window:
    """The message window's width and indent and where the line is, op after op."""

    def __init__(self, cells_, cmds, names):
        self.width, self.indent, self.col, self.cmds = cells_, 0, 0, cmds
        # op 26's strings by slot (the bytes the build writes), which 2173 inserts (its second byte
        # less 41h the slot): they hold commands too (a clear, the colour)
        self.names = names

    def op(self, d, a, op):
        if op == 0x03:
            self.width, self.col = 2 * d[a + 3], 0
        elif op == 0x4E:
            self.indent = d[a + 1]

    def jp(self, raw, var=False):
        at = atoms(raw, self.cmds, var)
        for k, (kind, ch, r) in enumerate(at):
            if kind == "n":
                # (the line after starts at the window's left before a name or the end, else indented)
                nxt = at[k + 1][2][:2] if k + 1 < len(at) else b""
                self.col = 0 if nxt in (b"", b"\x21\x73") else self.indent
            elif kind == "c" and r[:2] == b"\x21\x30":
                self.col = 0
            elif kind == "c" and r[:2] == b"\x21\x73" and not var:
                self.jp(self.names.get(r[3] - 0x41, b""), True)
            elif kind in "ta":
                self.col += 2 if kind == "t" else 1
                if self.col >= self.width:
                    self.col = self.indent

    def _cells(self, word, inner):
        """A word's cells, an inserted name's among them."""
        n = cells(word)
        for m in TOKEN.finditer(word):
            k = int(m.group(1)) - 1 if m.group(1) else -1
            if 0 <= k < len(inner) and inner[k][:2] == b"\x21\x73":
                v = self.names.get(inner[k][3] - 0x41, b"")
                n += sum(2 if k == "t" else 1 for k, _c, _r in atoms(v, self.cmds, True) if k in "ta")
        return n

    def wrap(self, prefix, text, inner=()):
        """The English with new lines between words, the line going on from where it is."""
        self.jp(prefix)
        out = []
        for k, para in enumerate(text.split("\n")):
            if k:
                out.append("\n")
                self.col = self.indent
            broke = False
            for j, word in enumerate(para.split(" ")):
                w = self._cells(word, inner)
                if j and not broke:
                    # (after a word that filled the line the program has broken it: no space)
                    if self.col + 1 + w > self.width and self.col > self.indent:
                        out.append("\n")
                        self.col = self.indent
                    else:
                        out.append(" ")
                        self.col += 1
                out.append(word)
                self.col += w
                broke = self.col >= self.width
                while self.col >= self.width:
                    self.col -= self.width - self.indent
        return "".join(out)


def routine(build, d, ops, index, target):
    """What a called routine does to the window, its ops from the call's target to its return in a
    line: (the width it sets or None, the indent or None, whether it clears: op 03 or a message with
    2130, the messages after the call starting at the window's top)."""
    width = indent = None
    clears = False
    for a, op, e, rule in ops[index.get(target, len(ops)):]:
        if rule == "ret":
            break
        if op == 0x03:
            width, clears = 2 * d[a + 3], True
        elif op == 0x4E:
            indent = d[a + 1]
        elif rule in ("msg", "bgmsg") and any(r[:2] == b"\x21\x30" for _k, _c, r in
                                              atoms(d[a + 1:e - 1], build.cmds)):
            clears = True
    return width, indent, clears


def entry_windows(build, every, cfg):
    """{script name: (width, indent)}: the window a script starts with, the one of the script that
    loads it (an op whose string names a script, "A:NAME"; the first such load met, from STARTUP.SIL
    on), since the program keeps it from script to script; the others game.json's window_cells."""
    by = {path.rsplit("/", 1)[-1].upper(): d for path, d in every}
    start = (cfg["window_cells"], 0)
    entry, queue = {"STARTUP.SIL": start}, ["STARTUP.SIL"]
    while queue:
        name = queue.pop(0)
        if name not in by:
            continue
        d = by[name]
        width, indent = entry[name]
        ops = sgs.walk(d, build)
        index = {a: k for k, (a, _o, _e, _r) in enumerate(ops)}
        for a, op, e, rule in ops:
            if op == 0x03:
                width = 2 * d[a + 3]
            elif op == 0x4E:
                indent = d[a + 1]
            elif not isinstance(rule, int) and rule[0] == "call":
                w, i, _c = routine(build, d, ops, index, struct.unpack_from("<H", d, a + rule[2])[0])
                width = width if w is None else w
                indent = indent if i is None else i
            elif not isinstance(rule, int) and rule[0] == "str":
                s = d[a + 1:e - 1]
                t = (s.split(b":")[-1].decode("ascii", "replace") + ".SIL").upper()
                if t in by and t not in entry:
                    entry[t] = (width, indent)
                    queue.append(t)
    return {n: entry.get(n, start) for n in by}


def _pseudo(e):
    if e["kind"] == "console":
        return pseudo(e["id"], cells(e["jp"]))[:e["max_cells"]]
    if e["kind"] in ("item", "name", "system"):
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:max(1, e["max_cells"] - 2)]
    return pseudo(e["id"], cells(e["jp"]))


def build_script(build, d, name, by_ref, ids, rooms, cfg, warn, limit, names, entry, ratio=1.0):
    """The script with its English (None: no English in it); names: op 26's strings by slot as
    the build writes them, the line's place after them (filled in as they are seen, the widest
    kept); entry: the window it starts with (entry_windows)."""
    ops, tx = script_texts(build, d)
    # (the script's own op 26 sets a slot for what follows; the others the widest seen anywhere)
    win = Window(entry[0], build.cmds, dict(names))
    win.indent = entry[1]

    def keep(slot, b):
        win.names[slot] = b
        if slot not in names or len(b) > len(names[slot]):
            names[slot] = b
    index = {a: k for k, (a, _o, _e, _r) in enumerate(ops)}
    at = {s: (a, kind, s, e) for a, kind, s, e in tx}
    new = {}
    for a, op, e, rule in ops:
        win.op(d, a, op)
        if not isinstance(rule, int) and rule[0] == "call":
            width, indent, clears = routine(build, d, ops, index, struct.unpack_from("<H", d, a + rule[2])[0])
            if width is not None:
                win.width = width
            if indent is not None:
                win.indent = indent
            if clears:
                win.col = 0
        for s in [s for s in sorted(at) if a < s < e]:
            _a, kind, s, t = at[s]
            raw = d[s:t]
            prefix, vis, suffix, inner = split(raw, _cmds(build, kind), kind == "var")
            ref = "%s:%04x" % (name, s)
            en = by_ref.get(ref) if vis.strip("　 \n") else None
            if en is not None and ratio < 1.0:
                en = en[:max(4, int(len(en) * ratio))]
            if kind == "msg":
                if en is None:
                    win.jp(raw)
                    continue
                en = win.wrap(prefix, en, inner)
                win.jp(suffix)
            if en is None:
                if kind == "var":
                    keep(d[a + 1], raw)
                continue
            b = prefix + encode(en, inner) + suffix
            room = ROOM.get("name" if kind == "var" else kind)
            if room and len(b) > room:
                warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), room))
                while len(b) > room:
                    en = en[:-1]
                    b = prefix + encode(en, inner) + suffix
            elif kind == "item" and cells(en) > rooms[ref]:
                warn.append("%s: %d cells, past its menu's room (%d)" % (ids[ref], cells(en), rooms[ref]))
            if kind == "var":
                keep(d[a + 1], b)
            new[(s, t)] = b
    if not new:
        return None
    return sgs.rebuild(d, ops, new, limit)


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    prog_path = _path(cfg, cfg["program"])
    prog = vol.read(prog_path)
    build = sgs.Build(prog)
    new_prog, helper = sgs.patch_program(prog)
    limit = build.room - len(helper)
    by_ref, ids, rooms = {}, {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            rooms[r] = e["max_cells"]
            if text:
                by_ref[r] = text
    # (the names first: a script may insert a name another sets)
    names, every = {}, list(scripts(vol, cfg))
    entry = entry_windows(build, every, cfg)
    for path, d in every:
        name = path.rsplit("/", 1)[-1]
        build_script(build, d, name, by_ref, ids, rooms, cfg, [], 0x10000, names, entry[name.upper()])
    warn, done, out = [], 0, []
    for path, d in every:
        name = path.rsplit("/", 1)[-1]
        try:
            new = build_script(build, d, name, by_ref, ids, rooms, cfg, warn, limit, names,
                               entry[name.upper()])
        except OverflowError as ex:
            if mode != "pseudo":
                raise SystemExit("%s: %d bytes with its English, the program reads %d (less the helper's "
                                 "%d); shorten these strings: %s" % (
                                     name, ex.args[0], build.room, len(helper), ", ".join(sorted(
                                         {ids[r] for r in by_ref if r.startswith(name + ":")}))))
            ratio, new = 1.0, None
            while new is None:
                ratio *= 0.9
                try:
                    new = build_script(build, d, name, by_ref, ids, rooms, cfg, [], limit, names,
                                       entry[name.upper()], ratio)
                except OverflowError:
                    continue
            warn.append("%s: the filler was cut to %d%% to fit the script's room" % (name, int(ratio * 100)))
        if new is not None and new != d:
            done += 1
        out.append((path, name, d if new is None else new))
    new_prog = patch_console(new_prog, by_ref, ids, cfg, warn)
    if done or patch_console(prog, by_ref, ids, cfg, []) != prog:
        for path, name, d in out:
            try:
                vol.write(path, sgs.helper_at(build, d, helper))
            except ValueError:
                raise SystemExit("%s: %d bytes, past the room the helper leaves (%d)" % (name, len(d), limit))
        vol.write(prog_path, new_prog)
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
