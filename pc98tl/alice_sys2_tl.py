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

from .alice_sys2 import ADisk, Page, mblen
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
        return encode_fullwidth(s)

    def cells(self, s):
        plain = TOKEN_RE.sub("", s)
        extra = TOKEN_CELLS * len(TOKEN_RE.findall(s))
        if self.kind == "packed":
            return packfont.cells(plain) + extra
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
        return "p%02d:%04x" % (self.page.index, self.page.ops[self.start].addr)


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

    def __init__(self, vol, game_dir, adisk="ADISK.DAT", ag00="AG00.DAT", config=None):
        self.vol = vol
        self.adisk_path = game_dir + "/" + adisk
        self.ag00_path = game_dir + "/" + ag00
        self.config = dict(self.DEFAULTS)
        self.config.update(config or {})
        self.enc = Encoder(self.config["encoding"])
        self.adisk = ADisk(vol.read(self.adisk_path))
        self.pages = {i: Page(i, d) for i, d in enumerate(self.adisk.page_data) if d is not None}

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
            for b in find_blocks(page):
                jp = b.jp_text()
                widest = max(jp_cells(l.encode("cp932", "replace")) for l in jp.split("\n"))
                floor = cfg["menu_cells"] if b.kind == "menu" else cfg["msg_cells"]
                add(b.kind, jp, b.ref, max(floor, widest))
            for op in page.ops:
                if op.cmd == "M" and op.text:
                    add("name", _jp(op.text), "p%02d:%04x" % (pi, op.addr), cfg["name_bytes"] // 2)
        head, verbs, objs = parse_ag00(self.vol.read(self.ag00_path))
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
            for b in find_blocks(page):
                hit = by_ref.get(b.ref)
                if hit:
                    repl[b.start] = self._encode_block(hit[0], hit[1], report)
                    for k in range(b.start + 1, b.end):
                        repl[k] = []
            for k, op in enumerate(page.ops):
                if op.cmd == "M":
                    hit = by_ref.get("p%02d:%04x" % (i, op.addr))
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
            data = page.assemble(repl)
            if len(data) > self.config["max_page_bytes"]:
                raise ValueError("page %d is %d bytes after patching (limit %d)"
                                 % (i, len(data), self.config["max_page_bytes"]))
            new_pages.append(data)
        self.vol.write(self.adisk_path, self.adisk.build(new_pages))

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

    def _encode_block(self, e, text, report):
        if e["kind"] == "msg":
            lines = wrap(text, e["max_cells"], width=self.enc.cells)
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
        return parts or [self.enc.encode(" ")]


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
