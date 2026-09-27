"""JAST family-B games (scene files *.SCM, message files *.MSG / *.MLO,
engine TEN6.EXE and relatives): extract/patch driver.

A scene file starts with command tables (small indices, FF-padded), then the
messages, each ended by 00 00; the engine finds a message by counting, so
messages may change length.  (Tenshi-tachi no Gogo VI; the others of the
family are checked per game.)

The engine reads text two bytes at a time as Shift-JIS and draws each
character from the kanji ROM through one glyph routine (Shift-JIS to JIS,
16x16 fetch into a buffer, draw).  The patch rewrites that routine's fetch:
a code whose first byte is below 80 (the routine gets it in AL) is two ASCII letters, drawn as the kanji
ROM's two 8x16 ANK glyphs side by side in the one cell.  So English is plain
ASCII, two letters per cell; untranslated Japanese draws as before.

game.json: {"title", "key", "image", "game_dir", "engine", "encoding": "jast_scm",
            "cols" (the text window's width in half-width columns), "dgroup" and
            "pointers" (two DGROUP offsets that stay zero, for the far pointer),
            "boot_steps", "dipsw", optional "native_ascii": true (engines that
            draw ASCII half-width themselves, on the text layer: no engine
            patch), "floppies": {"B": "<other disk image>", ...}}
A string's ref is "<file>:<message number>"; the engine program's own
strings (menus, disk prompts, help) are kind "engine", ref "EXE:<offset>",
rewritten in place (pc98tl/engine_strings.py) as ASCII (letter pairs in the
kanji-ROM builds, whose glyph routine draws them).  The noun table
NTBL.BIN (the objects of the LOOK/SPEAK/ACTION menus: 256 records of 16
bytes and a NUL) is kind "word", ref "NTBL:<record>", rewritten in place on
every disk that has it; batch files' Japanese echo lines are kind "batch",
ref "<file>:<line>".
"""

NTBL = "NTBL.BIN"
NTBL_REC = 17
import json
import os
import re
import struct

from .disk import DiskImage
from .alice_sys2_tl import sha256
from . import engine_strings

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""

# the glyph routine's fetch: code at [bp+4] -> JIS -> ports A1/A3 ... rows into
# a 32-byte buffer ... "mov al, 0A; out 68h, al"
FETCH = re.compile(rb"\xb0\x0b\xe6\x68(\x8b\x46\x04\x86\xe0\xd0\xe4\x2c\x1f\x78\x04\x3c\x61\x14\xde"
                   rb"\x05\xa1\x1f\x25\x7f\x7f\x80\xec\x20\xe6\xa1\x86\xe0\xe6\xa3.*?\xbf(..).*?)"
                   rb"\xb0\x0a\xe6\x68", re.S)


def _path(cfg, name):
    return (cfg["game_dir"] + "/" if cfg["game_dir"] else "") + name


def _clean(piece):
    """Pure message text: Shift-JIS, ASCII, half-width kana, 01 (a speaker
    line) and 0A (a new page)."""
    i = 0
    while i < len(piece):
        b = piece[i]
        if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF:
            if i + 1 >= len(piece) or not 0x40 <= piece[i + 1] <= 0xFC:
                return False
            i += 2
        elif 0x20 <= b <= 0x7E or 0xA1 <= b <= 0xDF or b in (0x01, 0x0A):
            i += 1
        else:
            return False
    return True


def text_start(data):
    """Where the messages begin: the first position just after a table byte
    (FF or a control value) whose 00 00-ended piece is message text with a
    Shift-JIS character in it."""
    cands = [0] + [i + 1 for i, b in enumerate(data) if b == 0xFF or (b < 0x20 and b not in (0x01, 0x0A))]
    for p in cands:
        e = data.find(b"\x00\x00", p)
        if e <= p:
            continue
        piece = data[p:e]
        if _clean(piece) and re.search(rb"[\x81-\x9f\xe0-\xef][\x40-\xfc]", piece):
            return p
    return len(data)


def messages(data):
    """[(number, start, end)]: the pieces after the tables, each ended by
    00 00, numbered by position; only pieces of pure message text are
    listed (a few files keep command tables between their messages, which
    are left alone)."""
    out, i, n = [], text_start(data), 0
    while i < len(data):
        e = data.find(b"\x00\x00", i)
        if e < 0:
            break
        piece = data[i:e]
        if piece and _clean(piece):
            out.append((n, i, e))
        n += 1
        i = e + 2
    return out


def scene_files(cfg, vol):
    ents = vol.listdir(vol.find(cfg["game_dir"])["cluster"]) if cfg["game_dir"] else vol.listdir(0)
    return sorted(e["name"] for e in ents if e["name"].upper().endswith(".SCM"))


def disks(cfg, src):
    """[(tag, image, volume)]: the source image (tag "") and, for floppy
    sets, the other disks named in game.json "floppies" (next to the source;
    tag = their key, e.g. "B").  Every disk's scene files are patched: the
    engine loads a scene from whichever disk is in the drive."""
    if cfg.get("hdd"):   # floppies too full for English: the hard-disk layout
        from .illusion_game import _hdd_install
        img, hcfg = _hdd_install(cfg, src)
        cfg["game_dir"] = hcfg["game_dir"]
        return [("", img, img.volumes[0])]
    img = DiskImage(src)
    out = [("", img, img.volumes[0])]
    for tag, name in cfg.get("floppies", {}).items():
        other = DiskImage(os.path.join(os.path.dirname(src), name))
        out.append((tag, other, other.volumes[0]))
    return out


def _exists(vol, path):
    try:
        vol.read(path)
        return True
    except Exception:
        return False


def batch_files(cfg, vol):
    ents = vol.listdir(vol.find(cfg["game_dir"])["cluster"]) if cfg["game_dir"] else vol.listdir(0)
    return sorted(e["name"] for e in ents if e["name"].upper().endswith(".BAT"))


def _ref(tag, name, num):
    return ("%s/%s:%d" % (tag, name, num)) if tag else ("%s:%d" % (name, num))


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    merged, order = {}, []
    all_disks = disks(cfg, src)
    for tag, _img, vol in all_disks:
      for name in scene_files(cfg, vol):
        data = vol.read(_path(cfg, name))
        for num, s, e in messages(data):
            pages = data[s:e].split(b"\x0a")
            speaker = [k for k, pg in enumerate(pages) if pg[:1] == b"\x01"]
            jp = "\n".join(pg.lstrip(b"\x01").decode("cp932", "replace") for pg in pages)
            if not jp.strip():
                continue
            ref = _ref(tag, name, num)
            if jp in merged:
                merged[jp]["refs"].append(ref)
                continue
            merged[jp] = {"kind": "msg", "jp": jp, "en": "", "refs": [ref], "speaker_pages": speaker}
            order.append(jp)
    strings = [{"id": "m%05d" % i, **merged[jp]} for i, jp in enumerate(order, 1)]
    exe = all_disks[0][2].read(_path(cfg, cfg["engine"]))
    eng = {}
    for s, e, jp in engine_strings.find(exe):
        if jp in eng:
            eng[jp]["refs"].append("EXE:%x" % s)
            continue
        eng[jp] = {"kind": "engine", "jp": jp, "en": "", "refs": ["EXE:%x" % s], "max_cells": (e - s) // 2}
    strings += [{"id": "e%05d" % i, **v} for i, v in enumerate(eng.values(), 1)]
    vol0 = all_disks[0][2]
    words, bats = {}, {}
    if _exists(vol0, _path(cfg, NTBL)):
        table = vol0.read(_path(cfg, NTBL))
        for k in range(len(table) // NTBL_REC):
            jp = table[k * NTBL_REC:k * NTBL_REC + 16].decode("cp932", "replace").rstrip("\u3000 ")
            if jp:
                words.setdefault(jp, {"kind": "word", "jp": jp, "en": "", "refs": [], "max_cells": 8})
                words[jp]["refs"].append("NTBL:%d" % k)
    for name in batch_files(cfg, vol0):
        for n, jp in engine_strings.batch_lines(vol0.read(_path(cfg, name))):
            bats.setdefault(jp, {"kind": "batch", "jp": jp, "en": "", "refs": []})
            bats[jp]["refs"].append("%s:%d" % (name, n))
    strings += [{"id": "w%05d" % i, **v} for i, v in enumerate(words.values(), 1)]
    strings += [{"id": "b%05d" % i, **v} for i, v in enumerate(bats.values(), 1)]
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):
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


def patch_engine(exe, dgroup, pointers):
    """Rewrite the glyph fetch: Shift-JIS codes as before; a code whose first
    byte is below 80 goes to a far routine (in a DOS block from
    illusion_font's entry stub, reached through a pointer in DGROUP bytes
    that stay zero) that fetches the two ANK letters side by side."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm, _entry_stub
    exe = bytearray(exe)
    base = struct.unpack_from("<H", exe, 8)[0] * 16
    img = bytes(exe[base:])
    m = FETCH.search(img)
    if not m:
        raise ValueError("glyph fetch not found")
    buf = struct.unpack("<H", m.group(2))[0]
    start, end = m.start(1), m.end(1)
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    near = """
        mov ax, word ptr [bp + 4]
        push ds
        pop es
        mov di, {buf}
        test al, 0x80
        jnz sj
        .byte 0xff, 0x1e
        .word {ptr}
        jmp done
    sj:
        xchg al, ah
        shl ah, 1
        sub al, 0x1f
        js j1
        cmp al, 0x61
        adc al, 0xde
    j1:
        add ax, 0x1fa1
        and ax, 0x7f7f
        sub ah, 0x20
        out 0xa1, al
        xchg al, ah
        out 0xa3, al
        xor cx, cx
    r1:
        mov al, cl
        or al, 0x20
        out 0xa5, al
        in al, 0xa9
        stosb
        mov al, cl
        out 0xa5, al
        in al, 0xa9
        stosb
        inc cx
        cmp cx, 16
        jne r1
    done:
    """.format(buf=buf, ptr=pointers[0])
    code = bytes(ks.asm(near, base + start)[0])
    if len(code) > end - start:
        raise ValueError("rewritten fetch is %d bytes, room for %d" % (len(code), end - start))
    exe[base + start:base + end] = code.ljust(end - start, b"\x90")
    far = """
        .word 0, 0, 0, 0, 0
    ank:
        push bx
        push cx
        mov bx, ax
        xor al, al
        out 0xa1, al
        mov al, bl
        out 0xa3, al
        xor cx, cx
    h1:
        mov al, cl
        or al, 0x20
        out 0xa5, al
        in al, 0xa9
        stosb
        inc di
        inc cx
        cmp cx, 16
        jne h1
        sub di, 31
        xor al, al
        out 0xa1, al
        mov al, bh
        out 0xa3, al
        xor cx, cx
    h2:
        mov al, cl
        or al, 0x20
        out 0xa5, al
        in al, 0xa9
        stosb
        inc di
        inc cx
        cmp cx, 16
        jne h2
        pop cx
        pop bx
        .byte 0xcb
    unused:
        .byte 0xcb
    finish:
        mov es, word ptr cs:[6]
        xor di, di
        mov cx, word ptr cs:[8]
        xor al, al
        cld
        rep stosb
        pop es
        pop ds
        pop bp
        pop di
        pop si
        pop dx
        pop cx
        pop bx
        pop ax
        .byte 0x2e, 0xff, 0x2e
        .word 2
    """
    blob, labels = _asm(ks, far, 0, ("ank", "unused", "finish"))
    labels = {"head_far": labels["ank"], "common_far": labels["unused"], "finish": labels["finish"]}
    _entry_stub(ks, exe, blob, labels, dgroup, pointers[0], pointers[1])
    return bytes(exe)


def encode_en(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-",
             "–": "-", "…": "..."}
    s = "".join(subst.get(c, c) for c in text)
    s = "".join(c if 0x20 <= ord(c) < 0x7F else "?" for c in s)
    if len(s) % 2:
        s += " "
    return s.encode("ascii")


def lay_out(text, cols, box_lines, speaker_pages=()):
    """For the kanji-ROM engines (Tenshi VI, Special II): one stream of lines
    word-wrapped to the window and padded to its full width, so the engine's
    own cell wrap lands between words; the engine pages a full box itself
    (waits for a click, clears).  Its 0A doesn't break a line, so the
    English uses none; each Japanese page starts on a new line."""
    from .text import wrap
    lines = []
    for page in text.split("\n"):
        # words stop two columns short of the edge (a letter in the last
        # column can be lost where the portrait panel meets the box)
        lines += wrap(page, cols - 2, width=len) or [""]
    body = "".join(ln.ljust(cols) if j < len(lines) - 1 else ln for j, ln in enumerate(lines))
    return encode_en(body)


def lay_out_lines(text, cols, box_lines, speaker_pages=()):
    """For the text-layer engines (native ASCII): every line ends with the
    engine's newline 0A and a Japanese page's first line keeps its speaker
    code 01; a message longer than the box pages through the console pager
    (pc98tl/jast_console.py)."""
    from .text import wrap
    lines = []
    for k, page in enumerate(text.split("\n")):
        for j, ln in enumerate(wrap(page, cols - 1, width=len) or [""]):
            lines.append((b"\x01" if (j == 0 and k in speaker_pages) else b"") + encode_en(ln).rstrip(b" "))
    return b"\x0a".join(lines)


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    cols = cfg.get("cols", 60)
    by_ref, eng = {}, {}
    for e in doc["strings"]:
        if mode == "pseudo":
            text = "\n".join(pseudo("%s.%d" % (e["id"], k), int(len(pg) * 2.5))
                             for k, pg in enumerate(e["jp"].split("\n")))
            if e["kind"] == "engine":      # filler as long as the string's room
                text = pseudo(e["id"], 2 * e["max_cells"], 1.0)[:2 * e["max_cells"]]
        else:
            text = e["en"]
        if text and e["kind"] == "engine":
            for r in e["refs"]:
                eng[r] = encode_en(text)
            continue
        if mode == "pseudo" and e["kind"] == "word":
            text = ("<%s>" % e["id"][1:])[:16]
        if text and e["kind"] in ("word", "batch"):
            for r in e["refs"]:
                eng[r] = text
            continue
        if text:
            for r in e["refs"]:
                by_ref[r] = (lay_out_lines if cfg.get("native_ascii") else lay_out)(
                    text, cols, cfg.get("box_lines", 3), e.get("speaker_pages", ()))
    all_disks = disks(cfg, src)
    for tag, _img, vol in all_disks:
      for name in scene_files(cfg, vol):
        data = vol.read(_path(cfg, name))
        out, pos, changed = bytearray(), 0, False
        for num, s, e in messages(data):
            en = by_ref.get(_ref(tag, name, num))
            if en is None:
                continue
            out += data[pos:s] + en
            pos = e
            changed = True
        if changed:
            out += data[pos:]
            vol.write(_path(cfg, name), bytes(out))
    for tag, _img, vol in all_disks:
        if _exists(vol, _path(cfg, NTBL)):
            table = bytearray(vol.read(_path(cfg, NTBL)))
            for k in range(len(table) // NTBL_REC):
                v = eng.get("NTBL:%d" % k)
                if v is not None:
                    b = encode_en(v)
                    if len(b) > 16:
                        print("warning: NTBL:%d: %d letters, the menu shows 16" % (k, len(b)))
                        b = b[:16]
                    table[k * NTBL_REC:k * NTBL_REC + 16] = b.ljust(16, b" ")
            vol.write(_path(cfg, NTBL), bytes(table))
        for name in batch_files(cfg, vol):
            data = vol.read(_path(cfg, name))
            lines = {n: eng["%s:%d" % (name, n)] for n, _t in engine_strings.batch_lines(data)
                     if "%s:%d" % (name, n) in eng}
            if lines:
                vol.write(_path(cfg, name), engine_strings.apply_batch(data, lines))
    tag, img, vol = all_disks[0]
    exe_path = _path(cfg, cfg["engine"])
    if cfg.get("one_drive"):
        # hard-disk layout for an engine without a hard-disk mode: its
        # "select disk" (DOS function 0E, drive from the argument) always
        # selects drive A, the hard disk, whose current directory holds
        # every disk's files
        exe = bytearray(vol.read(exe_path))
        sel = bytes.fromhex("b40e8a5604cd21")
        at = bytes(exe).find(sel)
        if at < 0 or bytes(exe).find(sel, at + 1) >= 0:
            raise ValueError("select-disk call not found (or not unique)")
        exe[at + 2:at + 5] = bytes.fromhex("b20090")
        vol.write(exe_path, bytes(exe))
    runs = engine_strings.find(vol.read(exe_path))
    exe, cut = engine_strings.apply(vol.read(exe_path), runs,
                                    {s: eng["EXE:%x" % s] for s, _e, _t in runs if "EXE:%x" % s in eng})
    vol.write(exe_path, exe)
    ids = {r: e["id"] for e in doc["strings"] for r in e["refs"]}
    for s, need, room in cut:
        print("warning: %s: %d bytes, room for %d (cut)" % (ids.get("EXE:%x" % s, "EXE:%x" % s), need, room))
    if cfg.get("native_ascii"):       # text layer through DOS: only the pager
        from .jast_console import install
        vol.write(exe_path, install(vol.read(exe_path), cfg["cave"]))
    else:                             # engines that draw only kanji-ROM glyphs
        vol.write(exe_path, patch_engine(vol.read(exe_path), cfg["dgroup"], cfg["pointers"]))
    vol.create(_path(cfg, "MTL_NOTE.TXT"),
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    img.save(dst)
    stem = os.path.splitext(dst)[0]
    for tag, other, _vol in all_disks[1:]:
        other.save("%s - %s" % (stem, os.path.basename(other.path)))
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
