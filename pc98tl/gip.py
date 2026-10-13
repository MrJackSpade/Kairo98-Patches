"""gip 2.08 (Ides, "Gun'sHip"; Cocktail Soft's Kurukuru Party - Princess
Quest): the EVT scripts.

The engine is PQ.OV1 (the gip system), PQ.OV2 (its frame file) and PQ.OVL
(the interpreter and the game's own commands); the scripts are `EVT/*.EVT`.
A script is bytecode run from offset 0.  Each command is an opcode byte and
fixed operands, except:

* `26 00 ...  00` / `26 01 ... 00`: a condition, the commands up to the 00
  joined by AND / OR; `26 02`..`26 09` (three bytes) set or test the flag.
* `28 a`: jump; `29`/`2a a`: jump when the flag is set / clear; `2b`..`2d a`:
  call (always / flag set / clear); `2e`/`2f v n t d`: jump / call through the
  table of n words at t, by variable v (d: the default, FFFF for none).
* `30`/`33 a`: chain to the script file named at a (main / second buffer),
  `31 a`: load a script into the second buffer, `32`: call it.
* `43 a`: show the message at a; `4d v a b`: the message at a or b by a flag.
* `4e ...` (13 bytes, `4f x` before it sets its layout): a menu of n entries
  (byte 10) in a table at bytes 11-12; an entry is six bytes: the word
  offset of its condition (one `26` command), two bytes, the offset of the
  item's text.
* `0d v a`: string variable v gets the string at a.
* `40 w c x y y n h`: open text window w, n full-width letters wide, h lines.
* 0x80-0xDD: the game's own commands (PQ.OVL), fixed lengths.

Every address is an offset from the script's start.  The code never runs
into its strings: a message, an item or a variable value is reached only
through the commands' pointers, so English is laid out anywhere in the file
and the pointers moved to it.

Text is Shift-JIS and ASCII; the game's text driver draws ASCII
half-width.  In a string, 0D starts a new line, 0B waits for a key, 0C
clears the window, 10-1F insert string variable 0-15 (the scripts keep
names, a speaker's name and opening bracket, indents and even "0B 0C" in
them).  The window wraps a line that runs past its edge and scrolls when it
is full; the patch wraps English between words and starts a new page
(0B 0C) before a line would scroll the window.

A script is loaded into a buffer: the main one (DS:1305h, 20000 bytes)
holds the scripts started by `30` and the start script; the second one
(DS:6125h up to the module area at DS:7C80h, 7003 bytes) those loaded by
`31`/`33`.  A script may not outgrow its buffer.
"""
import bisect
import json
import os
import re
import struct

from .disk import DiskImage

FIXED = {0x01: 3, 0x02: 5, 0x03: 3, 0x04: 1, 0x05: 1, 0x06: 1, 0x09: 1, 0x0b: 1, 0x0c: 1, 0x0e: 3, 0x0f: 3,
         0x10: 5, 0x11: 5, 0x12: 3, 0x13: 3, 0x14: 3, 0x15: 5, 0x16: 5, 0x17: 5, 0x18: 5, 0x19: 5, 0x1a: 5,
         0x1b: 5, 0x1c: 5, 0x1d: 5, 0x1e: 5, 0x1f: 7, 0x21: 4, 0x22: 6, 0x23: 6, 0x24: 6, 0x25: 6, 0x32: 1,
         0x3a: 4, 0x3f: 3, 0x40: 8, 0x41: 2, 0x42: 3, 0x44: 2, 0x45: 1, 0x46: 1, 0x47: 2, 0x48: 2, 0x49: 3,
         0x4a: 1, 0x4b: 8, 0x4c: 4, 0x4f: 2, 0x50: 1, 0x53: 3, 0x54: 6, 0x55: 4, 0x56: 3, 0x58: 2, 0x59: 3,
         0x5a: 2, 0x5e: 7, 0x5f: 9, 0x71: 1, 0x72: 1, 0x74: 2, 0x75: 1, 0x7c: 1, 0x7d: 1, 0x7e: 1, 0x7f: 1,
         # (0B and 0C remap a command and run their operand byte as the next command)
         # the game's own commands (PQ.OVL)
         0x80: 1, 0x81: 2, 0x82: 1, 0x83: 3, 0x84: 3, 0x85: 3, 0x86: 3, 0x87: 5, 0x88: 8, 0x89: 1, 0x8a: 1,
         0x8b: 1, 0x8c: 3, 0x8d: 1, 0x8e: 9, 0x8f: 5, 0x90: 5, 0x91: 6, 0x92: 6, 0x93: 15, 0x94: 21, 0x95: 17,
         0x96: 17, 0x97: 1, 0x98: 3, 0x99: 1, 0x9a: 9, 0x9b: 5, 0x9c: 5, 0x9d: 6, 0x9e: 6, 0x9f: 1, 0xa0: 3,
         0xa1: 7, 0xa2: 5, 0xa3: 1, 0xa4: 3, 0xa5: 7, 0xa6: 5, 0xa7: 7, 0xa8: 8, 0xa9: 6, 0xaa: 4, 0xab: 1,
         0xac: 3, 0xad: 3, 0xae: 1, 0xaf: 1, 0xb0: 1, 0xb1: 6, 0xb2: 7, 0xb3: 1, 0xb4: 7, 0xb5: 7, 0xb6: 8,
         0xb7: 8, 0xb8: 8, 0xb9: 8, 0xba: 5, 0xbb: 5, 0xbc: 1, 0xbd: 3, 0xbe: 3, 0xbf: 3, 0xc0: 3, 0xc1: 4,
         0xc2: 10, 0xc3: 7, 0xc4: 7, 0xc5: 5, 0xc6: 5, 0xc7: 5, 0xc8: 5, 0xc9: 1, 0xca: 1, 0xcb: 1, 0xcc: 3,
         0xcd: 4, 0xce: 7, 0xcf: 1, 0xd0: 3, 0xd1: 7, 0xd2: 3, 0xd3: 7, 0xd4: 1, 0xd5: 1, 0xd6: 1, 0xd7: 1,
         0xd8: 3, 0xd9: 3, 0xda: 3, 0xdb: 5, 0xdc: 5, 0xdd: 5}
# op: (length, [(operand offset, kind)]); kind: code (falls through too), jump (does not), msg,
# var (a string variable's value), file, end (chains to a script: does not fall through)
PTR = {0x0d: (4, [(2, "var")]), 0x28: (3, [(1, "jump")]), 0x29: (3, [(1, "code")]), 0x2a: (3, [(1, "code")]),
       0x2b: (3, [(1, "code")]), 0x2c: (3, [(1, "code")]), 0x2d: (3, [(1, "code")]),
       0x30: (3, [(1, "end")]), 0x31: (3, [(1, "file")]), 0x33: (3, [(1, "end")]), 0x3e: (3, [(1, "file")]),
       0x43: (3, [(1, "msg")]), 0x4d: (7, [(3, "msg"), (5, "msg")]), 0x51: (4, [(2, "file")]),
       0x52: (4, [(2, "file")]), 0x57: (7, [(5, "file")]), 0x70: (3, [(1, "file")]), 0x73: (3, [(1, "file")])}
TEXT_KINDS = ("msg", "item", "var")
MAIN_ROOM, SECOND_ROOM = 0x6125 - 0x1305, 0x7C80 - 0x6125
DEFAULT_WINDOW = (0x1B, 4)          # the game's usual message window: 27 letters, four lines
VAR_ROOM = 64                       # a string variable holds 64 bytes and its 00


def _w(d, at):
    return struct.unpack_from("<H", d, at)[0]


def cstr(d, at):
    e = d.find(b"\0", at)
    return d[at:e if e >= 0 else len(d)]


def disasm(d):
    """(ops {offset: (op, length)}, data [(target, kind, pointer site)]).
    Raises ValueError on a command it does not know."""
    ops, data = {}, []
    todo, conds, seen = [0], [], set()

    def run(pc, nested=False):
        while True:
            if pc in ops and not nested:
                return None
            if pc >= len(d):
                raise ValueError("code runs past the end at %x" % pc)
            op = d[pc]
            if op == 0:
                ops[pc] = (0, 1)
                return pc + 1 if nested else None
            stop = False
            if op == 0x26:
                if d[pc + 1] in (0, 1):
                    q = pc + 2
                    while d[q] != 0:
                        q = run(q, True)
                    n = q + 1 - pc
                else:
                    n = 3
            elif op in FIXED:
                n = FIXED[op]
            elif op in PTR:
                n, ptrs = PTR[op]
                for at, kind in ptrs:
                    if kind in ("code", "jump"):
                        todo.append(_w(d, pc + at))
                        stop = stop or kind == "jump"
                    else:
                        data.append((_w(d, pc + at), kind, pc + at))
                        stop = stop or kind == "end"
            elif op in (0x2e, 0x2f):
                n = 8
                cnt, tab, dflt = d[pc + 3], _w(d, pc + 4), _w(d, pc + 6)
                data.append((tab, "table%d" % cnt, pc + 4))
                todo.extend(_w(d, tab + 2 * k) for k in range(cnt))
                if dflt != 0xFFFF:
                    todo.append(dflt)
                stop = op == 0x2e and dflt != 0xFFFF
            elif op == 0x4e:
                n = 13
                cnt, tab = d[pc + 0xa], _w(d, pc + 0xb)
                data.append((tab, "menu%d" % cnt, pc + 0xb))
                for k in range(cnt):
                    # (the menu runs an entry's condition as one command, 26 xx ...)
                    conds.append(_w(d, tab + 6 * k))
                    data.append((_w(d, tab + 6 * k + 4), "item", tab + 6 * k + 4))
            else:
                raise ValueError("unknown command %02x at %x" % (op, pc))
            ops[pc] = (op, n)
            if nested:
                return pc + n
            if stop:
                return None
            pc += n

    while True:
        while todo or conds:
            if conds:
                c = conds.pop()
                if c not in ops:
                    if d[c] != 0x26:
                        raise ValueError("menu condition %02x at %x" % (d[c], c))
                    run(c, True)
                continue
            t = todo.pop()
            if t not in seen:
                seen.add(t)
                run(t)
        # a script holds further entries the code does not point at (the game's commands start
        # them): each begins right after an end, 00, or a jump or chain that does not come
        # back, where nothing else lies; one that does not decode cleanly is data
        taken = _taken(d, ops, data)
        found = False
        for a, (op, n) in sorted(ops.items()):
            t = a + n
            if op not in (0, 0x28, 0x30, 0x33) or t >= len(d) or t in taken or t in seen:
                continue
            seen.add(t)
            o2, d2, c2 = dict(ops), list(data), len(todo)
            try:
                run(t)
                while todo or conds:
                    if conds:
                        c = conds.pop()
                        if c not in ops:
                            if d[c] != 0x26:
                                raise ValueError
                            run(c, True)
                        continue
                    u = todo.pop()
                    if u not in seen:
                        seen.add(u)
                        run(u)
                new = set()
                for x, (op2, n2) in ops.items():
                    if x not in o2:
                        new.update(range(x, x + n2))
                if new & taken:
                    raise ValueError
                found = True
                break
            except (ValueError, IndexError, struct.error):
                ops.clear()
                ops.update(o2)
                data[:] = d2
                del todo[c2:]
                conds.clear()
        if not found:
            return ops, data


def _span(d, a, kind):
    if kind.startswith("table"):
        return 2 * int(kind[5:])
    if kind.startswith("menu"):
        return 6 * int(kind[4:])
    return len(cstr(d, a)) + 1


def _taken(d, ops, data):
    taken = set()
    for a, (op, n) in ops.items():
        taken.update(range(a, a + n))
    for a, kind, _s in data:
        taken.update(range(a, a + _span(d, a, kind)))
    return taken


def windows(d, ops):
    """{offset of a 43/4d command: (letters, lines) of the window it shows in}:
    the last window opened (40) before it in the file."""
    out, cur = {}, DEFAULT_WINDOW
    for a in sorted(ops):
        op = ops[a][0]
        if op == 0x40:
            cur = (d[a + 6], d[a + 7])
        elif op in (0x43, 0x4d):
            out[a] = cur
    return out


# ---- strings

_CTL = b"\x0b\x0c\x0d"


def split_raw(raw):
    """(head control bytes, body, tail control bytes) of a string."""
    m = re.match(rb"^([\x0b\x0c\x0d]*)(.*?)([\x0b\x0c\x0d]*)$", raw, re.S)
    return m.group(1), m.group(2), m.group(3)


def body_text(body):
    """A string's body as text: Shift-JIS, ASCII, 0D as a line break,
    10-1F as {Xn} (string variable n), PC-98 own characters as {Uxxxx}."""
    out, i = [], 0
    while i < len(body):
        b = body[i]
        if 0x10 <= b <= 0x1F:
            out.append("{X%d}" % (b - 0x10))
            i += 1
        elif b == 0x0D:
            out.append("\n")
            i += 1
        elif (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < len(body):
            pair = body[i:i + 2]
            try:
                ch = pair.decode("cp932")
                out.append(ch if b < 0xEB else "{U%s}" % pair.hex())
            except UnicodeDecodeError:
                out.append("{U%s}" % pair.hex())
            i += 2
        elif b < 0x20:
            out.append("{C%02x}" % b)
            i += 1
        else:
            out.append(chr(b))
            i += 1
    return "".join(out)


_TOKEN = re.compile(r"\{([XUC])([0-9a-fA-F]+)\}")


def encode(text):
    """English (or kept Japanese) to bytes: tokens back to their bytes,
    ASCII as is, anything else Shift-JIS (typographic quotes and dashes
    as ASCII)."""
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
    out, pos = bytearray(), 0
    for m in _TOKEN.finditer(text):
        out += _plain(text[pos:m.start()], subst)
        kind, val = m.group(1), m.group(2)
        out += bytes([0x10 + int(val)]) if kind == "X" else bytes.fromhex(val) if kind == "U" else bytes([int(val, 16)])
        pos = m.end()
    out += _plain(text[pos:], subst)
    return bytes(out)


def _plain(s, subst):
    out = bytearray()
    for ch in s:
        ch = subst.get(ch, ch)
        for c in ch:
            if c == "\n":
                out += b"\r"
            elif 0x20 <= ord(c) < 0x7F:
                out.append(ord(c))
            else:
                out += c.encode("cp932", "replace")
    return bytes(out)


def cells(b, varw=None):
    """Display width of string bytes: ASCII one cell, Shift-JIS two; a
    variable insert the width of its value (varw: {n: cells})."""
    n, i = 0, 0
    while i < len(b):
        c = b[i]
        if 0x10 <= c <= 0x1F:
            n += (varw or {}).get(c - 0x10, 0)
            i += 1
        elif 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            n += 2
            i += 2
        elif c < 0x20:
            i += 1
        else:
            n += 1
            i += 1
    return n


def file_strings(d):
    """[(address, kind, raw)] of the text a script points at (one entry per
    address; a menu item's kind wins over a message's)."""
    ops, data = disasm(d)
    out = {}
    for a, kind, _site in data:
        if kind in TEXT_KINDS and a not in out:
            out[a] = kind
    return [(a, out[a], cstr(d, a)) for a in sorted(out)]


def menu_widths(d, ops, data):
    """{item address: letters}: each item's menu width (4e byte 6)."""
    out = {}
    for a, (op, n) in ops.items():
        if op == 0x4e:
            cnt, tab = d[a + 0xa], _w(d, a + 0xb)
            for k in range(cnt):
                t = _w(d, tab + 6 * k + 4)
                out[t] = min(out.get(t, 255), d[a + 6])
    return out


def var_values(d, ops):
    """{variable: raw value} the script sets (0d v a), in address order."""
    out = {}
    for a in sorted(ops):
        if ops[a][0] == 0x0d:
            out[d[a + 1] & 0xF] = cstr(d, _w(d, a + 2))
    return out


# ---- the game folder

def _vol(cfg, src):
    return DiskImage(src)


def _evts(vol, cfg):
    d = cfg["game_dir"] + "/EVT"
    return [(p.split("/")[-1], p) for p, *_ in vol.walk() if p.upper().startswith(d.upper() + "/")
            and p.upper().endswith(".EVT")]


def rooms(vol, cfg):
    """{EVT name: bytes its buffer holds}: the second buffer for a script
    loaded by 31/33 (or one no script names), the main one otherwise."""
    named = {}
    for name, path in _evts(vol, cfg):
        d = vol.read(path)
        ops, data = disasm(d)
        for a, kind, site in data:
            if kind in ("file", "end"):
                f = cstr(d, a).decode("cp932", "replace").split("\\")[-1].upper()
                if f.endswith(".EVT"):
                    named.setdefault(f, set()).add(d[site - 1])
    start = cfg.get("start_script", "START.EVT").upper()
    out = {}
    for name, _p in _evts(vol, cfg):
        how = named.get(name.upper(), set())
        out[name] = MAIN_ROOM if name.upper() == start or (how and how <= {0x30}) else SECOND_ROOM
    return out


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


PREFIX = {"msg": "m", "item": "i", "var": "v"}


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = _vol(cfg, src).volumes[0]
    merged, order = {}, []
    for name, path in _evts(vol, cfg):
        d = vol.read(path)
        ops, data = disasm(d)
        win = windows(d, ops)
        mw = menu_widths(d, ops, data)
        vals = var_values(d, ops)
        # each message's window: the window of the first command showing it
        starts = sorted(ops)
        mwin = {}
        for a, kind, site in data:
            if kind == "msg":
                cmd = starts[bisect.bisect_right(starts, site) - 1]
                mwin.setdefault(a, win.get(cmd, DEFAULT_WINDOW))
        for a, kind, raw in file_strings(d):
            head, body, tail = split_raw(raw)
            jp = body_text(body)
            if not jp.strip(" 　\n") or not re.search(r"[^\x00-\x7f]", jp):
                continue
            if kind == "msg":
                cellsn = 2 * mwin[a][0] - 1
            elif kind == "item":
                cellsn = 2 * mw.get(a, 0) or cells(body)
            else:
                cellsn = VAR_ROOM
            key = (kind, jp)
            ref = "%s:%04x" % (name, a)
            if key in merged:
                merged[key]["refs"].append(ref)
                continue
            e = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cellsn}
            used = sorted({int(m) for m in re.findall(r"\{X(\d+)\}", jp)})
            if used:
                e["note"] = "; ".join("{X%d} = %s" % (n, body_text(vals[n]).replace("\x0b", "").replace("\x0c", "") or
                                                      "(a page break)") if n in vals else "{X%d}: a string variable"
                                      % n for n in used)
            merged[key] = e
            order.append(key)
    counts = {}
    strings = []
    for k in order:
        e = merged[k]
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        strings.append({"id": "%s%05d" % (PREFIX[e["kind"]], counts[e["kind"]]), **e})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):     # keep translations and notes
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev and prev.get("en"):
                e["en"] = prev["en"]
    doc = {"game": cfg["title"], "source_image_sha256": sha256(src), "strings": strings}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


# ---- patching

def _words(text):
    return text.split(" ")


def lay_out(text_bytes_fn, en, width, lines_per_page, state, varw, indent_cells=0):
    """Wrap one message's English to the window and page it: returns its
    bytes (lines joined with 0D; 0B 0C where a page fills) and updates
    state {"line", "col"}.  text_bytes_fn encodes a piece of text."""
    out = bytearray()
    paras = en.split("\n")
    for pi, para in enumerate(paras):
        if pi:
            out += b"\r"
            state["line"] += 1
            state["col"] = 0
        words = para.split(" ")
        lead = len(para) - len(para.lstrip(" "))
        first = True
        for w in words:
            if first:
                piece = text_bytes_fn(" " * lead + w.lstrip(" ") if lead else w)
                first = False
            else:
                piece = text_bytes_fn(" " + w)
            wc = cells(piece, varw)
            if state["col"] and state["col"] + wc > width:
                # (a new line; the space before the word is not drawn)
                piece = text_bytes_fn(" " * indent_cells + w)
                wc = cells(piece, varw)
                if state["line"] + 1 >= lines_per_page:
                    out += b"\x0b\x0c"
                    state["line"] = 0
                else:
                    out += b"\r"
                    state["line"] += 1
                state["col"] = 0
            while wc > width:
                # a word longer than the window: split it
                k = len(piece)
                while k > 1 and cells(piece[:k], varw) > width - state["col"]:
                    k -= 1
                out += piece[:k]
                piece = piece[k:]
                wc = cells(piece, varw)
                if state["line"] + 1 >= lines_per_page:
                    out += b"\x0b\x0c"
                    state["line"] = 0
                else:
                    out += b"\r"
                    state["line"] += 1
                state["col"] = 0
            out += piece
            state["col"] += wc
    return bytes(out)


def _advance(state, ctl, lines_per_page):
    """The window after control bytes (0D a line, 0C a fresh window)."""
    for c in ctl:
        if c == 0x0D:
            state["line"] += 1
            state["col"] = 0
            if state["line"] >= lines_per_page:
                state["line"] = lines_per_page - 1
        elif c == 0x0C:
            state["line"] = 0
            state["col"] = 0


def build_file(d, values, room, fit, warn, ids, name):
    """The script with the English in values ({address: text}) laid out
    and the pointers moved; values only for strings with English."""
    ops, data = disasm(d)
    if not values:
        return d
    win = windows(d, ops)
    mw = menu_widths(d, ops, data)
    raw_vals = var_values(d, ops)
    # the variables' bytes in this build (an English value where one is given)
    var_bytes = {}
    for a in sorted(ops):
        if ops[a][0] == 0x0d:
            t = _w(d, a + 2)
            v = d[a + 1] & 0xF
            var_bytes[v] = encode(values[t])[:VAR_ROOM] if t in values else raw_vals[v]
    varw = {v: cells(b) for v, b in var_bytes.items()}
    jpw = {v: cells(b) for v, b in raw_vals.items()}
    new = {}
    # messages in command order, the window followed across them
    state, cur = {"line": 0, "col": 0}, DEFAULT_WINDOW
    for a in sorted(ops):
        op = ops[a][0]
        if op == 0x40:
            cur = (d[a + 6], d[a + 7])
            state = {"line": 0, "col": 0}
        elif op == 0:
            state = {"line": 0, "col": 0}
        elif op in (0x43, 0x4d):
            # (4d shows one of two messages: each starts where the window is)
            targets = [_w(d, a + 1)] if op == 0x43 else [_w(d, a + 3), _w(d, a + 5)]
            after = None
            for t in targets:
                raw = cstr(d, t)
                head, body, tail = split_raw(raw)
                # (a letter in the window's last column wraps the line itself: English keeps one short)
                width, lines = 2 * cur[0] - 1, max(1, cur[1])
                st = dict(state)
                _advance(st, head, lines)
                if t in values and t not in new:
                    en = values[t]
                    if st["col"] and st.get("last", " ") != " " and en[:1] not in (" ", "　", ""):
                        # (a message going on along the line: a space between the words)
                        en = " " + en
                    body_b = lay_out(encode, en, width, lines, st, varw)
                    if body_b:
                        st["last"] = chr(body_b[-1])
                    if not set(tail) & {0x0c, 0x0d} and cells(body, jpw) and cells(body, jpw) % (2 * cur[0]) == 0:
                        # (the Japanese filled its line, which the window wraps by itself: the English
                        # ends its line too, so the next message starts on a line of its own)
                        tail = b"\r" + tail
                    if tail[:1] == b"\r" and st["line"] >= lines - 1:
                        # (a new line from the window's last line would scroll it, which leaves the
                        # bottom line, half outside the frame, behind: a new page instead)
                        tail = b"\x0b\x0c" + tail[1:].lstrip(b"\x0b")
                    new[t] = head + body_b + tail
                else:
                    st["col"] += cells(body, varw)
                    if body:
                        st["last"] = chr(body[-1])
                _advance(st, tail, lines)
                after = after or st
            state = after
    for t, en in values.items():
        if t in new:
            continue
        raw = cstr(d, t)
        head, body, tail = split_raw(raw)
        b = encode(en)
        if t in mw:
            room_cells = 2 * mw[t]
            if cells(b) > room_cells:
                warn.append("%s: %d cells, the menu has %d" % (ids.get((name, t), hex(t)), cells(b), room_cells))
                while cells(b) > room_cells:
                    b = b[:-1]
                if b and (0x81 <= b[-1] <= 0x9F or 0xE0 <= b[-1] <= 0xFC) and cells(b[:-1]) + 2 > room_cells:
                    b = b[:-1]
        elif len(b) > VAR_ROOM:
            warn.append("%s: %d bytes, the variable holds %d" % (ids.get((name, t), hex(t)), len(b), VAR_ROOM))
            b = b[:VAR_ROOM]
        new[t] = head + b + tail
    return _place(d, ops, data, new, room, fit, warn, ids, name)


def _place(d, ops, data, new, room, fit, warn, ids, name):
    """Lay the new strings into the bytes the replaced ones leave free and
    after the script's end, and point every pointer at its string."""
    taken_other = set()
    for a, (op, n) in ops.items():
        taken_other.update(range(a, a + n))
    for a, kind, _s in data:
        if kind not in TEXT_KINDS or a not in new:
            taken_other.update(range(a, a + _span(d, a, kind)))
    free = set()
    for a in new:
        free.update(range(a, a + len(cstr(d, a)) + 1))
    free -= taken_other
    holes = []
    for a in sorted(free):
        if holes and holes[-1][1] == a:
            holes[-1][1] = a + 1
        else:
            holes.append([a, a + 1])
    cut_total = 0
    while True:
        out, where = _pack(d, new, holes)
        over = len(out) - room
        if over <= 0:
            break
        if not fit:
            raise SystemExit("%s: the English takes %d bytes more than the script's buffer holds (%d bytes); "
                             "shorten these strings: %s" % (name, over, room, ", ".join(
                                 sorted({ids.get((name, t), hex(t)) for t in new}))))
        # (the --pseudo filler: the longest strings are cut until the script fits)
        cut_total += over
        for t in sorted(new, key=lambda x: -len(new[x])):
            if over <= 0:
                break
            head, body, tail = split_raw(new[t])
            cut = min(over, max(0, len(body) - 8))
            if not cut:
                continue
            body = body[:len(body) - cut]
            if body and (0x81 <= body[-1] <= 0x9F or 0xE0 <= body[-1] <= 0xFC):
                body = body[:-1]
                cut += 1
            new[t] = head + body + tail
            over -= cut
        if over > 0:
            raise SystemExit("%s: the script does not fit its buffer even with its strings cut" % name)
    if cut_total:
        warn.append("%s: the filler was cut by %d bytes to fit the script's buffer" % (name, cut_total))
    for a, kind, site in data:
        if kind in TEXT_KINDS and a in where:
            struct.pack_into("<H", out, site, where[a])
    return bytes(out)


def _pack(d, new, holes):
    """(the script with the new strings laid out, {old address: new
    address}): longest first, each into the first free run it fits, the
    rest after the end."""
    out = bytearray(d)
    holes = [list(h) for h in holes]
    where = {}
    for t in sorted(new, key=lambda x: -len(new[x])):
        b = new[t] + b"\0"
        for h in holes:
            if h[1] - h[0] >= len(b):
                where[t] = h[0]
                out[h[0]:h[0] + len(b)] = b
                h[0] += len(b)
                break
        else:
            where[t] = len(out)
            out += b
    return out, where


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = _vol(cfg, src)
    vol = img.volumes[0]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        if mode == "pseudo":
            text = pseudo(e["id"], cells(encode(e["jp"])))
            used = re.findall(r"\{X\d+\}", e["jp"])
            text = (" ".join(used) + " " + text) if used else text
        else:
            text = e["en"]
        for r in e["refs"]:
            f, a = r.rsplit(":", 1)
            ids[(f, int(a, 16))] = e["id"]
            if text:
                by_ref[(f, int(a, 16))] = text
    room = rooms(vol, cfg)
    warn, done = [], 0
    for name, path in _evts(vol, cfg):
        d = vol.read(path)
        values = {a: t for (f, a), t in by_ref.items() if f == name}
        new = build_file(d, values, room[name], mode == "pseudo", warn, ids, name)
        if new != d:
            vol.write(path, new)
            done += 1
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated, %d scripts rebuilt)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"]), done))
