"""Illusion's C-compiled games that draw text from a 24-dot font of their
own (Moeru Asoko no Paipai Yuugi, Angel Army): extraction.

The engine (Microsoft EXEPACK-packed, unpacked with pc98tl/exepack.py)
keeps its text as NUL-terminated Shift-JIS strings in its data segment.
Its font holds symbols, digits, capital letters, kana and the kanji the game
uses; a character's glyph comes from fixed code ranges and two code tables
(symbols, kanji), which are font maps and not text.

game.json: {"title", "key", "image", "game_dir", "engine", "encoding": "illusion_font24",
            "data": [start, end] (image offsets of the text area),
            "skip": [[start, end], ...] (the font maps inside it)}
A string's ref is "exe:<unpacked file offset>" with its byte length as the
limit (strings are replaced in place); kind "dos" strings (with line breaks)
are printed through DOS and stay plain ASCII.

The text drawer takes two bytes per cell.  English is written as letter
pairs (encode_en) that the patched drawer shows as two kanji-ROM ANK letters
in one cell (patch_engine); game.json then also has "dgroup" (the data
segment) and "pointers" (two DGROUP offsets that stay zero at run time, for
the hooks' far pointers).
"""
import json
import os
import re

from .disk import DiskImage
from .alice_sys2_tl import sha256
from . import exepack

CSTR = re.compile(rb"(?<=\x00)((?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e]|\r|\n)+)\x00")
JAPANESE = re.compile("[぀-ヿ一-鿿Ａ-ｚ]")


def _path(cfg, name):
    return (cfg["game_dir"] + "/" if cfg["game_dir"] else "") + name


def engine(cfg, vol):
    exe = vol.read(_path(cfg, cfg["engine"]))
    return exepack.unpack(exe) if exepack.is_packed(exe) else exe


def strings_in(exe, cfg):
    """[(file offset, byte length, text)] in the text area, font maps skipped."""
    import struct
    base = struct.unpack_from("<H", exe, 8)[0] * 16
    lo, hi = cfg["data"]
    skips = cfg.get("skip", [])
    out = []
    for m in CSTR.finditer(exe, base + lo, base + hi):
        at = m.start(1) - base
        if any(s <= at < e for s, e in skips):
            continue
        raw = m.group(1)
        try:
            text = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        if JAPANESE.search(text):
            out.append((m.start(1), len(raw), text.replace("\r\n", "\n")))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    exe = engine(cfg, vol)
    merged, order = {}, []
    for off, size, jp in strings_in(exe, cfg):
        ref = "exe:%05x" % off
        if jp in merged:
            merged[jp]["refs"].append(ref)
            merged[jp]["max_bytes"] = min(merged[jp]["max_bytes"], size)
            continue
        merged[jp] = {"kind": "dos" if "\n" in jp else "exe", "jp": jp, "en": "", "refs": [ref],
                      "max_bytes": size}
        if "%" in jp:
            merged[jp]["note"] = ("printf format: keep the %-specifier; the result is drawn as "
                                  "letter pairs, so the English on each side of the specifier "
                                  "must be even in length")
        order.append(jp)
    strings = [{"id": "e%05d" % i, **merged[jp]} for i, jp in enumerate(order, 1)]
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


# ---- patch --------------------------------------------------------------

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""

# the text drawer's glyph path: SJIS -> JIS (near call), kanji-ROM fetch
# into a 16x16 buffer (near call), both preceded by "push cs"
CONV_CALL = re.compile(rb"\x03\xc1\x50\x0e\xe8(..)\x5b\x89\x46\xd2", re.S)
FETCH_CALL = re.compile(rb"\xff\x76\xd2\x0e\xe8(..)\x83\xc4\x06", re.S)


def encode_en(text):
    """English as letter pairs the patched drawer shows in one cell: first
    byte A0-DF (never a Shift-JIS lead, a font-table code or a control
    code), second byte ASCII; a first letter 60-7F sets the second byte's
    top bit.  An odd length gets a trailing space."""
    subst = {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2014": "-",
             "\u2013": "-", "\u2026": "..."}
    s = "".join(subst.get(c, c) for c in text)
    s = "".join(c if 0x20 <= ord(c) < 0x7F else "?" for c in s)
    if len(s) % 2:
        s += " "
    out = bytearray()
    for i in range(0, len(s), 2):
        a, b = ord(s[i]), ord(s[i + 1])
        if a < 0x60:
            out += bytes([0xA0 + a - 0x20, b])
        else:
            out += bytes([0xA0 + a - 0x60, b | 0x80])
    return bytes(out)


def patch_engine(exe, cfg):
    """Hook the drawer's glyph path (see encode_en): the two far routines
    live in a DOS block set up by illusion_font's entry stub; the drawer
    reaches them through far pointers in DGROUP bytes that stay zero."""
    import struct
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    from .illusion_font import _asm, _entry_stub
    exe = bytearray(exe)
    base = struct.unpack_from("<H", exe, 8)[0] * 16
    img = bytes(exe[base:])
    c = CONV_CALL.search(img)
    f = FETCH_CALL.search(img)
    if not c or not f:
        raise ValueError("text drawer glyph calls not found")
    dgroup, ptrs = cfg["dgroup"], cfg["pointers"]
    ks = Ks(KS_ARCH_X86, KS_MODE_16)
    src = """
        .word 0, 0, 0, 0, 0
    conv:
        push bp
        mov bp, sp
        mov ax, word ptr [bp + 6]
        cmp ah, 0xa0
        jb sj
        cmp ah, 0xdf
        ja sj
        mov dl, ah
        sub dl, 0xa0
        test al, 0x80
        jz c1
        and al, 0x7f
        add dl, 0x60
        jmp c2
    c1:
        add dl, 0x20
    c2:
        mov ah, dl
        or ah, 0x80
        pop bp
        .byte 0xcb
    sj:
        mov dl, ah
        xor dh, dh
        cmp dx, 0xe0
        jb s1
        sub dx, 0x40
    s1:
        shl dx, 1
        sub dx, 0xe1
        xor ah, ah
        cmp ax, 0x7f
        jbe s2
        dec ax
    s2:
        cmp ax, 0x9d
        jbe s3
        inc dx
        sub ax, 0x7d
        jmp s4
    s3:
        sub ax, 0x1f
    s4:
        mov ah, dl
        pop bp
        .byte 0xcb
    fetch:
        push bp
        mov bp, sp
        push es
        push di
        push bx
        push cx
        les di, dword ptr [bp + 8]
        mov bx, word ptr [bp + 6]
        mov al, 0x0b
        out 0x68, al
        cld
        test bh, 0x80
        jnz eng
        mov al, bl
        out 0xa1, al
        mov al, bh
        sub al, 0x20
        out 0xa3, al
        xor cx, cx
    kr1:
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
        jb kr1
        jmp done
    eng:
        and bh, 0x7f
        xor al, al
        out 0xa1, al
        mov al, bh
        out 0xa3, al
        xor cx, cx
    a1:
        mov al, cl
        or al, 0x20
        out 0xa5, al
        in al, 0xa9
        stosb
        inc di
        inc cx
        cmp cx, 16
        jb a1
        sub di, 31
        xor al, al
        out 0xa1, al
        mov al, bl
        out 0xa3, al
        xor cx, cx
    b1:
        mov al, cl
        or al, 0x20
        out 0xa5, al
        in al, 0xa9
        stosb
        inc di
        inc cx
        cmp cx, 16
        jb b1
    done:
        mov al, 0x0a
        out 0x68, al
        pop cx
        pop bx
        pop di
        pop es
        pop bp
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
    blob, labels = _asm(ks, src, 0, ("conv", "fetch", "finish"))
    labels = {"head_far": labels["conv"], "common_far": labels["fetch"], "finish": labels["finish"]}
    # "push cs; call near" (4 bytes) -> "call far [ptr]" (4 bytes, DS = DGROUP)
    exe[base + c.start() + 3:base + c.start() + 7] = b"\xff\x1e" + struct.pack("<H", ptrs[0])
    exe[base + f.start() + 3:base + f.start() + 7] = b"\xff\x1e" + struct.pack("<H", ptrs[1])
    _entry_stub(ks, exe, blob, labels, dgroup, ptrs[0], ptrs[1])
    return bytes(exe)


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    exe = bytearray(engine(cfg, vol))
    report = []
    for e in doc["strings"]:
        if mode == "pseudo":
            if "%" in e["jp"]:
                continue          # format strings keep their specifiers
            text = pseudo(e["id"], len(e["jp"].encode("cp932")) * 5 // 4)
            if e["kind"] == "dos":
                text += "\n"
        else:
            text = e["en"]
        if not text:
            continue
        keep_nl = text.endswith("\n")
        if e["kind"] == "dos":        # printed through DOS: plain ASCII
            enc = b"\r\n".join(line.encode("ascii", "replace") for line in text.rstrip("\n").split("\n"))
        else:
            enc = b"\r\n".join(encode_en(line) for line in text.rstrip("\n").split("\n"))
        if keep_nl:
            enc += b"\n"
        n = e["max_bytes"]
        if len(enc) > n:
            report.append("%s: %d bytes, only %d fit (truncated)" % (e["id"], len(enc), n))
            enc = enc[:n - (n % 2)]
        for r in e["refs"]:
            off = int(r[4:], 16)
            exe[off:off + n] = enc.ljust(n, b"\0")
    vol.write(_path(cfg, cfg["engine"]), patch_engine(bytes(exe), cfg))
    vol.create(_path(cfg, "MTL_NOTE.TXT"),
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    img.save(dst)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
    for line in report:
        print("  " + line)
