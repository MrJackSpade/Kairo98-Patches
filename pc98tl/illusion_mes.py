"""Illusion's older MES*.D message files (Seisenshi Mokkoriman) and their
extract/patch driver.

A file is a run of records, each "10 <index> <group>" followed by Shift-JIS
text up to the next 10; the file ends "10 FF FF".  CR (0D) breaks a line.
The group byte tells the kind of text: in MES0.D 90 = character profiles
(one record per line, drawn in the profile frame) and A0 = the song lyrics
of a song; F4 = disk-change prompts in every file; the other groups are
scene messages.

The engine draws a byte below 80 from its own 8x16 font (FONT.DAT, a full
ASCII set), so English is half-width with no engine change.  Records may
change length; the engine loads each file into a 10000-byte buffer
(segment 636B up to the next buffer at 65DC), which bounds a file's size.

The engine's text window scrolls when its rows run out; the patch makes it
page instead (patch_engine), since English outgrows the Japanese.

game.json: {"title", "key", "image", "game_dir", "engine", "encoding": "illusion_mes",
            "files": ["MES0.D", ...], "cols": {"<group hex>": columns, ...},
            "default_cols", "max_file": 10000, "boot_steps"}
A string's ref is "<file>:<record ordinal>".
"""
import json
import os
import re

from .disk import DiskImage
from .alice_sys2_tl import sha256

RECORD = re.compile(rb"\x10(.)(.)", re.S)

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""


def parse(data):
    """[(ordinal, index, group, text start, text end)] (the FF FF end record excluded)."""
    heads = list(RECORD.finditer(data))
    out = []
    for k, m in enumerate(heads):
        if m.group(1) == b"\xff":
            break
        end = heads[k + 1].start() if k + 1 < len(heads) else len(data)
        out.append((k, m.group(1)[0], m.group(2)[0], m.end(), end))
    return out


def rebuild(data, texts):
    """Replace record texts ({ordinal: bytes}); every other byte kept."""
    out, prev = bytearray(), 0
    for k, _i, _g, s, e in parse(data):
        if k in texts:
            out += data[prev:s] + texts[k]
            prev = e
    out += data[prev:]
    return bytes(out)


def _path(cfg, name):
    return (cfg["game_dir"] + "/" if cfg["game_dir"] else "") + name


def _cols(cfg, group):
    return cfg.get("cols", {}).get("%02x" % group, cfg.get("default_cols", 70))


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for name in cfg["files"]:
        data = vol.read(_path(cfg, name))
        for k, _i, group, s, e in parse(data):
            jp = data[s:e].decode("cp932", "replace").replace("\r", "\n")
            if not jp.strip("　 \n"):
                continue
            key = (group, jp)
            ref = "%s:%d" % (name, k)
            if key in merged:
                merged[key]["refs"].append(ref)
                continue
            kind = {0x90: "profile", 0xA0: "lyric", 0xF4: "prompt"}.get(group, "msg")
            merged[key] = {"kind": kind,
                           "jp": jp, "en": "", "refs": [ref], "max_cols": _cols(cfg, group)}
            order.append(key)
    strings = [{"id": "m%05d" % i, **merged[k]} for i, k in enumerate(order, 1)]
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


def _encode(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
    from .text import encode_fullwidth
    out = bytearray()
    for ch in text:
        ch = subst.get(ch, ch)
        for c in ch:
            out += bytes([ord(c)]) if 0x20 <= ord(c) < 0x7F else encode_fullwidth(c)
    return bytes(out)


def _lay_out(text, cols):
    """Word-wrap to the record's columns (a line that fits is kept as
    written), lines joined with CR."""
    from .text import wrap
    width = lambda t: len(_encode(t))  # noqa: E731
    lines = []
    for para in text.split("\n"):
        lines += [para] if width(para) <= cols else wrap(para, cols, width=width)
    return b"\r".join(_encode(line) for line in lines)


# the text window's newline, where it would scroll the window up
SCROLL = re.compile(rb"\xf6\x44\x0c\x80\x74\x05\xc6\x44\x0b\x00\xcb"
                    rb"(\xc6\x44\x0a\x00\x8a\x44\x08\x32\xe4\x39\x44\x04\x76\x2d\x8a\x04\x32\xe4\x8b\x54\x01)"
                    rb"\x9a..\x00\x00", re.S)
CLEAR = re.compile(rb"\x32\xc0\x88\x44\x0a\x88\x44\x0b\xf6\x44\x0c\x04\x75\x15")


def patch_engine(exe):
    """Page instead of scroll: when a text window runs out of rows, wait for
    the space key (BIOS key table 0:0530 bit 4, as the game reads it) or the
    left mouse button (port 7FD9 bit 7), until it's released, then clear the
    window (the engine's own clear routine) and go on at the top.  The code
    goes into the dead scroll code, around the two relocated far calls in it
    (their segment words stay untouched)."""
    import struct
    from keystone import Ks, KS_ARCH_X86, KS_MODE_16
    exe = bytearray(exe)
    hdr = struct.unpack_from("<14H", exe, 0)
    base = hdr[4] * 16
    img = bytes(exe[base:])
    m = SCROLL.search(img)
    c = CLEAR.search(img)
    if not m or not c:
        raise ValueError("text window routines not found")
    a = m.start(1)                   # first free byte
    fix1 = m.end() - 2               # segment word of the first far call
    relocs = {struct.unpack_from("<H", exe, hdr[12] + 4 * k)[0] +
              struct.unpack_from("<H", exe, hdr[12] + 4 * k + 2)[0] * 16 for k in range(hdr[3])}
    b = fix1 + 2                     # second chunk, up to the next relocated word
    nxt = min(r for r in relocs if r > fix1)
    ks = Ks(KS_ARCH_X86, KS_MODE_16)

    def asm(src, org):
        return bytes(ks.asm(src, org)[0])
    # two passes: chunk A jumps to chunk B, chunk B loops back into A
    chunk_b_src = """
        in al, dx
        test al, 0x80
        jnz {p1}
    rel:
        test byte ptr es:[0x530], 0x10
        jnz rel
        in al, dx
        test al, 0x80
        jz rel
        pop es
        pop dx
        pop ax
        push cs
        .byte 0xe8
        .word {clr}
        .byte 0xcb
    """
    p1 = a + 10                      # push ax, dx, es; xor ax,ax; mov es,ax; mov dx,7FD9
    chunk_a = asm("""
        push ax
        push dx
        push es
        xor ax, ax
        mov es, ax
        mov dx, 0x7fd9
    p1:
        test byte ptr es:[0x530], 0x10
        jnz 0x%x
        jmp 0x%x
    """ % (b + 5, b), a)
    if len(chunk_a) > fix1 - 3 - a:
        raise ValueError("pager part A too long")
    chunk_b = asm(chunk_b_src.format(p1=p1, clr=0), b)
    call_at = b + chunk_b.index(b"\x0e\xe8") + 1
    disp = (c.start() - (call_at + 3)) & 0xFFFF
    chunk_b = asm(chunk_b_src.format(p1=p1, clr=disp), b)
    if b + len(chunk_b) > nxt:
        raise ValueError("pager part B too long")
    if chunk_a[p1 - a:p1 - a + 2] != b"\x26\xf6":
        raise ValueError("pager part A layout changed")
    exe[base + a:base + a + len(chunk_a)] = chunk_a
    exe[base + b:base + b + len(chunk_b)] = chunk_b
    return bytes(exe)


def run_patch(here, src, dst, mode="en"):
    from .text import pseudo
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    by_ref = {}
    for e in doc["strings"]:
        if mode == "pseudo":
            text = pseudo(e["id"], 2 * (len(e["jp"]) - e["jp"].count("\n")))
            if e["kind"] == "profile":      # one frame line per record
                text = text[:e["max_cols"]]
        else:
            text = e["en"]
        if text:
            for r in e["refs"]:
                by_ref[r] = _lay_out(text, e["max_cols"])
    report = []
    limit = cfg.get("max_file", 10000)
    for name in cfg["files"]:
        data = vol.read(_path(cfg, name))
        texts = {}
        for k, _i, _g, _s, _e in parse(data):
            new = by_ref.get("%s:%d" % (name, k))
            if new is not None:
                texts[k] = new
        new_data = rebuild(data, texts)
        if len(new_data) > limit:
            raise SystemExit("%s: %d bytes, the engine's buffer holds %d" % (name, len(new_data), limit))
        vol.write(_path(cfg, name), new_data)
    exe_path = _path(cfg, cfg["engine"])
    vol.write(exe_path, patch_engine(vol.read(exe_path)))
    vol.create(_path(cfg, "MTL_NOTE.TXT"),
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    img.save(dst)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
    for line in report:
        print("  " + line)
