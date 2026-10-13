"""English for PP Disk (pc98tl/ppdisk.py): strings.json in, a patched hard-disk image out.

The floppies have no room for the English, so the patch lays them out on a DOS hard disk the way
the other floppy games here are (game.json "hdd", pc98tl/illusion_game.py): Disk A in the install
directory, Disk B in a folder of it (game.json "folders"), started one after the other.

Strings (refs DISK:FILE@offset; PPDISK.EXE's, the same program on both disks, PPDISK.EXE@offset):

* "article": a record of PPDISK.TXT shown in the menus' box (refs X:PPDISK.TXT@offset): its lines,
  `\\n` between them.  Each line is wrapped between words to `max_cells` (46), 8 lines to a page.
* "page": a record shown on the whole screen (a list's pages, the replay mode's help): the same,
  80 letters to a line, 24 lines to a page.
  A record may take 32255 bytes (a letter a byte, and one for each line's end), 256 pages; a build
  past either is refused and names it.
* "title": a menu's title (refs X:PPDISK.SCR@pool offset), one line, `max_cells` 36 (the title box);
  "menu": a menu's item, one line, `max_cells` 46 (the menu's box), or 36 when it is also a title.
* "balloon": one of Pia's speech balloons (refs X:balloon<n>): wrapped to 16 letters, 6 lines at
  most (the balloon's six slots); past them the build is refused.
* "engine": a program's message (refs PPDISK.EXE@offset, B:PPCOPY.EXE@offset), in its own bytes:
  `max_cells` its room; past it the English is cut and reported.  `{S1}` / `{N1}` stand for the
  name / number the program puts in (printf's %s / %d); a message ending in a line break keeps it.
* "install": the text PPCOPY.EXE shows before it installs the REIRA demo (refs B:PPCOPY.CMD), lines
  of up to 78 letters, wrapped between words.

English is ASCII (half-width); another character is written in Shift-JIS when it has it (two
cells, full-width), else as `?`.
"""
import json
import os
import re
import struct

from . import ai5, ppdisk
from .alice_sys2_tl import sha256
from .text import pseudo, sjis_cols

PREFIX = {"article": "a", "page": "p", "title": "t", "menu": "m", "balloon": "b", "engine": "e",
          "install": "i"}
SUBST = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "♥": "<3"}
KANA = re.compile(r"[ぁ-ヾ]")
INSTALL_CELLS = 78
INSTALL_ROWS = 23                 # the text screen's 25 rows, less PPCOPY's own line and the cursor's
TOKENS = (("%s", "{S1}"), ("%d", "{N1}"))
EXES = ("PPDISK.EXE", "PPCOPY.EXE")
DEMO = {"msg": "demo", "item": "demo_item", "label": "demo_label"}
PREFIX.update({"demo": "dm", "demo_item": "di", "demo_label": "dl"})


def _demo(cfg, game_dir):
    """The demo's config for the AI5 driver (game.json "demo", its files in game_dir)."""
    demo = dict(cfg["demo"], game_dir=game_dir)
    ai5.set_calls(demo)
    ai5.set_engine(demo)
    return demo


def decode(raw):
    return raw.decode("cp932", "replace")


def encode(text):
    out = bytearray()
    for c in "".join(SUBST.get(c, c) for c in text):
        if 0x20 <= ord(c) < 0x7F:
            out.append(ord(c))
        else:
            try:
                b = c.encode("cp932")
            except UnicodeEncodeError:
                b = b"?"
            out += b if len(b) == 2 else b"?"
    return bytes(out)


def wrap(text, width):
    """Lines of at most width cells, broken between words; a line's leading spaces are kept."""
    def cols(t):
        return sjis_cols(encode(t))
    out = []
    for para in text.split("\n"):
        line = para[:len(para) - len(para.lstrip(" "))]
        for w in para.split():
            cand = line + w if not line.strip() else line + " " + w
            if cols(cand) <= width:
                line = cand
                continue
            if line.strip():
                out.append(line.rstrip())
            line = w
            while cols(line) > width:
                cut = width
                while cols(line[:cut]) > width:
                    cut -= 1
                out.append(line[:cut])
                line = line[cut:]
        out.append(line.rstrip())
    return out


def _disk(cfg, src, letter):
    from .disk import DiskImage
    if letter == "A":
        return DiskImage(src).volumes[0]
    return DiskImage(os.path.join(os.path.dirname(src), cfg["hdd"]["disks"][0])).volumes[0]


def _data_seg(exe):
    """The program's data segment (Microsoft C's startup: mov di, DGROUP; mov si, [2])."""
    hdr = struct.unpack_from("<H", exe, 8)[0] * 16
    ip, cs = struct.unpack_from("<HH", exe, 0x14)
    m = re.search(rb"\xbf(..)\x8b\x36\x02\x00", exe[hdr + cs * 16 + ip:hdr + cs * 16 + ip + 0x40], re.S)
    if not m:
        raise SystemExit("a program's startup not recognised")
    return hdr, struct.unpack("<H", m.group(1))[0] * 16


def _exe_strings(exe):
    """[(file offset, bytes)]: the Japanese messages in a program's data segment that its code names
    (a run of text whose start, or a place in it before its first Japanese, is an immediate operand),
    each NUL-ended."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    hdr, ds = _data_seg(exe)
    named = set()
    for i in Cs(CS_ARCH_X86, CS_MODE_16).disasm(exe[hdr:hdr + ds], 0):
        named.update(int(v, 16) for v in re.findall(r"0x([0-9a-f]+)", i.op_str))
    out = []
    data = exe[hdr + ds:]
    for m in re.finditer(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e\xa1-\xdf\n])+\x00", data):
        raw = m.group()[:-1]
        try:
            t = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        # (Japanese words: two kana at least (the pictures' signature, half-width, is not one); not the
        # version's what-string)
        if len(KANA.findall(t)) < 2 or t.startswith("@(#)"):
            continue
        first = m.start() + next(k for k, c in enumerate(raw) if c >= 0x80)
        at = [a for a in named if m.start() <= a <= first]
        if at:
            s = max(at)
            out.append((hdr + ds + s, data[s:m.end() - 1]))
    return out


def _exe_jp(raw):
    t = decode(raw)
    for a, b in TOKENS:
        t = t.replace(a, b)
    return t[:-1] if t.endswith("\n") else t


def _block(cmd):
    """PPCOPY.CMD's text: (start, end) of the lines between TEXT and END."""
    s = cmd.index(b"TEXT\r\n") + 6
    return s, cmd.index(b"\r\nEND", s) + 2


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    merged, order = {}, []

    def add(kind, jp, ref, cells, note=None):
        key = (kind, jp)
        if key in merged:
            if ref not in merged[key]["refs"]:
                merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], cells)
            return
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": cells}
        if note:
            merged[key]["note"] = note
        order.append(key)
    for letter in "AB":
        vol = _disk(cfg, src, letter)
        scr, txt = vol.read("PPDISK.SCR"), vol.read("PPDISK.TXT")
        view = ppdisk.viewers(scr, txt)
        for off, rec in ppdisk.records(txt):
            kind = view[off]
            jp = "\n".join(decode(ln) for ln in ppdisk.lines(rec))
            add(kind, jp, "%s:PPDISK.TXT@%x" % (letter, off),
                (ppdisk.ARTICLE if kind == "article" else ppdisk.PAGE)[0],
                None if off else "the replay mode's help")
        pool = ppdisk.pool_strings(scr)
        titles = set()
        for m, b, items in ppdisk.menus(scr):
            titles.add(ppdisk.word(scr, b))
        for m, b, items in ppdisk.menus(scr):
            for off in [ppdisk.word(scr, b)] + [ppdisk.word(scr, lp) for k, lp, t, ap in items]:
                if off < 0:
                    continue
                kind = "title" if off in titles else "menu"
                add(kind, decode(pool[off]), "%s:PPDISK.SCR@%x" % (letter, off),
                    ppdisk.TITLE_CELLS if off in titles else ppdisk.LABEL_CELLS,
                    "also a menu's item" if kind == "title" and any(
                        ppdisk.word(scr, lp) == off for mm, bb, it in ppdisk.menus(scr) for k, lp, t, ap in it)
                    else None)
        for n, bl in enumerate(ppdisk.balloons(scr)):
            offs = [ppdisk.word(scr, p) for p in bl]
            if all(o < 0 for o in offs):
                continue
            add("balloon", "\n".join(decode(pool[o]) for o in offs if o >= 0), "%s:balloon%d" % (letter, n),
                ppdisk.BALLOON[0])
        for name in EXES:
            if name == "PPCOPY.EXE" and letter == "A":
                continue
            if name == "PPDISK.EXE" and letter == "B":
                continue
            exe = vol.read(name)
            for off, raw in _exe_strings(exe):
                ref = "%s@%x" % (name, off) if name == "PPDISK.EXE" else "%s:%s@%x" % (letter, name, off)
                add("engine", _exe_jp(raw), ref, len(raw) - raw.endswith(b"\n"))
        if letter == "B":
            cmd = vol.read("PPCOPY.CMD")
            s, e = _block(cmd)
            jp = "\n".join(decode(ln).expandtabs(8).rstrip() for ln in cmd[s:e].split(b"\r\n")[:-1])
            add("install", jp, "B:PPCOPY.CMD", INSTALL_CELLS)
        if letter == cfg["demo"]["disk"]:
            demo = _demo(cfg, "")
            for kind, jp, ref, cells, note in ai5.script_strings(vol, demo, demo):
                add(DEMO[kind], jp, "%s:%s" % (letter, ref), cells, note)
    if _disk(cfg, src, "A").read("PPDISK.EXE") != _disk(cfg, src, "B").read("PPDISK.EXE"):
        raise SystemExit("the disks' PPDISK.EXE differ")
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
    if k in ("article", "page", "install"):
        return "\n".join(pseudo("%s.%d" % (e["id"], n), sjis_cols(encode(ln))) if ln.strip() else ""
                         for n, ln in enumerate(e["jp"].split("\n")))
    if k.startswith("demo"):
        return ai5.pseudo_text(e)
    if k == "balloon":
        lines = wrap(pseudo(e["id"], 2 * sjis_cols(encode(e["jp"]))), ppdisk.BALLOON[0])
        return " ".join(lines[:ppdisk.BALLOON[1]])
    return pseudo(e["id"], 2 * e["max_cells"], 1.0)[:e["max_cells"]]


def _text(text, width, limit, name, ident):
    """A record's bytes: its English wrapped, each line NUL-ended."""
    lines = wrap(text, width)
    rec = b"".join(encode(ln) + b"\x00" for ln in lines)
    if len(rec) > ppdisk.RECORD_MAX:
        raise SystemExit("%s: %d bytes in %s, a record may take %d" % (ident, len(rec), name, ppdisk.RECORD_MAX))
    if len(lines) > 256 * limit:
        raise SystemExit("%s: %d lines in %s, 256 pages of %d at most" % (ident, len(lines), name, limit))
    return rec


def _exe_text(text, raw, room, ident, warn):
    for a, b in TOKENS:
        text = text.replace(b, a) if a in decode(raw) else text
    b = encode(text)
    if len(b) > room:
        warn.append("%s: cut to its room (%d bytes)" % (ident, room))
        b = b[:room]
    if raw.endswith(b"\n"):
        b += b"\n"
    return b + bytes(len(raw) - len(b))


def _has(vol, path):
    try:
        vol.find(path)
        return True
    except FileNotFoundError:
        return False


def run_patch(here, src, dst, mode="en"):
    from .illusion_game import _hdd_install
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img, _ = _hdd_install(cfg, src)
    vol = img.volumes[0]
    by_ref, ids = {}, {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            ids[r] = e["id"]
            if text:
                by_ref[r] = text
    warn = []
    for letter, folder in cfg["folders"].items():
        path = lambda n: folder + "/" + n  # noqa: E731
        scr, txt = bytearray(vol.read(path("PPDISK.SCR"))), vol.read(path("PPDISK.TXT"))
        view = ppdisk.viewers(bytes(scr), txt)
        # the text, re-laid; the menus' offsets of it rewritten
        new, moved = bytearray(), {}
        for off, rec in ppdisk.records(txt):
            ref = "%s:PPDISK.TXT@%x" % (letter, off)
            if ref in by_ref:
                w, lim = ppdisk.ARTICLE if view[off] == "article" else ppdisk.PAGE
                rec = _text(by_ref[ref], w, lim, "%s's PPDISK.TXT" % letter, ids[ref])
            moved[off] = len(new)
            new += struct.pack("<H", len(rec)) + rec
        for pos, v in ppdisk.txt_fields(bytes(scr)):
            struct.pack_into("<I", scr, pos, moved[struct.unpack_from("<I", scr, pos)[0]])
        vol.write(path("PPDISK.TXT"), bytes(new))
        # the menus' strings: in their own bytes, or at the pool's end
        po, pn = ppdisk.sections(bytes(scr))["pool"]
        pool = bytearray(scr[po:])
        heads = [b for m, b, items in ppdisk.menus(bytes(scr))]
        labels = [lp for m, b, items in ppdisk.menus(bytes(scr)) for k, lp, t, ap in items]
        for off, raw in ppdisk.pool_strings(bytes(scr)).items():
            ref = "%s:PPDISK.SCR@%x" % (letter, off)
            if ref not in by_ref:
                continue
            b = encode(by_ref[ref])
            cells = ppdisk.TITLE_CELLS if any(ppdisk.word(scr, h) == off for h in heads) else ppdisk.LABEL_CELLS
            if sjis_cols(b) > cells:
                warn.append("%s: %d letters, past its box (%d)" % (ids[ref], sjis_cols(b), cells))
            if len(b) <= len(raw):
                pool[off:off + len(raw)] = b + bytes(len(raw) - len(b))
                continue
            at = len(pool)
            pool += b + b"\x00"
            for p in heads + labels:
                if ppdisk.word(scr, p) == off:
                    struct.pack_into("<H", scr, p, at)
        for n, bl in enumerate(ppdisk.balloons(bytes(scr))):
            ref = "%s:balloon%d" % (letter, n)
            if ref not in by_ref:
                continue
            lines = wrap(by_ref[ref], ppdisk.BALLOON[0])
            if len(lines) > ppdisk.BALLOON[1]:
                raise SystemExit("%s: %d lines, a balloon has %d" % (ids[ref], len(lines), ppdisk.BALLOON[1]))
            for k, p in enumerate(bl):
                if k < len(lines):
                    b = encode(lines[k]) + b"\x00"
                    at = pool.find(b"\x00" + b) + 1 if pool.find(b"\x00" + b) >= 0 else -1
                    if at <= 0:
                        at = len(pool)
                        pool += b
                    struct.pack_into("<H", scr, p, at)
                else:
                    struct.pack_into("<h", scr, p, -1)
        if len(pool) > 0xFFF0:
            raise SystemExit("%s's PPDISK.SCR: its strings take %d bytes, 65520 at most" % (letter, len(pool)))
        struct.pack_into("<H", scr, 0x12, len(pool))
        vol.write(path("PPDISK.SCR"), bytes(scr[:po]) + bytes(pool))
        # the programs
        for name in EXES:
            if not _has(vol, path(name)):
                continue
            exe = bytearray(vol.read(path(name)))
            for off, raw in _exe_strings(bytes(exe)):
                ref = "%s@%x" % (name, off) if name == "PPDISK.EXE" else "%s:%s@%x" % (letter, name, off)
                if ref in by_ref:
                    exe[off:off + len(raw)] = _exe_text(by_ref[ref], raw, len(raw) - raw.endswith(b"\n"),
                                                        ids[ref], warn)
            if name == "PPDISK.EXE":
                exe = bytearray(ppdisk.patch_exe(bytes(exe)))
            vol.write(path(name), bytes(exe))
        if _has(vol, path("PPCOPY.CMD")) and "%s:PPCOPY.CMD" % letter in by_ref:
            ref = "%s:PPCOPY.CMD" % letter
            cmd = vol.read(path("PPCOPY.CMD"))
            s, e = _block(cmd)
            lines = wrap(by_ref[ref], INSTALL_CELLS)
            if len(lines) > INSTALL_ROWS:
                warn.append("%s: %d lines, the screen shows %d (the first scroll off)" % (
                    ids[ref], len(lines), INSTALL_ROWS))
            vol.write(path("PPCOPY.CMD"), cmd[:s] + b"".join(encode(ln) + b"\r\n" for ln in lines) + cmd[e:])
    # the demo's scripts (the AI5 driver)
    letter = cfg["demo"]["disk"]
    demo = _demo(cfg, cfg["folders"][letter])
    d_ref, d_ids = {}, {}
    for e in doc["strings"]:
        if not e["kind"].startswith("demo"):
            continue
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            f, a = r[len(letter) + 1:].rsplit(":", 1)
            d_ids[(f, int(a, 16))] = e["id"]
            if text:
                d_ref[(f, int(a, 16))] = text
    ai5.patch_scripts(vol, demo, demo, d_ref, d_ids, warn, mode)
    for w in sorted(set(warn)):
        print("warning:", w)
    img.save(dst)
    print("wrote", dst)
