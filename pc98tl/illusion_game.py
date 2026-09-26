"""Extract/patch driver for Illusion (tmexec engine) games.

game.json:
  {"title", "key", "image", "game_dir": "KAN", "engine": "GAME.EXE",
   "encoding": "illusion", optional "window_cols", "box_lines", "boot_steps"}
Every file in game_dir holding "#nnnnn ... $" records is a message file
(pc98tl/illusion.py); a message's ref is "<file>:<number>".  Japanese
strings hard-coded in the engine (ended by "$" too) are "exe" strings with
ref "exe:<offset>", replaced in place.
"""
import json
import os
import re

from .disk import DiskImage
from .alice_sys2_tl import sha256
from . import illusion

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""

EXE_TEXT = re.compile(rb"((?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|\r\n|[\x20-\x23\x25-\x7e]){3,})\$")
KANA = re.compile("[ぁ-ヿ]")


def _cells(text):
    return max((sum(1 if ord(c) < 0x80 else 2 for c in line) + 1) // 2 for line in text.split("\n"))


def _message_files(vol, game_dir):
    out = []
    ents = vol.listdir(vol.find(game_dir)["cluster"]) if game_dir else vol.listdir(0)
    for e in sorted(ents, key=lambda e: e["name"]):
        if e["is_dir"] or e["size"] > 300000:
            continue
        path = (game_dir + "/" if game_dir else "") + e["name"]
        data = vol.read(path)
        if illusion.is_message_file(data):
            out.append((e["name"], path, data))
    return out


def exe_strings(exe):
    """Japanese strings hard-coded in the engine, ended by "$" like the
    message records (drawn by the same library, or printed through DOS):
    [(offset, byte length, text)].  A string needs two kana, unless it sits
    in a "$"-separated table (character names, menu labels)."""
    out = []
    for m in EXE_TEXT.finditer(exe):
        raw, k = m.group(1), 0
        while k < len(raw) and not (0x81 <= raw[k] <= 0x9F or 0xE0 <= raw[k] <= 0xEF):
            k += 1
        raw = raw[k:]
        try:
            text = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        start = m.start(1) + k
        in_table = exe[start - 1] == 0x24 and "\r\n" not in text and text.strip("　") != ""
        if len(KANA.findall(text)) >= 2 or in_table:
            out.append((m.start(1) + k, len(raw), text.replace("\r\n", "\n")))
    return out


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for name, _path, data in _message_files(vol, cfg["game_dir"]):
        for num, text, _s, _e in illusion.parse(data):
            jp = text.decode("cp932", "replace").replace("\r\n", "\n")
            ref = "%s:%05d" % (name, num)
            if jp in merged:
                merged[jp]["refs"].append(ref)
                continue
            merged[jp] = {"kind": "msg", "jp": jp, "en": "", "refs": [ref], "max_cells": _cells(jp)}
            order.append(jp)
    strings = []
    for i, jp in enumerate(order, 1):
        strings.append({"id": "m%05d" % i, **merged[jp]})
    exe = vol.read(cfg["game_dir"] + "/" + cfg["engine"])
    for i, (off, size, jp) in enumerate(exe_strings(exe), 1):
        strings.append({"id": "e%05d" % i, "kind": "exe", "jp": jp, "en": "",
                        "refs": ["exe:%05x" % off], "max_bytes": size, "max_cells": _cells(jp)})
    out = os.path.join(here, "strings.json")
    if os.path.exists(out):  # keep translations and hand-tuned fields
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in strings:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                for k in ("en", "max_cells", "note"):
                    if k in prev:
                        e[k] = prev[k]
    doc = {"game": cfg["title"], "source_image_sha256": sha256(src), "strings": strings}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote %s: %d strings" % (out, len(strings)))


def encode_en(text):
    """English as one byte per ASCII character (drawn half-width by the
    patched engine); "$" ends a record and "#" starts one, so they are
    replaced; anything else outside ASCII is written as full-width Shift-JIS."""
    from .text import encode_fullwidth
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-",
             "…": "...", "$": "S", "#": "No."}
    out = bytearray()
    for ch in text:
        ch = subst.get(ch, ch)
        for c in ch:
            out += bytes([ord(c)]) if 0x20 <= ord(c) < 0x7F else encode_fullwidth(c)
    return bytes(out)


def _lay_out(text, cols):
    """Word-wrap English to the message window's width (the engine would
    otherwise break lines mid-word) and join lines with CR LF.  A line that
    already fits is kept as written, spacing included (menus place their
    items at fixed columns)."""
    from .text import wrap
    cols = max(8, cols)
    width = lambda t: len(encode_en(t))  # noqa: E731
    lines = []
    for para in text.split("\n"):
        lines += [para] if width(para) <= cols else wrap(para, cols, width=width)
    return b"\r\n".join(encode_en(line) for line in lines)



def _box_lines(cfg, doc, window):
    """Lines the message box holds: the most lines Japanese records fill when
    the engine wraps them at the window width (the authors kept records
    inside their box), counting only line counts at least 1% of records
    reach, since a few records (credits, endings) are drawn in larger windows.
    game.json "box_lines" overrides it."""
    if cfg.get("box_lines"):
        return cfg["box_lines"]
    counts = {}
    for e in doc["strings"]:
        if e["kind"] != "msg":
            continue
        n = sum(max(1, -(-sum(1 if ord(c) < 0x80 else 2 for c in line) // window))
                for line in e["jp"].split("\n"))
        counts[n] = counts.get(n, 0) + 1
    total = sum(counts.values())
    return max([n for n, k in counts.items() if k * 100 >= total] or [1])


def _text(e, mode):
    from .text import pseudo
    if mode == "pseudo":
        return pseudo(e["id"], 2 * (len(e["jp"]) - e["jp"].count("\n")))
    return e["en"]


def run_patch(here, src, dst, mode="en"):
    from . import illusion_font
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    report = []
    exe_path = cfg["game_dir"] + "/" + cfg["engine"]
    exe = bytearray(vol.read(exe_path))
    window = cfg.get("window_cols") or illusion_font.message_width(bytes(exe)) or 34
    for e in doc["strings"]:          # engine strings: in place, ended by "$"
        if e["kind"] != "exe":
            continue
        text = _text(e, mode)
        if not text:
            continue
        enc = b"\r\n".join(encode_en(line) for line in text.split("\n"))
        n = e["max_bytes"]
        if len(enc) > n:
            report.append("%s: %d bytes, only %d fit (truncated)" % (e["id"], len(enc), n))
            enc = enc[:n]
        off = int(e["refs"][0][4:], 16)
        exe[off:off + n + 1] = (enc + b"$").ljust(n + 1, b" ")
    by_ref = {}
    for e in doc["strings"]:
        if e["kind"] != "msg":
            continue
        text = _text(e, mode)
        if text:
            for r in e["refs"]:
                by_ref[r] = _lay_out(text, window)
    for name, path, data in _message_files(vol, cfg["game_dir"]):
        texts = {}
        for num, _t, _s, _e in illusion.parse(data):
            new = by_ref.get("%s:%05d" % (name, num))
            if new is not None:
                texts[num] = new
        if texts:
            vol.write(path, illusion.rebuild(data, texts))
    vol.write(exe_path, illusion_font.build(bytes(exe), box_lines=_box_lines(cfg, doc, window)))
    vol.create(cfg["game_dir"] + "/MTL_NOTE.TXT",
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    img.save(dst)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
    for line in report:
        print("  " + line)
