"""Translation extract/patch for Alice Soft System 2 games.

Strings file layout (UTF-8 JSON):
{
  "game": ..., "engine": "alice-sys2", "config": {...},
  "strings": [
    {"id": "m00012", "kind": "msg"|"menu"|"name"|"verb"|"obj",
     "jp": "...", "en": "", "refs": ["p01:0074", ...], "max_cells": 34}
  ]
}
* Identical Japanese strings are merged (translate once, applied at every ref).
* "\n" in jp marks an original line break.  In en, "\n" forces a break;
  everything else is re-wrapped to max_cells automatically.
* Widths are in 16px screen cells: one Japanese character = one cell; with the
  packed encoding one cell holds two English characters.
* {X1}, {X2}... are runtime inserts (e.g. character names).  Keep them.
* Empty "en" leaves the Japanese in place, so partial translations work.
"""
import hashlib
import struct

from .alice_sys import ADisk, Page, mblen
from . import alice3_font, alice1_text
from . import packfont
from .text import encode_fullwidth, wrap, pseudo, TOKEN_RE

TOKEN_CELLS = 4  # assumed width of a {Xn} insert


_KANA = None  # optional engine table: half-width byte A0-DF -> displayed str


def set_kana_table(table):
    """Some games store hiragana as half-width katakana bytes and convert them
    at draw time (Dalk: ADV.COM CS:1A29).  With the table set, "jp" shows the
    text as it appears on screen, which machine translation handles far better."""
    global _KANA
    _KANA = table


def _jp(b):
    if not _KANA:
        return b.decode("cp932", "replace")
    out, i = [], 0
    while i < len(b):
        n = mblen(b[i])
        if n == 1 and 0xA0 <= b[i] <= 0xDF and _KANA[b[i] - 0xA0].strip():
            out.append(_KANA[b[i] - 0xA0])
        else:
            out.append(b[i:i + n].decode("cp932", "replace"))
        i += n
    return "".join(out)


def jp_cells(data):
    """Screen cells of original script text (half-width kana are drawn full-width)."""
    n = i = 0
    while i < len(data):
        i += mblen(data[i])
        n += 1
    return n


class Encoder:
    def __init__(self, kind):
        self.kind = kind

    def encode(self, s):
        if self.kind == "packed":
            return packfont.encode(s, encode_fullwidth)
        if self.kind == "halfkana":
            return alice3_font.encode(s, encode_fullwidth)
        if self.kind == "textvram":
            return alice1_text.encode(s, encode_fullwidth)
        return encode_fullwidth(s)

    def cells(self, s):
        plain = TOKEN_RE.sub("", s)
        extra = TOKEN_CELLS * len(TOKEN_RE.findall(s))
        if self.kind == "packed":
            return packfont.cells(plain) + extra
        if self.kind == "halfkana":
            return alice3_font.cells(plain) + extra
        if self.kind == "textvram":
            return alice1_text.cells(plain) + extra
        return (sum(1 if c == " " else 2 for c in plain) + 1) // 2 + extra


class Block:
    def __init__(self, page, start, end, kind):
        self.page, self.start, self.end, self.kind = page, start, end, kind

    def ops(self):
        return self.page.ops[self.start:self.end]

    def jp_text(self):
        s = ""
        for op in self.ops():
            if op.cmd == "text":
                s += _jp(op.text)
            elif op.cmd == "R":
                s += "\n"
            elif op.cmd == "X":
                s += "{X%d}" % op.parts[0][1]
        return s

    @property
    def ref(self):
        return "%sp%02d:%04x" % (self.page.prefix, self.page.index, self.page.ops[self.start].addr)


def find_blocks(page):
    """Runs of text / name-insert / newline ops that no jump lands inside."""
    targets = page.all_targets()
    ops = page.ops
    blocks = []
    i = 0
    while i < len(ops):
        if ops[i].cmd in ("text", "X"):
            j = i + 1
            while j < len(ops) and ops[j].cmd in ("text", "X", "R") and ops[j].addr not in targets:
                j += 1
            while ops[j - 1].cmd == "R":  # trailing newlines stay outside
                j -= 1
            if any(o.cmd == "text" for o in ops[i:j]):
                kind = "menu" if i > 0 and ops[i - 1].cmd == "$" else "msg"
                blocks.append(Block(page, i, j, kind))
            i = j
        else:
            i += 1
    return blocks


def _consts(raw, start):
    """Values of the expressions in raw[start:]; None where not a constant."""
    vals, p, cur = [], start, []
    while p < len(raw):
        x = raw[p]
        if x == 0x7F:
            vals.append(cur[0] if len(cur) == 1 and cur[0] is not None else None)
            cur, p = [], p + 1
            continue
        if 0x40 <= x <= 0x76:
            cur.append(x - 0x40)
            p += 1
        elif x <= 0x3F:
            cur.append(((x & 0x3F) << 8) | raw[p + 1])
            p += 2
        else:  # variables and operators: not a plain constant
            cur.append(None)
            p += 2 if x >= 0xC0 else 1
    return vals


def window_command(op, version):
    """(sub-command, index, p1..p5) of a 'B' window command, None for non-constants."""
    raw = op.parts[0]
    if version == 3:
        vals = _consts(raw, 2)
        return [raw[1]] + vals
    return _consts(raw, 1)


def window_cells(p1, p3):
    """Text window width in 16px cells from its left/right coordinates
    (8px columns when small, pixels otherwise)."""
    if p1 is None or p3 is None or p3 <= p1:
        return None
    px = (p3 - p1) * 8 if max(p1, p3) <= 80 else (p3 & 0xFFF8) - (p1 & 0xFFF8)
    return max(4, px // 16)


def parse_ag00(data):
    head, _, rest = data.partition(b"\r\n")
    _d0, nverb, nobj, _d3 = map(int, head.split(b","))
    items = rest.split(b"\r")
    return head, items[:nverb], items[nverb:nverb + nobj]


def build_ag00(head, verbs, objs, orig):
    body = head + b"\r\n" + b"\r".join(verbs + objs) + b"\r"
    if len(body) + 1 <= len(orig):
        body = body.ljust(len(orig) - 1, b"\0")
    return body + b"\x1a"


class Sys2Game:
    # msg_cells is the floor: each message may use the width of its own widest
    # Japanese line (the original authors kept every line inside its window;
    # the engine never wraps on its own), but never less than this.
    DEFAULTS = {"encoding": "packed", "msg_cells": 21, "menu_cells": 16,
                "name_bytes": 32, "verb_cells": 10, "obj_cells": 10,
                "max_page_bytes": 65000}

    def __init__(self, vol, game_dir, version=2, ag00="AG00.DAT", config=None,
                 disks=None, scope=None, prefix="", adisk_bytes=None):
        """disks: {disk number: path} overriding ADISK/BDISK discovery in game_dir.
        scope: disk numbers whose pages this instance handles (scenario sets share
        disk 1 but carry their own BDISK).  prefix: string-ref prefix per set."""
        self.vol = vol
        self.game_dir = game_dir
        self.version = version
        self.config = dict(self.DEFAULTS)
        self.config.update(config or {})
        self.enc = Encoder(self.config["encoding"])
        # scenario disks: ADISK.DAT = 1, BDISK.DAT = 2, ...
        self.disk_paths, files = {}, {}
        for n, letter in enumerate("ABCDEFGH", 1):
            path = (disks or {}).get(n) or "%s/%sDISK.DAT" % (game_dir, letter)
            try:
                files[n] = vol.read(path)
            except FileNotFoundError:
                continue
            self.disk_paths[n] = path
        if adisk_bytes is not None:  # link table from another disk image (floppy sets)
            files[1] = adisk_bytes
            self.disk_paths.pop(1, None)
        self.adisk = ADisk(files)
        self.scope = set(scope) if scope else set(files)
        self.prefix = prefix
        self.pages = {}
        wanted = self._reachable(version) if self.config.get("reachable_only") else None
        for i, d in enumerate(self.adisk.page_data):
            if d is not None and self.adisk.links[i][0] in self.scope and (wanted is None or i in wanted):
                self.pages[i] = Page(i, d, version)
                self.pages[i].prefix = prefix
        self.ag00_path = game_dir + "/" + ag00
        try:
            vol.find(self.ag00_path)
        except FileNotFoundError:
            self.ag00_path = None

    def layout(self, page, blocks, on_block):
        """Walk a page in order, tracking the active text window's width and the
        column where the next text starts.  Calls on_block(block, width, first)
        for each message block (first = room left on the current line) and
        expects the number of cells the block's last line uses (or None when
        the block is unchanged, to use its Japanese width)."""
        starts = {b.start: b for b in blocks}
        msg_widths = [max(jp_cells(l.encode("cp932", "replace")) for l in b.jp_text().split("\n"))
                      for b in blocks if b.kind == "msg"]
        fallback = max(msg_widths + [8])  # widest Japanese line on this page
        widths, active, col = {}, None, 0
        ops, k = page.ops, 0
        while k < len(ops):
            op = ops[k]
            b = starts.get(k)
            if b is not None:
                known = widths.get(active) is not None
                w = widths.get(active) or fallback
                jp_w = max(jp_cells(l.encode("cp932", "replace")) for l in b.jp_text().split("\n"))
                w = max(w, jp_w) if col == 0 else w
                b.window_known = known
                used = on_block(b, w, max(0, w - col))
                if b.kind != "msg":  # menu items go to the menu box, not the text line
                    k = b.end
                    continue
                if used is None:  # unchanged: advance by the Japanese
                    last = b.jp_text().split("\n")[-1]
                    used = jp_cells(last.encode("cp932", "replace")) + (col if "\n" not in b.jp_text() else 0)
                col = used
                k = b.end
                continue
            if op.cmd == "B":
                v = window_command(op, self.version)
                if len(v) >= 7 and v[0] == 3:
                    widths[v[1]] = window_cells(v[2], v[4])
                elif len(v) >= 7 and v[0] == 4 and v[6] == 0:
                    active, col = v[1], 0
            elif op.cmd in ("R", "A"):
                col = 0
            elif op.cmd == "X":
                col += TOKEN_CELLS
            elif op.cmd == "text":
                col += jp_cells(op.text)
            k += 1

    def _reachable(self, version):
        """Pages reachable from page 0 through page jumps/calls with constant
        targets.  Used where a disk's pointer table carries filler entries
        (Super D.P.S).  If any jump target is computed at runtime, every
        parseable page is kept so nothing can silently drop out."""
        from .alice_sys import SysError
        seen, todo, dynamic = set(), [0], False
        while todo:
            i = todo.pop()
            if i in seen or i >= len(self.adisk.page_data) or self.adisk.page_data[i] is None:
                continue
            seen.add(i)
            try:
                page = Page(i, self.adisk.page_data[i], version)
            except SysError:
                continue
            for op in page.ops:
                if op.cmd in ("&", "%"):
                    e = op.parts[0][1:]
                    if len(e) == 2 and 0x40 <= e[0] <= 0x76 and e[1] == 0x7F:
                        todo.append(e[0] - 0x40)
                    elif len(e) == 3 and e[0] <= 0x3F and e[2] == 0x7F:
                        todo.append(((e[0] & 0x3F) << 8) | e[1])
                    else:
                        dynamic = True
        if dynamic:
            ok = set()
            for i, d in enumerate(self.adisk.page_data):
                if d is None:
                    continue
                try:
                    Page(i, d, version)
                    ok.add(i)
                except SysError:
                    pass
            return ok
        return seen

    # ---------------------------------------------------------------- extract
    def extract(self, title, image_sha):
        entries, order = {}, []
        cfg = self.config

        def add(kind, jp, ref, max_cells):
            key = (kind, jp)
            if key not in entries:
                entries[key] = {"id": None, "kind": kind, "jp": jp, "en": "",
                                "refs": [], "max_cells": max_cells}
                order.append(key)
            entries[key]["refs"].append(ref)

        for pi, page in self.pages.items():
            blocks = find_blocks(page)
            room = {}
            self.layout(page, blocks, lambda b, w, first: room.__setitem__(b.start, w))
            for b in blocks:
                jp = b.jp_text()
                widest = max(jp_cells(l.encode("cp932", "replace")) for l in jp.split("\n"))
                if b.kind == "menu":
                    # menu boxes grow with their text from a fixed position, so each
                    # item keeps its own Japanese width (the original authors' layout)
                    add(b.kind, jp, b.ref, max(4, widest) if cfg.get("menu_fit_jp") else max(cfg["menu_cells"], widest))
                else:
                    add(b.kind, jp, b.ref, max(widest, room.get(b.start, cfg["msg_cells"])))
            for op in page.ops:
                if op.cmd == "M" and op.text:
                    add("name", _jp(op.text), "%sp%02d:%04x" % (self.prefix, pi, op.addr), cfg["name_bytes"] // 2)
        use_ag00 = self.ag00_path and 1 in self.scope
        head, verbs, objs = parse_ag00(self.vol.read(self.ag00_path)) if use_ag00 else (b"", [], [])
        for n, v in enumerate(verbs):
            if v.strip():
                add("verb", _jp(v), "verb:%d" % n, cfg["verb_cells"])
        for n, o in enumerate(objs):
            if o.strip():
                add("obj", _jp(o), "obj:%d" % n, cfg["obj_cells"])
        prefix = {"msg": "m", "menu": "u", "name": "n", "verb": "v", "obj": "o"}
        counters, out = {}, []
        for key in order:
            e = entries[key]
            counters[e["kind"]] = counters.get(e["kind"], 0) + 1
            e["id"] = "%s%05d" % (prefix[e["kind"]], counters[e["kind"]])
            out.append(e)
        return {"game": title, "engine": "alice-sys2", "source_image_sha256": image_sha,
                "config": cfg, "strings": out}

    # ------------------------------------------------------------------ patch
    def patch(self, doc, mode="en", report=None):
        """mode: 'en' (use translations) or 'pseudo' (stress-test filler)."""
        report = report if report is not None else []
        by_ref = {}
        for e in doc["strings"]:
            if mode == "en":
                text = e["en"]
            else:
                jp_w = max(len(l) for l in e["jp"].split("\n"))
                text = pseudo(e["id"], jp_w * 2, factor=2.5)  # ~2.5 letters per JP char
                if e["kind"] != "msg":  # fixed-size slots: stay inside the limit
                    text = text[:max(1, e.get("max_cells", e.get("max_bytes", 32) // 2) * 2)]
            if text:
                for r in e["refs"]:
                    by_ref[r] = (e, text)

        new_pages = []
        for i in range(len(self.adisk.links)):
            page = self.pages.get(i)
            if page is None:
                new_pages.append(self.adisk.page_data[i])
                continue
            repl = {}

            def place(b, width, first):
                hit = by_ref.get(b.ref)
                if not hit:
                    return None
                parts, used = self._encode_block(hit[0], hit[1], report, width, first)
                jp_lines = b.jp_text().count(chr(10)) + 1
                en_lines = sum(1 for x in parts if x == b"R") + 1
                if not getattr(b, "window_known", True) and en_lines > jp_lines and mode != "pseudo":
                    report.append("%s: %d lines where the Japanese has %d, in a window of unknown size "
                                  "(may overlap; shorten)" % (hit[0]["id"], en_lines, jp_lines))
                repl[b.start] = parts
                for k in range(b.start + 1, b.end):
                    repl[k] = []
                return used

            self.layout(page, find_blocks(page), place)
            for k, op in enumerate(page.ops):
                if op.cmd == "M":
                    hit = by_ref.get("%sp%02d:%04x" % (self.prefix, i, op.addr))
                    if hit:
                        e, text = hit
                        text = text.replace("\n", " ")
                        if self.enc.cells(text) > e["max_cells"]:
                            report.append("%s: name wider than %d cells" % (e["id"], e["max_cells"]))
                        enc = self.enc.encode(text)
                        lim = self.config["name_bytes"]
                        if len(enc) > lim:
                            report.append("%s: name exceeds %d bytes, truncated" % (e["id"], lim))
                            enc = _trim(enc, lim)
                        repl[k] = [b"M", enc, b":"]
            try:
                data = page.assemble(repl)
            except struct.error:  # an address no longer fits in 16 bits
                data = None
            if data is None or len(data) > self.config["max_page_bytes"]:
                size = "over 64 KB" if data is None else "%d bytes" % len(data)
                if mode != "pseudo":
                    raise ValueError("page %d is %s after patching (limit %d)"
                                     % (i, size, self.config["max_page_bytes"]))
                report.append("page %d would be %s (limit %d); left in Japanese for this test"
                              % (i, size, self.config["max_page_bytes"]))
                data = page.assemble()
            new_pages.append(data)
        for n, data in self.adisk.build(new_pages).items():
            if n in self.scope and n in self.disk_paths:
                self.vol.write(self.disk_paths[n], data)
        if not self.ag00_path or 1 not in self.scope:
            return report

        orig = self.vol.read(self.ag00_path)
        head, verbs, objs = parse_ag00(orig)
        verbs, objs = list(verbs), list(objs)
        for kind, arr in (("verb", verbs), ("obj", objs)):
            for n in range(len(arr)):
                hit = by_ref.get("%s:%d" % (kind, n))
                if hit:
                    e, text = hit
                    text = text.replace("\n", " ")
                    if self.enc.cells(text) > e["max_cells"]:
                        report.append("%s: %s wider than %d cells" % (e["id"], kind, e["max_cells"]))
                    arr[n] = self.enc.encode(text)
        ag = build_ag00(head, verbs, objs, orig)
        if len(ag) > len(orig):
            report.append("AG00.DAT grew from %d to %d bytes" % (len(orig), len(ag)))
        self.vol.write(self.ag00_path, ag)
        return report

    def _encode_block(self, e, text, report, width=None, first=None):
        if e["kind"] == "msg":
            width = width or e["max_cells"]
            lines = wrap(text, width, width=self.enc.cells, first=first)
        else:
            lines = [text.replace("\n", " ")]
            if self.enc.cells(lines[0]) > e["max_cells"]:
                report.append("%s: menu item wider than %d cells" % (e["id"], e["max_cells"]))
        parts = []
        for n, line in enumerate(lines):
            if n:
                parts.append(b"R")
            pos = 0
            for m in TOKEN_RE.finditer(line):
                if m.start() > pos:
                    parts.append(self.enc.encode(line[pos:m.start()]))
                parts.append(bytes([ord(m.group(1)), int(m.group(2))]))
                pos = m.end()
            if pos < len(line):
                parts.append(self.enc.encode(line[pos:]))
        parts = parts or [self.enc.encode(" ")]
        if e["kind"] != "msg":
            return parts, None
        last = self.enc.cells(lines[-1]) if lines else 0
        if len(lines) == 1 and first is not None:  # continued on the same line
            last += width - first
        return parts, last


def _trim(enc, lim):
    i = 0
    while i < len(enc):
        n = mblen(enc[i])
        if i + n > lim:
            break
        i += n
    return enc[:i]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
