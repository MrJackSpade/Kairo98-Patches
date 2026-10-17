"""English for Crystal Soft's Virgin Angel (pc98tl/vangel.py): strings.json in, a patched disk out.

Strings:
* m (message): narration, any length: broken between words and paged by the patcher; \\n a new line.
* d (dialogue): a speaker's lines, any length (broken narrower, under the speaker's name).
* n (name): a speaker's name, drawn before the first of their lines.
* e (program): M.EXE's own text (the opening's lines, the staff roll, the music mode, messages), in
  place: max_cells letters.
* b (batch): the start-up batch files' lines (the sound board's choice), DOS text: any length; {Cn} a
  colour, kept.
* a (announcement): ANNOUNCE.TXT's lines (the title menu's last choice): any length up to 78 letters.

A build with English writes CMD00.TXB again, M.EXE unpacked with the half-width helper and its own text,
the batch files and ANNOUNCE.TXT.
"""
import json
import os
import re
import unicodedata

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import vangel as V
from .text import pseudo

PREFIX = {"msg": "m", "dlg": "d", "name": "n", "prog": "e", "bat": "b", "ann": "a"}
NOTE = {"msg": "narration: any length (broken between words and paged by the patcher); \\n a new line",
        "dlg": "a speaker's lines: any length (broken between words, under the speaker's name)",
        "name": "a speaker's name (drawn before their first line)",
        "prog": "the program's own text, in place: max_cells letters",
        "bat": "a start-up batch file's line (DOS): any length; keep each {Cn} (a colour)",
        "ann": "a line of the announcement screen: up to max_cells letters"}
BATCHES = ("GAME.BAT", "HDGAME.BAT")
ESC = re.compile(rb"\x1b\[(\d+)m")
JP = re.compile(rb"[\x81-\x9f\xe0-\xfc][\x40-\xfc]|[\xa1-\xdf]")


def _path(cfg, name):
    return cfg["dir"] + "/" + name


def _program(vol, cfg):
    exe = V.plain(vol.read(_path(cfg, cfg["engine"])))
    h = int.from_bytes(exe[8:10], "little") * 16
    return exe, h, exe[h:]


def found(vol, cfg):
    """[(ref, kind, Japanese text, max cells or None)]."""
    out = []
    exe, _h, image = _program(vol, cfg)
    kana = V.kana_table(image)
    kana_at = V.KANA_SIG.search(image)
    kana_at = int.from_bytes(kana_at.group(1), "little") * 16
    parts, _tail = V.texts(V.decode(vol.read(_path(cfg, cfg["text"]))))
    for t, text in enumerate(parts):
        for kind, nums in V.units(text):
            jp = V.show(V.unit_bytes(text, kind, nums), kana)
            if jp.strip():
                out.append(("T:%03d:%s:%d" % (t, kind, nums[0]), kind, jp, None))
    for s, e, console in V.program_strings(image, kana_at):
        out.append(("E:%05x:%s" % (s, "c" if console else "g"), "prog",
                    image[s:e].decode("cp932").replace("\r", "").replace("\n", "\\n"), e - s))
    for name in BATCHES:
        if not vol.find(_path(cfg, name)):
            continue
        for n, line in enumerate(vol.read(_path(cfg, name)).split(b"\r\n")):
            if line[:5].lower() == b"echo " and JP.search(line):
                out.append(("B:%s:%d" % (name, n), "bat", _bat_show(line[5:]), None))
    ann = vol.read(_path(cfg, "ANNOUNCE.TXT"))
    for n, line in enumerate(ann.split(b"\r\n")):
        if JP.search(line):
            out.append(("A:%d" % n, "ann", line.decode("cp932", "replace"), 78))
    return out


def _bat_show(b):
    return ESC.sub(lambda m: b"{C%s}" % m.group(1), b).decode("cp932", "replace")


def run_extract(here, src):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = DiskImage(src).volumes[0]
    merged, order = {}, []
    for ref, kind, jp, room in found(vol, cfg):
        key = (kind, jp)
        if key in merged:
            merged[key]["refs"].append(ref)
            merged[key]["max_cells"] = min(merged[key]["max_cells"], room or 9999)
            continue
        merged[key] = {"kind": kind, "jp": jp, "en": "", "refs": [ref], "max_cells": room or 9999,
                       "note": NOTE[kind]}
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
    if e["kind"] == "bat":
        parts = re.split(r"(\{C\d+\})", e["jp"])
        return "".join(p if p.startswith("{C") else pseudo(e["id"], _cols(p)) for p in parts if p)
    if e["kind"] in ("prog", "ann"):
        return pseudo(e["id"], _cols(e["jp"]))
    return pseudo(e["id"], _cols(e["jp"]))


def _ascii(text):
    subst = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
    s = "".join(subst.get(c, c) for c in text)
    return "".join(c if 0x20 <= ord(c) < 0x7F else "?" for c in s).encode("ascii")


def _bat_line(text):
    """An echo line's English: {Cn} as the colour's escape; DOS's redirections < > | written as ( ) /,
    % doubled."""
    out = b""
    for p in re.split(r"(\{C\d+\})", text):
        m = re.fullmatch(r"\{C(\d+)\}", p)
        if m:
            out += b"\x1b[" + m.group(1).encode("ascii") + b"m"
        elif p:
            safe = p.replace("<", "(").replace(">", ")").replace("|", "/")
            out += _ascii(safe).replace(b"%", b"%%")
    return out


def run_patch(here, src, dst, mode="en"):
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    vol = img.volumes[0]
    by_ref = {}
    for e in doc["strings"]:
        text = _pseudo(e) if mode == "pseudo" else e["en"]
        for r in e["refs"]:
            by_ref[r] = (e, text)
    warn, texts, places, bats, ann = [], {}, [], {}, {}
    for ref, kind, jp, room in found(vol, cfg):
        e, text = by_ref.get(ref, (None, ""))
        if not text:
            continue
        part = ref.split(":")
        if part[0] == "T":
            texts.setdefault(int(part[1]), {})[(part[2], int(part[3]))] = text
        elif part[0] == "E":
            letters = text.replace("\\n", " ")
            if len(letters) > room:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(letters), room))
                letters = letters[:room]
            if part[2] == "c":
                b = _ascii(letters).ljust(room, b" ")
            else:
                # (two letters a character; an odd room ends with a space byte, which the drawers skip)
                even = room - room % 2
                b = V.pairs(V._normal(letters)[:even].ljust(even)) + b" " * (room % 2)
            places.append((int(part[1], 16), b))
        elif part[0] == "B":
            bats.setdefault(part[1], {})[int(part[2])] = text
        else:
            if len(text) > room:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(text), room))
            ann[int(part[1])] = text[:room]
    if not (texts or places or bats or ann):
        img.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    exe, h, image = _program(vol, cfg)
    kana = V.kana_table(image)
    tp = _path(cfg, cfg["text"])
    parts, tail = V.texts(V.decode(vol.read(tp)))
    for t, english in texts.items():
        parts[t] = V.text(parts[t], english, kana)
        if len(parts[t]) > V.LIMIT:
            raise SystemExit("text %d: %d bytes with its English, the program's text buffer holds %d; shorten "
                             "its English" % (t, len(parts[t]), V.LIMIT))
    vol.write(tp, V.encode(V.join(parts, tail)))
    vol.write(_path(cfg, cfg["engine"]), V.patch_program(exe, places))
    for name, lines in bats.items():
        p = _path(cfg, name)
        old = vol.read(p).split(b"\r\n")
        for n, text in lines.items():
            old[n] = b"echo " + _bat_line(text)
        vol.write(p, b"\r\n".join(old))
    if ann:
        p = _path(cfg, "ANNOUNCE.TXT")
        old = vol.read(p).split(b"\r\n")
        for n, text in ann.items():
            old[n] = _ascii(text)
        vol.write(p, b"\r\n".join(old))
    vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
