"""English for Elf's early AI engine (pc98tl/elfai.py, De-Ja): strings.json in, a patched image out.

Strings (refs SCRIPT:offset, the run's first byte):

* "msg": a run of text the window draws (its dictionary codes expanded, ％ as a line break, `{N<n>}`
  for a name AC draws: n the variable's letter less 40h).  The English is kept in SCRIPT.ENG; the
  script gets, for each line, statement BBh with the line's offset there.  Lines are wrapped between
  words to the window's width (less one letter: the engine would break a full line itself), starting
  where the text before leaves the cursor, and a new page (A6 AA: a key, then the window cleared)
  begun when the window is full.  `\\n` starts a new line.
* "item": a menu's item, written as a string ("..."): one line, `max_cells` the menu's box.
* "tag": the text in a dictionary entry that does more than draw it (a speaker's name after a new
  page and a colour, a sound): a string, one line.
* "name": a text B1 sets: a hero's default name (`max_cells` 12, KPUT.COM's six characters) or the
  name entry's prompt: written full-width (the engine draws a name as script text); past `max_cells`
  it is cut and reported.

English is ASCII, drawn half-width; another character becomes `?` (and `"` in a string `'`).  A
script with its English may take elfai.room() bytes (24 KB, less where it names a lower buffer), its
English 65535; a build past either is refused and names it.
"""
import json
import os
import re

from . import elfai
from .alice_sys2_tl import sha256
from .text import pseudo

PREFIX = {"msg": "m", "item": "i", "tag": "t", "name": "n"}
SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "♥": "<3", "　": " "}
TOKEN = re.compile(r"(\{N\d+\})")
TAG_CELLS = 20
DEFAULT_WINDOW = (0, 151, 79, 199)
NOTES = {24: "the hero's family name (KPUT.COM's entry)", 25: "the hero's given name (KPUT.COM's entry)"}


def _image(src):
    from .disk import DiskImage
    return DiskImage(src)


def scripts(vol, cfg):
    d = vol.find(cfg["game_dir"])["cluster"]
    return sorted(e["name"] for e in vol.listdir(d) if e["name"].upper().endswith(".MES"))


def ascii_(text, quoted=False):
    out = bytearray()
    for c in "".join(SUBST.get(c, c) for c in text):
        if quoted and c == '"':
            c = "'"
        out.append(ord(c) if 0x20 <= ord(c) < 0x7F else 0x3F)
    return bytes(out)


def fullwidth(text):
    out = bytearray()
    for c in "".join(SUBST.get(c, c) for c in text):
        if c == " ":
            out += "　".encode("cp932")
            continue
        o = ord(c)
        ch = chr(o + 0xFEE0) if 0x21 <= o <= 0x7E else c
        try:
            b = ch.encode("cp932")
        except UnicodeEncodeError:
            b = "？".encode("cp932")
        out += b if len(b) == 2 and 0x81 <= b[0] <= 0x98 else "？".encode("cp932")
    return bytes(out)


def _cells(text):
    return elfai.text_cells(text)


class Sim:
    """The window and the cursor, followed through a script in file order (a branch's text as if it
    ran)."""

    def __init__(self):
        self.win, self.lh = DEFAULT_WINDOW, 16
        self.col = self.line = 0

    @property
    def width(self):
        return self.win[2] - self.win[0] + 1

    @property
    def lines(self):
        return max(1, (self.win[3] + 1 - self.win[1]) // max(1, self.lh))

    def newline(self):
        self.col = 0
        self.line = (self.line + 1) % self.lines

    def advance(self, n):
        self.col += n
        while self.col >= self.width:
            self.col -= self.width
            self.newline()

    def clear(self):
        self.col = self.line = 0


def _args(S, k, n):
    """The values of the n numbers after the op at token k, joined by ","; None when not numbers."""
    d, t = S.d, S.t
    out, j = [], k + 1
    for i in range(n):
        if j >= len(t) or t[j][0] != "num":
            return None
        out.append(elfai.numval(d, t[j]))
        j += 1
        if i < n - 1:
            if j >= len(t) or t[j][0] != "byte" or d[t[j][1]] != 0x2C:
                return None
            j += 1
    return out


def _sim_token(S, k, sim, tag_cells, depth=0):
    d, t = S.d, S.t
    kind, a, b = t[k]
    if kind == "sj":
        if d[a:b] == elfai.NEWLINE:
            sim.newline()
        else:
            sim.advance(2)
        return
    if kind != "byte":
        return
    c = d[a]
    if c == 0xAA:
        sim.clear()
    elif c == 0xA7:
        v = _args(S, k, 4)
        if v:
            sim.win = tuple(v)
            sim.clear()
    elif c == 0xA8:
        v = _args(S, k, 2)
        if v:
            sim.col = max(0, v[0] - sim.win[0])
            sim.line = max(0, (v[1] - sim.win[1]) // max(1, sim.lh)) % sim.lines
    elif c == 0x9B and k + 5 < len(t) and d[t[k + 1][1]] == 0x40:
        if t[k + 3][0] == "num" and elfai.numval(d, t[k + 3]) == 5 and t[k + 5][0] == "num":
            sim.lh = elfai.numval(d, t[k + 5]) or sim.lh
    elif c == 0xAC:
        sim.advance(elfai.NAME_CELLS)
    elif c in S.code_entry and depth < 8:
        s, e = S.code_entry[c]
        j = s
        while j < e:
            if j in tag_cells:
                cells, end = tag_cells[j]
                sim.advance(cells)
                j = end
                continue
            _sim_token(S, j, sim, tag_cells, depth + 1)
            j += 1


def _words(text):
    """[(word, cells)] of a paragraph; a token {N<n>} is a word of its own."""
    out = []
    for w in text.split(" "):
        if not w:
            continue
        for part in TOKEN.split(w):
            if part:
                out.append(part)
    return out


def _segments(line):
    """[(ascii or token)] for a line of English."""
    return [p for p in TOKEN.split(line) if p]


def _var(token):
    return bytes([0xAC, 0x40 + int(token[2:-1])])


def _msg(text, sim, eng, engmap, warn, ident):
    """A message's bytes (see the module's docstring)."""
    out = bytearray()
    first = True

    def brk():
        nonlocal out
        if sim.line + 1 < sim.lines:
            out += elfai.NEWLINE
            sim.newline()
        else:
            out += b"\xa6\xaa"
            sim.clear()
    for para in text.split("\n"):
        if not first:
            brk()
        first = False
        lead = len(para) - len(para.lstrip(" "))
        line, cells = " " * lead, lead
        lines = []
        cap = sim.width - 1 - sim.col
        for w in _words(para):
            wc = elfai.NAME_CELLS if TOKEN.fullmatch(w) else len(ascii_(w))
            sep = 1 if line.strip() else 0
            if cells + sep + wc <= cap:
                line += (" " if sep else "") + w
                cells += sep + wc
                continue
            if line.strip() or (not lines and sim.col):
                lines.append(line)      # (or, at a line's end, the first word on a line of its own)
            cap = sim.width - 1
            while wc > cap and not TOKEN.fullmatch(w):
                lines.append(w[:cap])
                w = w[cap:]
                wc = len(w)
            line, cells = w, wc
        lines.append(line)
        for i, ln in enumerate(lines):
            if i:
                brk()
            for seg in _segments(ln):
                if TOKEN.fullmatch(seg):
                    out += _var(seg)
                    sim.advance(elfai.NAME_CELLS)
                    continue
                raw = ascii_(seg)
                if raw not in engmap:
                    engmap[raw] = len(eng)
                    eng += raw + b"\x00"
                out += bytes([elfai.FAR]) + elfai.number(engmap[raw])
                sim.advance(len(raw))
    return bytes(out)


def _string(text, sim):
    out = bytearray()
    for seg in _segments(text):
        if TOKEN.fullmatch(seg):
            out += _var(seg)
            sim.advance(elfai.NAME_CELLS)
        else:
            raw = ascii_(seg, quoted=True)
            out += b'"' + raw + b'"'
            sim.advance(len(raw))
    return bytes(out)


def rebuild(d, values, warn, ids, name):
    """(the script with its English, its English segment) for values {run start offset: text}."""
    S = elfai.Script(d)
    t = S.t
    runs = {s: (e, kind) for s, e, kind in S.runs()}
    if not values:
        return d, b""
    # (a tag's width, for the cursor: its English's, else its own)
    tag_cells = {}
    for s, (e, kind) in runs.items():
        if kind == "tag":
            text = values.get(t[s][1])
            tag_cells[s] = ((len(ascii_(text)) if text is not None else _cells(S.render(s, e))), e)
    out, eng, engmap = bytearray(), bytearray(), {}
    sim = Sim()
    k = 0
    while k < len(t):
        if k in runs:
            e, kind = runs[k]
            a, b = t[k][1], t[e - 1][2]
            text = values.get(a)
            if text is None:
                for j in range(k, e):
                    _sim_token(S, j, sim, tag_cells)
                out += d[a:b]
                k = e
                continue
            ident = ids.get(a, hex(a))
            if kind == "msg" and k in S.in_entry:
                # (in a dictionary entry: from a cleared window, where the entry is run)
                local = Sim()
                local.win, local.lh = sim.win, sim.lh
                piece = _msg(text, local, eng, engmap, warn, ident)
            elif kind == "msg":
                piece = _msg(text, sim, eng, engmap, warn, ident)
            elif kind == "name":
                limit = elfai.NAME_CELLS if _ends_name(S, e) else max(elfai.NAME_CELLS, _cells(S.render(k, e)))
                piece = fullwidth(text)
                if len(piece) > limit:
                    warn.append("%s: %d cells, cut to %d" % (ident, len(piece), limit))
                    piece = piece[:limit - limit % 2]
            else:
                piece = _string(text, sim)
                if kind == "item" and len(piece) - 2 > elfai.ITEM_CELLS:
                    warn.append("%s: %d letters, past the menu's box (%d)" % (ident, len(piece) - 2, elfai.ITEM_CELLS))
            out += piece
            # (a number a statement would take as its argument's continuation: ended by an empty string)
            if piece and e < len(t) and t[e][0] in ("num", "byte") and elfai.is_expr_byte(d[t[e][1]]) and \
                    kind == "msg":
                out += b'""'
            k = e
            continue
        _sim_token(S, k, sim, tag_cells)
        out += d[t[k][1]:t[k][2]]
        k += 1
    if len(eng) > 0xFFFF:
        raise SystemExit("%s: its English takes %d bytes, 65535 at most" % (name, len(eng)))
    return bytes(out), bytes(eng)


def _ends_name(S, e):
    """The run's B1 text ends with "}" (a name AC draws), not 0 (KPUT.COM's prompt)."""
    d, t = S.d, S.t
    j = e
    while j < len(t) and t[j][0] == "byte" and d[t[j][1]] == 0x2C:
        j += 1
    return j < len(t) and t[j][0] == "num" and elfai.numval(d, t[j]) == 0x7D


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _image(src).volumes[0]
    merged, order = {}, []
    for name in scripts(vol, cfg):
        d = vol.read(cfg["game_dir"] + "/" + name)
        S = elfai.Script(d)
        for s, e, kind in S.runs():
            jp = S.render(s, e)
            if not jp.strip("　 \n"):
                continue
            if kind == "msg":
                cells = DEFAULT_WINDOW[2] - DEFAULT_WINDOW[0]
            elif kind == "item":
                cells = elfai.ITEM_CELLS
            elif kind == "tag":
                cells = TAG_CELLS
            else:
                cells = elfai.NAME_CELLS if _ends_name(S, e) else max(elfai.NAME_CELLS, _cells(jp))
            key = (kind, jp)
            ref = "%s:%04x" % (name, S.t[s][1])
            if key in merged:
                merged[key]["refs"].append(ref)
                merged[key]["max_cells"] = min(merged[key]["max_cells"], cells)
                continue
            ent = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells}
            used = sorted({int(x) for x in re.findall(r"\{N(\d+)\}", jp)})
            if used:
                ent["note"] = "; ".join("{N%d}: %s" % (x, NOTES.get(x, "a name the script keeps in variable %s"
                                                                   % chr(0x40 + x))) for x in used)
            if kind == "name":
                ent["note"] = ("the name entry's prompt (KPUT.COM)" if cells > elfai.NAME_CELLS else
                               "a name, six full-width letters at most (KPUT.COM's)") + "; written full-width"
            merged[key] = ent
            order.append(key)
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


def _pseudo(e):
    k = e["kind"]
    if k == "msg":
        parts = []
        for para in e["jp"].split("\n"):
            toks = TOKEN.findall(para)
            body = TOKEN.sub("", para)
            parts.append((" ".join(toks) + " " if toks else "") +
                         (pseudo(e["id"], _cells(body)) if body.strip("　 ") else ""))
        return "\n".join(p.rstrip() for p in parts)
    if k == "name":
        return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"] // 2]
    return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"]]


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _image(src)
    vol = img.volumes[0]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            f, a = r.rsplit(":", 1)
            ids[(f, int(a, 16))] = e["id"]
            if text:
                by_ref[(f, int(a, 16))] = text
    warn, done = [], 0
    for name in scripts(vol, cfg):
        path = cfg["game_dir"] + "/" + name
        d = vol.read(path)
        values = {a: v for (f, a), v in by_ref.items() if f == name}
        sids = {a: v for (f, a), v in ids.items() if f == name}
        new, eng = rebuild(d, values, warn, sids, name)
        room = elfai.room(d)
        if len(new) > room:
            raise SystemExit("%s: %d bytes with its English, the script may take %d; shorten these strings: %s" % (
                name, len(new), room, ", ".join(sorted(set(sids[a] for a in values)))))
        eng_path = cfg["game_dir"] + "/" + name[:-4] + ".ENG"
        if new != d:
            vol.write(path, new)
            done += 1
        if eng:
            try:
                vol.write(eng_path, eng)
            except FileNotFoundError:
                vol.create(eng_path, eng)
    exe = cfg["game_dir"] + "/" + cfg["program"]
    vol.write(exe, elfai.patch_exe(vol.read(exe)))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
