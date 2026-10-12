"""English for four nine's System-98 (pc98tl/sys98.py): strings.json in, a patched image out.

Strings (refs SCRIPT:address of the text; a script on its own on the disk, next to the archives, is
the one the program reads):

* "msg": a text op 15h shows in a window (op 03h sets a window: its width and height in 16-dot
  cells): any length.  The patcher breaks its lines between words at the window's edge and, past
  the window's lines, waits for a key and clears the window (as 01h does).  `\\n` in the English
  forces a new line.
* "menu": a text op 15h shows in a small window (under 40 cells: the command menus, a menu's title):
  each line an item, kept as it is (no breaks added, no pages); `max_cells` the window's width; a
  longer line or more lines than the Japanese reported.
* "label": a text op 16h shows at a place on the screen (a menu's items, a title): `max_cells` the
  Japanese's width; past it reported.
* "name": a string op 59h copies to one of the 80-byte strings the texts insert (a speaker's name):
  past 79 bytes cut and reported.
* "console": a line SYS98.EXE prints to the screen through the BIOS when it has to stop (memory, a
  file it cannot read): in place, `max_cells` its room in bytes (a letter one, a full-width
  character two); past it cut and reported.

`{C1}`-style tokens are the controls inside a text (colours, names inserted, numbers, key waits, new
pages) and must be kept.  English is ASCII, drawn half-width (the program patched, sys98.patch_program);
another character is written full-width in Shift-JIS when it has one, else `?`.  A script with its
English may take 16 KB (the program reads that much); a longer build is refused and names the script
and its strings.  The archives with a changed script are written anew (the changed members and the catalog
compressed as the originals are); a script on its own is written over.
"""
import json
import os
import re
import struct

from . import lzexe, sys98
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "menu": "i", "label": "l", "name": "n", "console": "c"}
MENU_WIDTH = 40   # a window narrower than this (in cells) holds a menu or a title, a line an item
NAME_ROOM = 79
TOKEN = re.compile(r"\{C(\d+)\}|\{X([0-9A-F]{2,4})\}")
SUBST = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"}
# a line printed through int DCh: mov dx, the line / mov ah, 1 / mov cl, 10h / int DCh, ds set before it
# (push the segment / pop ds)
CONSOLE_SIG = re.compile(rb"\xba(..)\xb4\x01\xb1\x10\xcd\xdc", re.S)
SEG_SIG = re.compile(rb"\x68(..)\x1f", re.S)


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


class Game:
    """The archives, the scripts (a script on its own overriding its archive's), the program."""

    def __init__(self, vol, cfg):
        self.vol, self.cfg = vol, cfg
        gd = cfg["game_dir"]
        self.files = {p.rsplit("/", 1)[-1].upper(): p for p, e in vol.walk()
                      if not e["is_dir"] and p.upper().startswith(gd.upper() + "/")}
        self.cats = []
        for name in sorted(self.files):
            if name.endswith(".CAT") and name[:-4] + ".LIB" in self.files:
                self.cats.append((name, sys98.Catalog(vol.read(self.files[name]),
                                                      vol.read(self.files[name[:-4] + ".LIB"]))))
        self.where = {}
        for cname, cat in self.cats:
            for m in cat.names():
                if m.lower().endswith(".s") and m.upper() not in self.where:
                    self.where[m.upper()] = (cname, m)
        self.scripts = {}
        for key, (cname, m) in sorted(self.where.items()):
            raw = vol.read(self.files[key]) if key in self.files else dict(self.cats)[cname].read(m)
            self.scripts[m] = sys98.decode(raw)
        self.sub = cfg["sub_script"]

    def org(self, name):
        return 0x4000 if name.lower() == self.sub.lower() else 0

    def walks(self):
        ext, out = set(), {}
        for n, d in self.scripts.items():
            if self.org(n) == 0:
                out[n] = sys98.walk(d)
                ext |= {t for _a, k, t in out[n][1] if k == "extern"}
        for n, d in self.scripts.items():
            if self.org(n):
                out[n] = sys98.walk(d, self.org(n), sorted(ext))
        return out


def _char(raw):
    try:
        return raw.decode("cp932")
    except UnicodeDecodeError:
        return "{X%s}" % raw.hex().upper()


def split(d, i):
    """(prefix bytes, visible text, suffix bytes, [inner control bytes]) of the text at i: the
    controls before its first character and after its last outside, the others tokens."""
    at = sys98.atoms(d, i)
    a, b = 0, len(at)
    while a < b and at[a][0] not in "ta":
        a += 1
    while b > a and at[b - 1][0] not in "ta":
        b -= 1
    inner, vis = [], ""
    for kind, r in at[a:b]:
        if kind == "n":
            vis += "\n"
        elif kind in "ta":
            vis += _char(r)
        else:
            inner.append(r)
            vis += "{C%d}" % len(inner)
    return b"".join(r for _k, r in at[:a]), vis, b"".join(r for _k, r in at[b:]), inner


def cells(text):
    t = TOKEN.sub(lambda m: "" if m.group(1) else "..", text)
    return max((sum(1 if ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F else 2 for c in line)
                for line in t.split("\n")), default=0)


def _sjis(ch):
    try:
        e = ch.encode("cp932")
    except UnicodeEncodeError:
        return None
    return e


def encode(text, inner, page=None):
    """English as text bytes: ASCII as it is (drawn half-width), another character in Shift-JIS, a
    new line 0Dh (page: the places, as counts of new lines, where a new page goes instead: 01h)."""
    out = bytearray()
    pos, pieces = 0, []
    for m in TOKEN.finditer(text):
        pieces.append(("s", text[pos:m.start()]))
        pieces.append(("k", m))
        pos = m.end()
    pieces.append(("s", text[pos:]))
    nl = 0
    for kind, v in pieces:
        if kind == "k":
            if v.group(1):
                k = int(v.group(1)) - 1
                if 0 <= k < len(inner):
                    out += inner[k]
            else:
                out += bytes.fromhex(v.group(2))
            continue
        for ch in "".join(SUBST.get(c, c) for c in v):
            if ch == "\n":
                nl += 1
                out.append(0x01 if page and nl in page else 0x0D)
            elif " " <= ch <= "~":
                out.append(ord(ch))
            else:
                e = _sjis(ch)
                out += e if e and len(e) == 2 else b"?"
    return bytes(out)


def windows(game, walks):
    """{window: (cells, lines)}: each window's text room, the size op 03h sets it to most often."""
    seen = {}
    for n, d in game.scripts.items():
        org = game.org(n)
        for a, (op, e) in walks[n][0].items():
            if op == 0x03:
                win, _x, _y, w, h = struct.unpack_from("<5H", d, a - org + 2)
                seen.setdefault(win, {}).setdefault((max(1, (w - 2) * 2), max(1, h - 2)), 0)
                seen[win][(max(1, (w - 2) * 2), max(1, h - 2))] += 1
    return {k: max(v, key=v.get) for k, v in seen.items()}


def texts(game, walks, wins):
    """[(script, kind, target, op address, window)]: the texts and strings the scripts show."""
    out = []
    for n, d in game.scripts.items():
        org = game.org(n)
        ops, refs = walks[n]
        starts = sorted(ops)
        for a, kind, t in refs:
            if kind not in ("text", "string"):
                continue
            o = max(s for s in starts if s <= a)
            op = ops[o][0]
            if kind == "string":
                out.append((n, "name", t, o, None))
            elif op == 0x15:
                win = d[o - org + 2] & 0x0F
                out.append((n, "msg" if wins.get(win, (66, 4))[0] >= MENU_WIDTH else "menu", t, o, win))
            else:
                out.append((n, "label", t, o, None))
    return out


def console_lines(prog_image):
    """[(start, end)]: the program's lines it prints through int DCh (a "$" ends each), image offsets."""
    out = set()
    for m in CONSOLE_SIG.finditer(prog_image):
        segs = list(SEG_SIG.finditer(prog_image, max(0, m.start() - 32), m.start()))
        if not segs:
            continue
        seg = struct.unpack("<H", segs[-1].group(1))[0]
        s = seg * 16 + struct.unpack("<H", m.group(1))[0]
        e = prog_image.find(b"$", s)
        if 0 < e and re.search(rb"[\x81-\x9f\xe0-\xfc]", prog_image[s:e]):
            out.add((s, e))
    return sorted(out)


def console_split(raw):
    a, b = 0, len(raw)
    while a < b and raw[a] in b"\x07\x0a\x0d":
        a += 1
    while b > a and raw[b - 1] in b"\x07\x0a\x0d":
        b -= 1
    return raw[:a], raw[a:b].decode("cp932"), raw[b:]


def _visible(vis):
    t = TOKEN.sub("", vis).strip("　 \n")
    return bool(t) and not all(0xFF61 <= ord(c) <= 0xFF9F or c in "　 " for c in t) and \
        not all(ch in "{}" for ch in t)


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    game = Game(vol, cfg)
    walks = game.walks()
    wins = windows(game, walks)
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
    prog = lzexe.unpack(vol.read(game.files[cfg["program"].upper()]))["image"]
    for s, e in console_lines(prog):
        _p, vis, _s = console_split(prog[s:e])
        add("console", vis, "%s:%05x" % (cfg["program"], s), len(prog[s:e]) - len(_p) - len(_s),
            "a line the program prints when it has to stop (memory, a file): its room in bytes (a letter "
            "one, a full-width character two); past it cut and reported")
    done = set()
    for n, kind, t, o, win in texts(game, walks, wins):
        if (n, t) in done:
            continue
        done.add((n, t))
        d = game.scripts[n]
        _p, vis, _s, _i = split(d, t - game.org(n))
        if not _visible(vis):
            continue
        ref = "%s:%04x" % (n, t)
        if kind == "msg":
            add("msg", vis, ref, wins.get(win, (66, 4))[0])
        elif kind == "menu":
            add("menu", vis, ref, wins.get(win, (66, 4))[0], "a menu's items or a title in a small window: "
                "each line one item, at most `max_cells` (the window's width); no more lines than the "
                "Japanese")
        elif kind == "label":
            add("label", vis, ref, cells(vis), "a text at a place on the screen (a menu's item, a title): "
                "`max_cells` the Japanese's width")
        else:
            add("name", vis, ref, cells(vis), "a string the texts insert (a speaker's name): `max_cells` the "
                "Japanese's; the program keeps %d bytes" % NAME_ROOM)
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


def wrap(text, width, lines):
    """(the English with new lines between words, {new line counts where a page starts}): the line
    breaks at width cells, a new page after `lines` lines."""
    out, page = [], set()
    col, line, nl = 0, 0, 0
    for k, para in enumerate(text.split("\n")):
        if k:
            out.append("\n")
            nl += 1
            line += 1
            col = 0
            if line >= lines:
                page.add(nl)
                line = 0
        for j, word in enumerate(para.split(" ")):
            w = cells(word)
            if j:
                if col + 1 + w > width and col:
                    out.append("\n")
                    nl += 1
                    line += 1
                    col = 0
                    if line >= lines:
                        page.add(nl)
                        line = 0
                else:
                    out.append(" ")
                    col += 1
            out.append(word)
            col += w
            while col > width:
                col -= width
                line += 1
    return "".join(out), page


def _pseudo(e):
    if e["kind"] == "menu":
        return "\n".join(pseudo(e["id"] + str(k), 2 * e["max_cells"], 1.0)[:max(1, min(e["max_cells"], 2 * cells(
            line)))] for k, line in enumerate(e["jp"].split("\n")))
    if e["kind"] in ("label", "name", "console"):
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:max(1, e["max_cells"])]
    return pseudo(e["id"], cells(e["jp"]) * max(1, e["jp"].count("\n") + 1))


def build_script(game, n, walks, wins, by_ref, ids, rooms, warn, ratio=1.0):
    d = game.scripts[n]
    org = game.org(n)
    ops, refs = walks[n]
    new = {}
    for nm, kind, t, o, win in texts(game, walks, wins):
        if nm != n or t in new:
            continue
        ref = "%s:%04x" % (n, t)
        en = by_ref.get(ref)
        if en is None:
            continue
        if ratio < 1.0:
            en = en[:max(4, int(len(en) * ratio))]
        prefix, vis, suffix, inner = split(d, t - org)
        page = None
        if kind == "msg":
            width, lines = wins.get(win, (76, 3))
            en, page = wrap(en, width, lines)
        b = prefix + encode(en, inner, page) + suffix
        if kind == "name" and len(b) > NAME_ROOM:
            warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), NAME_ROOM))
            while len(b) > NAME_ROOM:
                en = en[:-1]
                b = prefix + encode(en, inner) + suffix
        elif kind == "menu" and (cells(en) > rooms[ref] or en.count("\n") > vis.count("\n")):
            warn.append("%s: %d cells, %d lines, past its window (%d cells, %d lines)" % (
                ids[ref], cells(en), en.count("\n") + 1, rooms[ref], vis.count("\n") + 1))
        elif kind == "label" and cells(en) > rooms[ref]:
            warn.append("%s: %d cells, past its room (%d)" % (ids[ref], cells(en), rooms[ref]))
        new[t] = b
    if not new:
        return None
    return sys98.rebuild(d, org, refs, new, keep_layout=bool(org))


def patch_console(prog, by_ref, ids, cfg, warn):
    prog = bytearray(prog)
    for s, e in console_lines(bytes(prog)):
        ref = "%s:%05x" % (cfg["program"], s)
        en = by_ref.get(ref)
        if en is None:
            continue
        pre, _v, suf = console_split(bytes(prog[s:e]))
        room = e - s - len(pre) - len(suf)
        b = "".join(SUBST.get(c, c) for c in en).encode("cp932", "replace").replace(b"$", b"S")
        if len(b) > room:
            warn.append("%s: %d bytes, cut to %d" % (ids[ref], len(b), room))
            b = b[:room]
        prog[s:e] = (pre + b + suf).ljust(e - s, b" ")
    return bytes(prog)


def write_archives(game, changed):
    """The archives with the changed scripts (changed {member: decoded bytes}), each written anew: its
    members in their order, a changed one compressed (sys98.pack); the catalog compressed too."""
    for cname, cat in game.cats:
        mine = {m: d for m, d in changed.items() if game.where.get(m.upper(), (None,))[0] == cname and
                m.upper() not in game.files}
        if not mine:
            continue
        lib = bytearray(cat.lib[:sys98.LIB_HEAD])
        entries = []
        for name, flag, size, off, raw12 in cat.entries:
            if name in mine:
                data, flag = sys98.pack(sys98.encode(mine[name])), 1
            else:
                data = cat.lib[sys98.LIB_HEAD + off:sys98.LIB_HEAD + off + size]
            off, size = len(lib) - sys98.LIB_HEAD, len(data)
            lib += data
            entries.append(raw12 + struct.pack("<HII", flag, size, off))
        catb = b"Cat1" + struct.pack("<H", len(entries)) + sys98.pack(b"".join(entries))[4:]
        game.vol.write(game.files[cname], catb)
        game.vol.write(game.files[cname[:-4] + ".LIB"], bytes(lib))
    for m, d in changed.items():
        if m.upper() in game.files:
            game.vol.write(game.files[m.upper()], sys98.encode(d))


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    game = Game(vol, cfg)
    walks = game.walks()
    wins = windows(game, walks)
    by_ref, ids, rooms = {}, {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            rooms[r] = e["max_cells"]
            if text:
                by_ref[r] = text
    warn, changed = [], {}
    for n in sorted(game.scripts):
        try:
            new = build_script(game, n, walks, wins, by_ref, ids, rooms, warn)
        except OverflowError as ex:
            if mode != "pseudo":
                raise SystemExit("%s: %d bytes with its English, the program reads %d; shorten these "
                                 "strings: %s" % (n, ex.args[0], sys98.SCRIPT_ROOM, ", ".join(sorted(
                                     {ids[r] for r in by_ref if r.startswith(n + ":")}))))
            ratio, new = 1.0, None
            while new is None:
                ratio *= 0.9
                try:
                    new = build_script(game, n, walks, wins, by_ref, ids, rooms, [], ratio)
                except OverflowError:
                    continue
            warn.append("%s: the filler was cut to %d%% to fit the script's 16 KB" % (n, int(ratio * 100)))
        if new is not None and new != game.scripts[n]:
            changed[n] = new
    prog_path = game.files[cfg["program"].upper()]
    p = lzexe.unpack(vol.read(prog_path))
    prog = patch_console(p["image"], by_ref, ids, cfg, warn)
    if changed or prog != p["image"]:
        write_archives(game, changed)
        image, p["relocs"] = sys98.patch_program(prog, p["relocs"])
        vol.write(prog_path, lzexe.build(p, image))
    for w_ in dict.fromkeys(warn):
        print("warning:", w_)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), len(changed)))
