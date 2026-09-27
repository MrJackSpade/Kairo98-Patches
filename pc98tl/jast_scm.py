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
            "boot_steps", "dipsw"}
A string's ref is "<file>:<message number>".
"""
import json
import os
import re
import struct

from .disk import DiskImage
from .alice_sys2_tl import sha256

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


def text_start(data):
    """Where the messages begin: the first Shift-JIS character after the
    tables (every message is Shift-JIS text ended by 00 00)."""
    m = re.search(rb"[\x81-\x9f\xe0-\xef][\x40-\xfc]", data)
    return m.start() if m else len(data)


def messages(data):
    """[(number, start, end)]: messages after the tables, each ended by 00 00."""
    out, i, n = [], text_start(data), 0
    while i < len(data):
        e = data.find(b"\x00\x00", i)
        if e < 0:
            break
        out.append((n, i, e))
        n += 1
        i = e + 2
    return out


def scene_files(cfg, vol):
    ents = vol.listdir(vol.find(cfg["game_dir"])["cluster"]) if cfg["game_dir"] else vol.listdir(0)
    return sorted(e["name"] for e in ents if e["name"].upper().endswith(".SCM"))


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for name in scene_files(cfg, vol):
        data = vol.read(_path(cfg, name))
        for num, s, e in messages(data):
            jp = data[s:e].decode("cp932", "replace").replace("\x00", "\n")
            if not jp.strip():
                continue
            ref = "%s:%d" % (name, num)
            if jp in merged:
                merged[jp]["refs"].append(ref)
                continue
            merged[jp] = {"kind": "msg", "jp": jp, "en": "", "refs": [ref]}
            order.append(jp)
    strings = [{"id": "m%05d" % i, **merged[jp]} for i, jp in enumerate(order, 1)]
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


def lay_out(text, cols):
    """Word-wrapped to the window (lines padded to full width, two letters a
    cell, so the engine's own cell wrap lands between words)."""
    from .text import wrap
    lines = []
    for para in text.split("\n"):
        lines += wrap(para, cols, width=len) or [""]
    body = "".join(line.ljust(cols) if k < len(lines) - 1 else line for k, line in enumerate(lines))
    return encode_en(body)


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    cols = cfg.get("cols", 60)
    by_ref = {}
    for e in doc["strings"]:
        text = pseudo(e["id"], int(len(e["jp"]) * 2)) if mode == "pseudo" else e["en"]
        if text:
            for r in e["refs"]:
                by_ref[r] = lay_out(text, cols)
    for name in scene_files(cfg, vol):
        data = vol.read(_path(cfg, name))
        out, pos, changed = bytearray(), 0, False
        for num, s, e in messages(data):
            en = by_ref.get("%s:%d" % (name, num))
            if en is None:
                continue
            out += data[pos:s] + en
            pos = e
            changed = True
        if changed:
            out += data[pos:]
            vol.write(_path(cfg, name), bytes(out))
    exe_path = _path(cfg, cfg["engine"])
    vol.write(exe_path, patch_engine(vol.read(exe_path), cfg["dgroup"], cfg["pointers"]))
    vol.create(_path(cfg, "MTL_NOTE.TXT"),
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    img.save(dst)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
