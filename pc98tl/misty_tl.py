"""English for Misty Blue (pc98tl/misty.py): strings.json in, patched disks out.

Strings:
* m (message): a piece of text of a bundle's record, any length: letters two a cell (half-width),
  lines broken between words at the window's edge by the engine's patched text routine; \\n a new
  line.  The same Japanese is one string everywhere.
* p (prompt): the program's and the scene modules' own texts (disk changes, saving, loading, the
  opening's credits), written in place: max_cells bytes, a letter a byte; {D} is a digit (one the
  program may fill in), kept where it was.

* t (text): a text of a program's written as it is to the text screen or DOS (disk prompts, the
  bonus game's start-up and errors), in place: max_cells letters, a letter a column.
* c (choice): a choice of one of the bonus game's menus, drawn in a box of its own: max_cells
  letters (the box's width).

The bonus game (disk B: its own MAIN.EXE and .MES scripts, pc98tl/misty_mes.py) shares the m
strings: its messages (and the names it keeps, the hero's and the monsters') too are any length,
broken between words and paged by its patched program.

A build with English rewrites the bundles on all three disks and puts the helper that draws the
letters, with the dictionary of the English's most frequent words, into each disk's MAIN.EXE
(disks A and C), and the bonus game's scripts and helper into disk B's.
"""
import json
import os
import re
import struct
import unicodedata

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import misty as M
from . import misty_mes as S
from .text import pseudo

PREFIX = {"msg": "m", "prompt": "p", "text": "t", "choice": "c"}
NOTE = {"msg": "a message: any length (lines broken between words at the window's edge); \\n a new line",
        "prompt": "a prompt of the program's, in place: max_cells letters; keep each {D} (a digit the "
                  "program fills in), in order",
        "text": "a text of the program's, in place: max_cells letters",
        "choice": "a choice of a menu, in its box: max_cells letters"}
DATA_SEG = 0x17800
DIGIT = re.compile(rb"\x82[\x4f-\x58]")
SAVED_NAME = re.compile(rb"((?:[\x81-\x98][\x40-\xfc])+)\x7d(?=\x00)")
SJIS_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){2,}")


def _paths(here, src, cfg):
    d = os.path.dirname(os.path.abspath(src))
    return [src] + [os.path.join(d, n) for n in cfg.get("disks", [])]


def prompts(seg):
    """[(start, end)] of the program's prompts in its data segment: text ended by 02, after 00 or
    02, decoding to Japanese."""
    out = []
    for m in re.finditer(rb"(?<=[\x00\x02])[\x20-\xfe]{4,}?\x02", seg):
        s, e = m.start(), m.end() - 1
        t = seg[s:e]
        try:
            if any(k == "ctl" for k, _ in M.pieces(t)):
                continue
            txt = M.show(t)
        except IndexError:
            continue
        if "�" in txt or sum(1 for c in txt if "぀" <= c <= "ヿ" or "一" <= c <= "鿿") < 3:
            continue
        out.append((s, e))
    return out


MODULE_BASE = 0x1000


def _trails(t):
    """Whether every two-byte character's second byte is a Shift-JIS one."""
    i = 0
    while i < len(t):
        b = t[i]
        if M.PAIR_LEAD <= b < 0xAB and b not in (M.NEWLINE, M.KATA, M.HIRA):
            if i + 1 >= len(t) or not (0x40 <= t[i + 1] <= 0xFC and t[i + 1] != 0x7F):
                return False
            i += 2
        else:
            i += 1
    return True


def module_texts(data):
    """[(start, end)] of the texts a scene module's code points at (the module runs at 1000h): text
    up to its 02 that reads as Japanese."""
    words = {struct.unpack_from("<H", data, k)[0] for k in range(len(data) - 1)}
    out = []
    for w in sorted(words):
        a = w - MODULE_BASE
        if not 0 < a < len(data):
            continue
        e = data.find(b"\x02", a)
        if not 8 <= e - a < 120 or out and a < out[-1][1]:
            continue
        t = data[a:e]
        try:
            if any(k == "ctl" for k, _ in M.pieces(t)):
                continue
            txt = M.show(t)
        except IndexError:
            continue
        jp = sum(1 for c in txt if "぀" <= c <= "ヿ" or "一" <= c <= "鿿")
        if ("�" in txt or jp < 4 or jp < 0.4 * len(txt.replace("　", "")) or not _trails(t)
                or re.search(r"[ゐゑ]|([^　ー…・])\1", txt)):
            continue
        out.append((a, e))
    return out


def found(vols):
    """[(ref, kind, Japanese bytes)] (refs: disk letter, file, record, piece; or disk, P, place)."""
    out = []
    for tag, vol in vols:
        for path, e in sorted(vol.walk()):
            if e["is_dir"] or not path.upper().endswith(".BUN"):
                continue
            for n, rec in enumerate(M.records(vol.read(path))):
                for k, (kind, b) in enumerate(M.pieces(rec)):
                    if kind == "text" and any(c >= 0x49 for c in b):
                        out.append(("%s:%s:%d:%d" % (tag, path, n, k), "msg", b))
        for path, e in sorted(vol.walk()):
            if e["is_dir"] or "." in path or path == "DISNO":
                continue
            data = vol.read(path)
            for a, b in module_texts(data):
                out.append(("%s:M:%s:%04x" % (tag, path, a), "prompt", data[a:b]))
            for a, b in screen_texts(data):
                out.append(("%s:V:%s:%04x" % (tag, path, a), "text", data[a:b]))
        if vol.find("MAIN.EXE") and M.PAIR_SIG.search(M.code_segment(vol.read("MAIN.EXE"))[1]):
            _p, image, _cs = M.code_segment(vol.read("MAIN.EXE"))
            seg = image[DATA_SEG:DATA_SEG + 0x10000]
            for s, e in prompts(seg):
                out.append(("%s:P:%04x" % (tag, s), "prompt", seg[s:e]))
        elif vol.find("MAIN.EXE") and S.QUOTE_SIG.search(S.code_segment(vol.read("MAIN.EXE"))[1]):
            for path, e in sorted(vol.walk()):
                if e["is_dir"] or not path.upper().endswith(".MES"):
                    continue
                data = vol.read(path)
                for s, t, kind in S.texts(data):
                    out.append(("%s:S:%s:%04x" % (tag, path, s), "choice" if kind == "choice" else "msg",
                                data[s:t]))
            for s, t, kind in engine_texts(vol.read("MAIN.EXE")):
                out.append(("%s:%s:%04x" % (tag, kind, s), "msg" if kind == "Q" else "text",
                            engine_data(vol.read("MAIN.EXE"))[s:t]))
    return out


def screen_texts(data):
    """[(start, end)] of the texts a scene module writes to the text screen (pc98tl/misty.py
    `vram_texts`): Shift-JIS up to a word 0."""
    out = []
    for _m, starts in M.vram_texts(data):
        for a in starts:
            e = a
            while e + 1 < len(data) and data[e:e + 2] != b"\0\0":
                e += 2
            if e > a and (a, e) not in out:
                out.append((a, e))
    return sorted(out)


def engine_data(exe):
    """Disk B's MAIN.EXE: its data segment (the image's 200h up to the code)."""
    _p, image, cs = S.code_segment(exe)
    return image[0x200:cs]


def engine_texts(exe):
    """[(start, end, Q or D)] of the Japanese in disk B's MAIN.EXE's data: Q a script's text (run as
    statements, followed by A6h), D a DOS string (ended by $ after it)."""
    seg = engine_data(exe)
    out = []
    for m in SJIS_RUN.finditer(seg):
        s, e = m.start(), m.end()
        try:
            txt = seg[s:e].decode("cp932")
        except UnicodeDecodeError:
            continue
        if sum(1 for c in txt if "぀" <= c <= "ヿ" or "一" <= c <= "鿿") < 3:
            continue
        out.append((s, e, "Q" if seg[e:e + 1] == b"\xa6" else "D"))
    return out


def _sjis(ref):
    """Whether the ref's text is plain Shift-JIS (the bonus game, the text screen, DOS)."""
    return ref.split(":")[1] in ("S", "V", "Q", "D")


def _show(ref, kind, b):
    if _sjis(ref):
        return S.show(b)
    if kind == "prompt":
        return re.sub("[０-９]", "{D}", M.show(b))
    return M.show(b)


def _room(ref, kind, b):
    if kind == "prompt":
        return len(b)
    if kind == "choice":
        return S.cols(b)
    if kind == "text":
        return len(b)
    return 9999


def _vols(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    imgs = [DiskImage(p) for p in _paths(here, src, cfg)]
    return cfg, imgs, list(zip("ABC", [i.volumes[0] for i in imgs]))


def run_extract(here, src):
    cfg, _imgs, vols = _vols(here, src)
    merged, order = {}, []
    for ref, kind, b in found(vols):
        jp = _show(ref, kind, b)
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], _room(ref, kind, b))
            continue
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref],
                       "max_cells": _room(ref, kind, b), "note": NOTE[kind]}
        order.append(key)
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
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"source_image_sha256": sha256(src), "strings": strings}, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def _cols(t):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


def _pseudo(e):
    if e["kind"] == "prompt":
        parts = e["jp"].split("{D}")
        return "{D}".join(pseudo(e["id"], _cols(p), 1.0)[:max(1, len(p))] for p in parts)
    return "\n".join(pseudo(e["id"], _cols(line)) for line in e["jp"].split("\n"))


def _prompt(jp_b, text):
    """A prompt's English in place: its pieces between the digits, each in its old room (a room of an
    odd length ends with a one-byte space)."""
    rooms, digits, last = [], [], 0
    for m in DIGIT.finditer(jp_b):
        rooms.append(m.start() - last)
        digits.append(m.group())
        last = m.end()
    rooms.append(len(jp_b) - last)
    parts = text.split("{D}")
    if len(parts) != len(rooms):
        raise ValueError("%d {D}, the Japanese has %d" % (len(parts) - 1, len(rooms) - 1))
    out, cut = bytearray(), False
    for n, (p, room) in enumerate(zip(parts, rooms)):
        b = M.pairs(p)
        if len(b) > room:
            b, cut = b[:room - room % 2], True
        b += M._pairs(" " * (room - len(b) - (room - len(b)) % 2))
        if len(b) < room:
            b += b"\x20"
        assert len(b) == room
        out += b
        if n < len(digits):
            out += digits[n]
    return bytes(out), cut


def run_patch(here, src, dst, mode="en"):
    cfg, imgs, vols = _vols(here, src)
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    by_ref = {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            by_ref[r] = (e, text)
    warn, bundles, proms, mods, scripts, engine = [], {}, {}, {}, {}, {}
    english = {}                    # the bonus game's English: its number in the table
    items = found(vols)
    names = {("%s:S:%s:%04x" % (tag, path, s)) for tag, vol in vols for path, e in vol.walk()
             if not e["is_dir"] and path.upper().endswith(".MES")
             for s, _t, k in S.texts(vol.read(path)) if k == "name"}
    words = M.dictionary(dict.fromkeys(by_ref[r][1] for r, k, _b in items if k == "msg" and r in by_ref
                                       and by_ref[r][1] and not _sjis(r)))
    for ref, kind, b in items:
        e, text = by_ref.get(ref, (None, ""))
        if not text:
            continue
        tag = ref.split(":")[0]
        part = ref.split(":")
        if kind in ("text", "choice"):
            room = _room(ref, kind, b)
            if len(text) > room:
                text = text[:room]
                warn.append("%s: longer than its room, cut" % e["id"])
        if part[1] in ("S", "Q"):
            n = english.setdefault(text, len(english))
        if part[1] == "S":
            s = int(part[3], 16)
            new = S.name(n) if ref in names else S.ref(n)
            scripts.setdefault((tag, part[2]), {})[s] = (s + len(b), new)
            continue
        if part[1] == "V":
            new = S.ascii_text(text) + b"\0"
            mods.setdefault((tag, part[2]), []).append((int(part[3], 16), new))
            continue
        if part[1] == "Q":
            engine.setdefault(tag, []).append((int(part[2], 16), S.ref(n, len(b))))
            continue
        if part[1] == "D":
            engine.setdefault(tag, []).append((int(part[2], 16), S.ascii_text(text).ljust(len(b), b" ")))
            continue
        if kind == "prompt":
            try:
                new, cut = _prompt(b, text)
            except ValueError as x:
                raise SystemExit("%s: %s" % (e["id"], x))
            if cut:
                warn.append("%s: longer than its room, cut" % e["id"])
            if part[1] == "M":
                mods.setdefault((tag, part[2]), []).append((int(part[3], 16), new))
            else:
                proms.setdefault(tag, []).append((int(part[2], 16), new))
            continue
        _t, path, n, k = ref.split(":")
        bundles.setdefault((tag, path), {})[(int(n), int(k))] = M.encode(text, words)
    any_en = bool(bundles or proms or mods or scripts or engine)
    by_jp = {e["jp"]: by_ref[e["refs"][0]][1] for e in doc["strings"] if e["kind"] == "msg"}
    for tag, vol in vols:
        for path, e in sorted(vol.walk()):
            if e["is_dir"] or not path.upper().startswith("FLAG"):
                continue
            # the bonus game's save: its names (32-byte buffers) as the references of their English
            data = bytearray(vol.read(path))
            for m in SAVED_NAME.finditer(bytes(data)):
                text = by_jp.get(S.show(m.group(1)), "")
                if text:
                    new = S.ref(english.setdefault(text, len(english))) + b"}"
                    data[m.start():m.start() + len(new)] = new
            vol.write(path, bytes(data))
        for path, e in sorted(vol.walk()):
            if not any_en or e["is_dir"] or "." in path or path == "DISNO":
                continue
            data = bytearray(vol.read(path))
            for a, b in mods.get((tag, path), []):
                data[a:a + len(b)] = b
            for m, _starts in M.vram_texts(bytes(data)):
                data[m.start():m.end()] = M.vram_writer(m, m.start() + MODULE_BASE)
            if data != vol.read(path):
                vol.write(path, bytes(data))
        for (t, path), new in scripts.items():
            if t != tag:
                continue
            old = vol.read(path)
            out = S.rebuild(old, new)
            if len(out) > len(old):
                raise SystemExit("%s (disk %s): %d bytes with its references, it had %d" % (
                    path, tag, len(out), len(old)))
            vol.write(path, out)
        for (t, path), new in bundles.items():
            if t != tag:
                continue
            data = vol.read(path)
            recs = []
            for n, rec in enumerate(M.records(data)):
                ps = M.pieces(rec)
                recs.append(b"".join(new.get((n, k), b) for k, (_kind, b) in enumerate(ps)))
            out = M.bundle(recs, len(data))
            if len(out) > M.BUNDLE_ROOM:
                raise SystemExit("%s (disk %s): %d bytes, the bundle's room is %d; shorten its English" % (
                    path, tag, len(out), M.BUNDLE_ROOM))
            vol.write(path, out)
        if any_en and vol.find("MAIN.EXE") and M.PAIR_SIG.search(M.code_segment(vol.read("MAIN.EXE"))[1]):
            exe = vol.read("MAIN.EXE")
            if tag in proms:
                plain, image, cs = M.code_segment(exe)
                img = bytearray(image)
                for s, b in proms[tag]:
                    img[DATA_SEG + s:DATA_SEG + s + len(b)] = b
                exe = M.exepack.pack(exe, bytes(img))
            vol.write("MAIN.EXE", M.patch_main(exe, words))
        elif any_en and vol.find("MAIN.EXE") and S.QUOTE_SIG.search(S.code_segment(vol.read("MAIN.EXE"))[1]):
            exe = vol.read("MAIN.EXE")
            if tag in engine:
                plain, image, cs = S.code_segment(exe)
                img = bytearray(image)
                for s, b in engine[tag]:
                    img[0x200 + s:0x200 + s + len(b)] = b
                exe = M.exepack.pack(exe, bytes(img))
            vol.write("MAIN.EXE", S.patch_engine(exe, list(english)))
    vols[0][1].create("MTL_NOTE.TXT", MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    stem = os.path.splitext(dst)[0]
    imgs[0].save(dst)
    for p, img in zip(_paths(here, src, cfg)[1:], imgs[1:]):
        img.save("%s - %s" % (stem, os.path.basename(p)))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
