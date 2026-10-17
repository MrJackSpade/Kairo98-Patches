"""English for Custom's Star Platinum (pc98tl/starpt.py): strings.json in, a patched disk out.

Strings:
* m (message): narration, any length: broken between words at the window's width (a narrower layout's
  where the Japanese is narrower) and paged by the patcher; \\n a new line; keep each {..} code (a wait,
  a pause, the typing speed) where it belongs; {Gxxxx} is a character of the game's font and is dropped.
* d (dialogue): a speaker's lines, any length (broken under the speaker's name, a new screen with the
  name again after the window's lines).
* n (name): a speaker's name, up to max_cells letters (the column before the lines).
* c (choice): a menu's line (the top menu, the story menu, the galleries), one line: max_cells letters.
* b (balloon): a line of the card game's balloons: broken between words at 27 letters, up to 4 lines.
* r (credit): a line of a staff roll (the ending's, the gallery's): one line, centred where the Japanese
  was.
* e (program): the programs' own text (the system menu, the card rules; the drivers' and the start-up
  disk maker's DOS messages), in place: max_cells letters; \\n a new line; keep each %s, %d, %c, %ld and
  {ESC}.

A build with English writes SCENARIO.GDM and MUSIC.GDM (the balloons, the staff rolls) again, and the
programs unpacked with their own text (the ones that draw text with the half-width helper).
"""
import json
import os
import re
import unicodedata

from .alice_sys2_tl import sha256
from .alice_game import MTL_NOTE
from .disk import DiskImage
from . import pklite
from . import starpt as S
from .text import pseudo

PREFIX = {"msg": "m", "dlg": "d", "name": "n", "choice": "c", "balloon": "b", "credit": "r", "prog": "e"}
NOTE = {"msg": "narration: any length (broken between words and paged by the patcher); \\n a new line; "
               "keep each {..} code",
        "dlg": "a speaker's lines: any length (broken under the speaker's name, paged by the patcher); "
               "keep each {..} code",
        "name": "a speaker's name: up to max_cells letters",
        "choice": "a menu's choice: one line, max_cells letters",
        "balloon": "a card game balloon: broken between words at 27 letters, up to 4 lines",
        "credit": "a staff roll's line: one line (centred by the patcher), up to max_cells letters",
        "prog": "the program's own text, in place: max_cells letters; \\n a new line; keep each %s, %d, %c, %ld and "
                "{ESC}"}
MODULES = ("SPV.BIN", "SPG.BIN", "SPD.BIN", "SPE.BIN", "SPF.BIN", "SPO.BIN", "CUSTLOGO.BIN", "VAL24.BIN", "CSTMOUSE.BIN",
           "CSTMET.BIN", "CSTMIDI.BIN", "MKBOOT.EXE")
CONSOLE = ("VAL24.BIN", "CSTMOUSE.BIN", "CSTMET.BIN", "CSTMIDI.BIN", "MKBOOT.EXE")   # (their text DOS messages)
DRAWS = ("SPV.BIN", "SPG.BIN", "SPD.BIN", "SPE.BIN", "SPF.BIN")     # (the others draw no text: their own
                                                                    # is DOS messages)
SCENARIO, MUSIC = "SCENARIO.GDM", "MUSIC.GDM"


def _path(cfg, name):
    return cfg["dir"] + "/" + name


def _modules(vol, cfg):
    """{name: the module unpacked}."""
    out = {}
    for name in MODULES:
        data = vol.read(_path(cfg, name))
        out[name] = pklite.unpack(data) if pklite.is_packed(data) else data
    return out


def _image(exe):
    return exe[int.from_bytes(exe[8:10], "little") * 16:]


def _menu_widths(strs):
    """{string: its menu's room}: a menu is a run of one-line strings (its title and choices), its room
    the widest."""
    out, run = {}, []
    for si, s in enumerate(strs + [b""]):
        if S.has_text(s) and b"\n" not in s:
            run.append(si)
            continue
        if run:
            w = max(S.cols(strs[k]) for k in run)
            out.update((k, w) for k in run)
        run = []
    return out


def found(vol, cfg, modules=None):
    """[(ref, kind, Japanese text, max cells or None)]."""
    out = []
    entries, _raw, _t = S.gdm(vol.read(_path(cfg, SCENARIO)))
    for ei, e in enumerate(entries):
        _code, strs = S.strings(e)
        menus = _menu_widths(strs)
        for si, s in enumerate(strs):
            if not S.has_text(s):
                continue
            for ui, u in enumerate(S.units(s)):
                if not isinstance(u, S.Unit):
                    continue
                if u.name is not None:
                    out.append(("N:%02d:%d:%d" % (ei, si, ui), "name", S.show(u.name), S.NAME))
                if not S.has_text(u.body()):
                    continue
                if b"\n" not in s:
                    kind, room = "choice", menus[si] - S.cols(u.ws)
                else:
                    kind, room = ("dlg" if u.name is not None else "msg"), None
                out.append(("S:%02d:%d:%d" % (ei, si, ui), kind, S.show(u.body()), room))
    entries, _raw, _t = S.gdm(vol.read(_path(cfg, MUSIC)))
    for ei, e in enumerate(entries):
        if S.is_credits(e):
            for k, line in enumerate(e.split(b"\r\n")):
                if S.has_text(line):
                    out.append(("R:%03d:%d" % (ei, k), "credit", S.show(line.strip(b" \t")), S.LINE))
            continue
        if not S.is_balloons(e):
            continue
        texts, _tail = S.balloons(e)
        for k, t in enumerate(texts):
            if S.has_text(t):
                out.append(("M:%03d:%d" % (ei, k), "balloon", S.show(t), S.BALLOON))
    modules = modules or _modules(vol, cfg)
    for name in MODULES:
        img = _image(modules[name])
        for s, e in S.program_strings(img, name in CONSOLE):
            out.append(("E:%s:%05x" % (name, s), "prog", S.show(img[s:e]), e - s))
    return out


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
    t = re.sub(r"\{[^{}]*\}", "", t)
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


def _pseudo(e):
    if e["kind"] == "prog":
        # (a line each of the Japanese's: a menu keeps its choices)
        return "\n".join(pseudo(e["id"], _cols(line)) if line.strip() else line for line in e["jp"].split("\n"))
    return pseudo(e["id"], _cols(e["jp"]))


def _program_bytes(text, jp):
    """A program string's English: broken at the Japanese's widest line, with its kind of new line (and
    its last new line, if it ends with one)."""
    width = max(S.cols(line) for line in jp.split(b"\n"))
    nl = b"\r\n" if b"\r\n" in jp else b"\n"
    lines = []
    for line in text.rstrip("\n").split("\n"):
        # (a line that fits kept as it is, its spaces with it: a menu's choices)
        plain = S.plain(line)
        lines += [plain] if S.cols(plain) <= width else S.wrap(line, width)
    return nl.join(lines) + (nl if jp.endswith(b"\n") else b"")


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
    if not any(t for _e, t in by_ref.values()):
        img.save(dst)
        print("patched %s (%s mode, no English)" % (dst, mode))
        return
    warn = []
    modules = _modules(vol, cfg)
    # the scenario
    data = vol.read(_path(cfg, SCENARIO))
    entries, raw, table = S.gdm(data)
    names = {}
    for e in doc["strings"]:
        if e["kind"] == "name":
            text = _pseudo(e) if mode == "pseudo" else e["en"]
            if text and len(S.ascii_text(text)) > e["max_cells"]:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(S.ascii_text(text)), e["max_cells"]))
            for r in e["refs"]:
                names[r] = text
    for ei, entry in enumerate(entries):
        code, strs = S.strings(entry)
        wide = S.entry_width(strs)
        changed = False
        for si, s in enumerate(strs):
            if not S.has_text(s):
                continue
            parts = S.units(s)
            texts, tnames = {}, {}
            for ui, u in enumerate(parts):
                if not isinstance(u, S.Unit):
                    continue
                ref = "S:%02d:%d:%d" % (ei, si, ui)
                e, text = by_ref.get(ref, (None, ""))
                english_name = names.get("N:%02d:%d:%d" % (ei, si, ui))
                if english_name and u.name is not None:
                    tnames[u.name] = english_name
                if text:
                    texts[ui] = text
                    if e["kind"] == "choice" and len(S.ascii_text(text)) > e["max_cells"]:
                        warn.append("%s: %d letters, room for %d" % (e["id"], len(S.ascii_text(text)), e["max_cells"]))
                elif english_name and u.name is not None:
                    texts[ui] = None
            if not texts:
                continue
            # (a unit with an English name but no English text keeps its Japanese lines)
            for ui in [k for k, t in texts.items() if t is None]:
                texts[ui] = S.show(parts[ui].body())
            width = 9999 if b"\n" not in s else S.string_width(s, wide)
            strs[si] = S.english_string(parts, texts, tnames, width)
            changed = True
        if changed:
            new = S.entry_bytes(code, strs)
            if len(new) > S.BUFFER:
                raise SystemExit("SCENARIO.GDM entry %d: %d bytes with its English, the script buffer holds %d; "
                                 "shorten its English" % (ei, len(new), S.BUFFER))
            raw[ei] = S.literal(new)
    vol.write(_path(cfg, SCENARIO), S.gdm_bytes(raw, table))
    # the card game's balloons
    data = vol.read(_path(cfg, MUSIC))
    entries, raw, table = S.gdm(data)
    for ei, entry in enumerate(entries):
        if S.is_credits(entry):
            lines = entry.split(b"\r\n")
            changed = False
            for k, line in enumerate(lines):
                e, text = by_ref.get("R:%03d:%d" % (ei, k), (None, ""))
                if text and S.has_text(line):
                    lines[k] = S.credit(line, text)
                    changed = True
            if changed:
                raw[ei] = S.literal(b"\r\n".join(lines))
            continue
        if not S.is_balloons(entry):
            continue
        texts, tail = S.balloons(entry)
        changed = False
        for k, t in enumerate(texts):
            e, text = by_ref.get("M:%03d:%d" % (ei, k), (None, ""))
            if not text:
                continue
            b, n = S.balloon(text)
            if n > S.BALLOON_LINES:
                warn.append("%s: %d lines, room for %d" % (e["id"], n, S.BALLOON_LINES))
                b = b"\r\n".join(b.split(b"\r\n")[:S.BALLOON_LINES])
            texts[k] = b
            changed = True
        if changed:
            raw[ei] = S.literal(S.balloons_bytes(texts, tail))
    vol.write(_path(cfg, MUSIC), S.gdm_bytes(raw, table))
    # the programs
    for name in MODULES:
        exe = modules[name]
        image = _image(exe)
        places = []
        for s, end in S.program_strings(image, name in CONSOLE):
            e, text = by_ref.get("E:%s:%05x" % (name, s), (None, ""))
            if not text:
                continue
            jp = image[s:end]
            room = end - s
            b = _program_bytes(text, jp)
            if len(b) > room:
                warn.append("%s: %d letters, room for %d" % (e["id"], len(b), room))
                b = b[:room]
            places.append((s, b.ljust(room, b"\0")))
        if name in DRAWS or places:
            vol.write(_path(cfg, name), S.patch_module(exe, places, name, buffer=(name == "SPV.BIN"),
                                                       helper=name in DRAWS))
    vol.create(_path(cfg, "MTL_NOTE.TXT"), MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    for w in dict.fromkeys(warn):
        print("warning:", w)
    img.save(dst)
    print("patched %s (%s mode, %d/%d strings translated)" % (
        dst, mode, sum(1 for e in doc["strings"] if e["en"]), len(doc["strings"])))
