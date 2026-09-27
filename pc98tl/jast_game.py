"""Extract/patch driver for JAST family-A games (scene files *.OVL, engine
*.EXE with the shared text interpreter).

Scene files hold text and scene code in one stream (pc98tl/jast_ovl.py).  The
patch never moves a byte: each Japanese text run is overwritten with the
engine's own goto (0B 36 <word file offset>) to its English, which is
appended at the end of the file and ends with a goto back to just after the
run.  So every offset the scene code holds stays valid, whatever the grammar
of that engine's scene code.  A file must still fit the engine's 16 KB scene
buffer.

The engine draws single-byte ASCII half-width from its own ANK font
(JAST.FNT or equivalent).  Its character check lets letters and digits into
a message but drops the punctuation 21-3F, so the patch marks those bytes
(all but "%", the name placeholder) as single-byte characters in the
engine's character class table.

English lines are padded with spaces so the engine's own wrap (at the text
window's width, a speaker's lines hanging after the colon) falls between
words.

Strings hard-coded in the engine program (menus, prompts, item names, the
bonus texts and, in some games, the opening) are rewritten in place
(pc98tl/engine_strings.py); ASCII is native there too.

game.json: {"title", "key", "image", "game_dir", "engine", "encoding": "jast",
            optional "cols" (else read from the engine), "min_run", "boot_steps"}
A string's ref is "<file>:<offset>"; kind "msg" for scene text, "engine"
(ref "EXE:<offset>" in the unpacked program) for the engine's strings.
"""
import json
import os
import re
import struct

from .disk import DiskImage
from .alice_sys2_tl import sha256
from . import exepack, engine_strings

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""

SCENE_BUFFER = 0x4000
CLASS_CHECK = re.compile(rb"\xf6[\x84-\x87](..)\x04\x75.\xf6[\x84-\x87](..)\x08\x75.\xf6[\x84-\x87](..)\x0e", re.S)
GOTO = re.compile(rb"\x05\xfd\xff\x8b\xd8\xa1(..)\x8b\x16(..)\x03\xd3", re.S)
COLON = "："


def _lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def text_runs(data, min_chars=2):
    """[(start, end)] of the Japanese text runs in a scene file: Shift-JIS
    with ASCII and %nnn inside, starting at a Shift-JIS character or a %nnn
    placeholder and ending before a control byte; at least `min_chars`
    full-width characters that decode, one of them kana or punctuation."""
    out, i, n = [], 0, len(data)
    while i < n - 1:
        b = data[i]
        if not ((_lead(b) and 0x40 <= data[i + 1] <= 0xFC and data[i + 1] != 0x7F)
                or (b == 0x25 and data[i + 1:i + 4].isdigit() and i + 4 <= n)):
            i += 1
            continue
        j, chars, last_good = i, [], i
        while j < n:
            c = data[j]
            if _lead(c) and j + 1 < n and 0x40 <= data[j + 1] <= 0xFC and data[j + 1] != 0x7F:
                chars.append(data[j:j + 2])
                j += 2
                last_good = j
            elif c == 0x25 and data[j + 1:j + 4].isdigit():
                j += 4
                last_good = j
            elif 0x20 <= c <= 0x7E or 0xA1 <= c <= 0xDF:
                j += 1              # ASCII / half-width kana inside a run
            else:
                break
        end = last_good if j < n and data[j] not in (0x00, 0x01, 0x0A) else j
        end = max(end, last_good)
        good = 0
        text = ""
        for ch in chars:
            try:
                t = ch.decode("cp932")
            except UnicodeDecodeError:
                continue
            good += 1
            text += t
        if good >= min_chars and re.search("[　-ヿ！-～]", text):
            out.append((i, end))
            i = end
        else:
            i = j if j > i else i + 1
    return out


def _decode(raw):
    out, i = [], 0
    while i < len(raw):
        b = raw[i]
        if _lead(b):
            try:
                out.append(raw[i:i + 2].decode("cp932"))
            except UnicodeDecodeError:
                out.append("{%s}" % raw[i:i + 2].hex().upper())
            i += 2
        else:
            out.append(chr(b) if b < 0x80 else bytes([b]).decode("cp932", "replace"))
            i += 1
    return "".join(out)


def _path(cfg, name):
    return (cfg["game_dir"] + "/" if cfg["game_dir"] else "") + name


def scene_files(cfg, vol):
    ents = vol.listdir(vol.find(cfg["game_dir"])["cluster"]) if cfg["game_dir"] else vol.listdir(0)
    return sorted(e["name"] for e in ents if e["name"].upper().endswith(".OVL"))


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for name in scene_files(cfg, vol):
        data = vol.read(_path(cfg, name))
        for s, e in text_runs(data, cfg.get("min_run", 2)):
            jp = _decode(data[s:e])
            ref = "%s:%x" % (name, s)
            if jp in merged:
                merged[jp]["refs"].append(ref)
                continue
            merged[jp] = {"kind": "msg", "jp": jp, "en": "", "refs": [ref]}
            order.append(jp)
    strings = [{"id": "m%05d" % i, **merged[jp]} for i, jp in enumerate(order, 1)]
    exe = vol.read(_path(cfg, cfg["engine"]))
    if exepack.is_packed(exe):
        exe = exepack.unpack(exe)
    eng = {}
    for s, e, jp in engine_strings.find(exe):
        if jp in eng:
            eng[jp]["refs"].append("EXE:%x" % s)
            continue
        eng[jp] = {"kind": "engine", "jp": jp, "en": "", "refs": ["EXE:%x" % s], "max_cells": (e - s) // 2}
    strings += [{"id": "e%05d" % i, **v} for i, v in enumerate(eng.values(), 1)]
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):  # keep translations and hand-tuned fields
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                for k in ("en", "note"):
                    if k in prev:
                        e[k] = prev[k]
    doc = {"game": cfg["title"], "source_image_sha256": sha256(src), "strings": strings}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def encode_en(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-",
             "–": "-", "…": "...", COLON: COLON}
    out = bytearray()
    for ch in text:
        ch = subst.get(ch, ch)
        if ch == COLON:
            out += ch.encode("cp932")
        elif 0x20 <= ord(ch) < 0x7F:
            out += b"%" if ch == "%" else bytes([ord(ch)])
        else:
            try:
                out += ch.encode("cp932")
            except UnicodeEncodeError:
                out += b"?"
    return bytes(out)


WRAP = re.compile(rb"\xa1(..)\xbb\x08\x00\x99\xf7\xfb\x3b\x04\x7f.", re.S)


def window_cols(exe):
    """The text window's width in columns: the value the engine stores most
    often in the variable its wrap test divides by 8."""
    from collections import Counter
    hdr = struct.unpack_from("<14H", exe, 0)
    img = bytes(exe[hdr[4] * 16:])
    m = WRAP.search(img)
    if not m:
        return None
    vals = Counter(struct.unpack("<H", x.group(1))[0]
                   for x in re.finditer(rb"\xc7\x06" + re.escape(m.group(1)) + rb"(..)", img, re.S))
    return vals.most_common(1)[0][0] // 8 if vals else None


def lay_out(text, cols):
    """A scene message laid out with the engine's new-line code (0A), so its
    own character wrap never triggers: "Name: text" (the Japanese "name:"
    layout: the name in 14 columns, the colon, the text from column 16 and
    each further line indented 16) or narration in lines of `cols`
    columns; a line break in the English starts a new line."""
    from .text import wrap
    m = re.match(r"^((?:%\d{3})|[^:：\n]{1,14})\s*[:：]\s*(.*)$", text, re.S)
    if m:
        name, body = m.group(1), m.group(2)
        head = name if name.startswith("%") else name[:14].ljust(14)
        lines = []
        for para in body.split("\n"):
            lines += wrap(para, cols - 17, width=len) or [""]
        out = encode_en(head) + COLON.encode("cp932") + encode_en(lines[0])
        for line in lines[1:]:
            out += b"\x0a" + b" " * 16 + encode_en(line)
        return out
    lines = []
    for para in text.split("\n"):
        lines += wrap(para, cols - 1, width=len) or [""]
    return b"\x0a".join(encode_en(line) for line in lines)


def patch_engine(exe):
    """Let ASCII punctuation into messages: mark 21-3F (but digits and "%")
    as single-byte characters in the engine's character class table."""
    exe = bytearray(exe)
    hdr = struct.unpack_from("<14H", exe, 0)
    base = hdr[4] * 16
    img = bytes(exe[base:])
    m = CLASS_CHECK.search(img)
    if not m:
        raise ValueError("character check not found")
    table = struct.unpack("<H", m.group(1))[0]
    # the table's segment: DGROUP, found by its shape (lead bytes 81-9F have bit 4)
    for seg in range(0, len(img) // 16):
        at = seg * 16 + table
        if at + 0x100 > len(img):
            break
        t = img[at:at + 0x100]
        if (all(t[c] & 4 for c in range(0x81, 0xA0)) and all(t[c] & 4 for c in range(0xE0, 0xF0))
                and all(t[c] & 8 for c in range(0x40, 0x7F)) and not t[0x20] & 0x0D):
            for c in range(0x21, 0x40):
                if c != 0x25 and not 0x30 <= c <= 0x39:
                    exe[base + at + c] |= 1
            return bytes(exe)
    raise ValueError("character class table not found")


def patch_scene(data, texts):
    """Overwrite text runs ({start: (end, english bytes)}) with gotos to the
    English appended at the end."""
    out = bytearray(data)
    for s, (e, en) in sorted(texts.items()):
        if e - s < 4:
            if len(en) <= e - s:
                out[s:e] = en.ljust(e - s, b" ")
            continue
        at = len(out)
        out[s:s + 4] = b"\x0b\x36" + struct.pack("<H", at)
        out += en + b"\x0b\x36" + struct.pack("<H", e)
    return bytes(out)


def relocate_scene(data, texts):
    """For engines without a goto (Marilyn DX's older interpreter, whose
    scene code holds no file offsets): replace text runs inline and move the
    word offsets in header tables 0 and 1 (entry points, blocks)."""
    from . import jast_ovl
    hdr = jast_ovl.header(data) if data[:2] != b"\x00\x00" or len(data) < 4 else jast_ovl.header(data)
    order = sorted(hdr)
    words = []
    for t, nxt in list(zip(order, order[1:] + [None]))[:2]:
        end = nxt if nxt is not None else t
        for p in range(t, end, 2):
            words.append(p)
    out, pos, shift = bytearray(), 0, []
    for s, (e, en) in sorted(texts.items()):
        out += data[pos:s] + en
        shift.append((e, len(en) - (e - s)))
        pos = e
    out += data[pos:]

    def moved(o):
        return o + sum(d for end, d in shift if end <= o)
    for p in words:
        w = struct.unpack_from("<H", data, p)[0]
        if 0 < w <= len(data):
            struct.pack_into("<H", out, p, moved(w))
    return bytes(out)


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    exe_path = _path(cfg, cfg["engine"])
    exe = vol.read(exe_path)
    if exepack.is_packed(exe):
        exe = exepack.unpack(exe)
    cols = cfg.get("cols") or window_cols(exe) or 60
    by_ref = {}
    for e in doc["strings"]:
        text = e["en"]
        if mode == "pseudo":
            jp = e["jp"]
            m = re.match(r"^([^0-9０-９【】「」]{1,8}?)：", jp)
            body = pseudo(e["id"], int(len(jp) * 2))
            text = (m.group(1) + ": " + body) if m else body
            if e["kind"] == "engine":      # filler as long as the string's room
                text = pseudo(e["id"], 2 * e["max_cells"], 1.0)[:2 * e["max_cells"]]
        if not text:
            continue
        if e["kind"] == "engine":
            room = 2 * e["max_cells"]
            laid = lay_out(text, cols)
            val = laid if len(laid) <= room else encode_en(text)
            for r in e["refs"]:
                by_ref[r] = val
            continue
        for r in e["refs"]:
            by_ref[r] = lay_out(text, cols)
    report = []
    for name in scene_files(cfg, vol):
        data = vol.read(_path(cfg, name))
        texts = {}
        for s, e in text_runs(data, cfg.get("min_run", 2)):
            en = by_ref.get("%s:%x" % (name, s))
            if en is not None:
                texts[s] = (e, en)
        if not texts:
            continue
        new = relocate_scene(data, texts) if cfg.get("relocate") else patch_scene(data, texts)
        if len(new) > SCENE_BUFFER:
            report.append("%s: %d bytes, the scene buffer holds %d (left in Japanese)"
                          % (name, len(new), SCENE_BUFFER))
            continue
        vol.write(_path(cfg, name), new)
    runs = engine_strings.find(exe)
    exe, cut = engine_strings.apply(exe, runs, {s: by_ref["EXE:%x" % s] for s, _e, _t in runs
                                               if "EXE:%x" % s in by_ref})
    ids = {r: e["id"] for e in doc["strings"] for r in e["refs"]}
    for s, need, room in cut:
        report.append("%s: %d bytes, room for %d (cut)" % (ids.get("EXE:%x" % s, "EXE:%x" % s), need, room))
    vol.write(exe_path, patch_engine(exe))
    vol.create(_path(cfg, "MTL_NOTE.TXT"),
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    img.save(dst)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
    for line in report:
        print("  " + line)
