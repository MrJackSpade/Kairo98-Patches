"""Shared extract/patch driver for Alice Soft System 2/3 games.

A game folder holds game.json:
  {"title": ..., "key": "<index key>", "game_dir": "BEE", "version": 3,
   "encoding": "halfkana", "config": {...optional Sys2Game overrides},
   "demos": ["BEE_DEMO.COM", ...optional opening/demo programs in game_dir]}
and thin extract.py / patch.py wrappers that call run_extract / run_patch.
"""
import json
import os
import re

from .disk import DiskImage
from .alice_sys2_tl import Sys2Game, sha256, set_kana_table
from . import alice3_font, alice2_font, alice1_text, dosmem
from .alice_exe import find_strings, apply_strings, widen
from .text import pseudo

ORG = 0x100
COLLECTION = os.environ.get("PC98_ROOT", r"C:\PC98")

MTL_NOTE = """{title} - English patch (machine translation)

The English script in this patch is a MACHINE TRANSLATION (AI/MTL), not a
human translation. It was made so the game can be played at all. If a human
translation is released, use that instead; this patch will be retired.

Made with the PC-98 translation kit (Kairo98-Patches).
"""


def kana_table(adv):
    """ADV.COM's half-width kana -> displayed full-width table (64 words)."""
    at = adv.find(bytes.fromhex("4081428175817681418145"))
    if at < 0:
        return None
    t = adv[at:at + 128]
    return [bytes([t[i + 1], t[i]]).decode("cp932", "replace") for i in range(0, 128, 2)]


def _games(here, img, src=None, cfg=None):
    """One Sys2Game per scenario set.  Without "sets": a single game.  With
    "sets" (e.g. Super D.P.S): the shared ADISK pages once, then each set's
    own disks, e.g. {"prefix": "s1:", "disks": {"2": "SDPS/SDPS0001/BDISK.DAT"}}.
    A set may name its own command table ("version"), e.g. a sub-game run by a
    second engine from its own scenario file."""
    if cfg is None:
        cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = img.volumes[0]
    conf = dict(cfg.get("config", {}))
    conf.setdefault("encoding", cfg["encoding"])
    if cfg["encoding"] == "packed":  # message cell width comes from the engine
        conf.setdefault("font_px", alice2_font.font_px(vol.read(_adv_path(cfg))))
    if not cfg.get("sets"):
        return cfg, vol, [Sys2Game(vol, cfg["game_dir"], version=cfg["version"], config=conf)]
    games = [Sys2Game(vol, cfg["game_dir"], version=cfg["version"], config=conf, scope={1})]
    for st in cfg["sets"]:
        disks = {int(k): v for k, v in st["disks"].items()}
        set_vol, set_img = vol, None
        if st.get("image"):  # scenario on its own floppy, next to the main image
            base = os.path.dirname(src) if src else os.path.join(COLLECTION, os.path.dirname(cfg["image"]))
            set_img = DiskImage(os.path.join(base, st["image"]))
            set_vol = set_img.volumes[0]
            # the shared link table lives on the main image's ADISK.DAT
            disks = dict(disks)
        g = Sys2Game(set_vol, cfg["game_dir"], version=st.get("version", cfg["version"]), config=conf,
                     disks=disks, scope=set(disks), prefix=st["prefix"],
                     adisk_bytes=vol.read((cfg["game_dir"] + "/" if cfg["game_dir"] else "") + "ADISK.DAT")
                     if set_img else None)
        g.set_image, g.set_name = set_img, st.get("image")
        games.append(g)
    return cfg, vol, games


def _merge(docs):
    """Merge extract() results of several scenario sets into one document."""
    merged, order = {}, []
    for doc in docs:
        for e in doc["strings"]:
            key = (e["kind"], e["jp"])
            if key in merged:
                merged[key]["refs"] += e["refs"]
                merged[key]["max_cells"] = min(merged[key]["max_cells"], e["max_cells"])
            else:
                merged[key] = dict(e)
                order.append(key)
    prefix = {"msg": "m", "menu": "u", "name": "n", "verb": "v", "obj": "o", "exe": "e", "demo": "d"}
    counters, out = {}, []
    for key in order:
        e = merged[key]
        counters[e["kind"]] = counters.get(e["kind"], 0) + 1
        e["id"] = "%s%05d" % (prefix.get(e["kind"], "x"), counters[e["kind"]])
        out.append(e)
    doc = dict(docs[0])
    doc["strings"] = out
    return doc


def _adv_path(cfg):
    return (cfg["game_dir"] + "/" if cfg["game_dir"] else "") + cfg.get("engine", "ADV.COM")


def _kana(cfg, prog):
    """(display table, full-width codes) for a System 3 program whose kana
    table the English patch remaps; (None, None) otherwise."""
    if cfg["encoding"] != "halfkana":
        return None, None
    at = prog.find(bytes.fromhex("4081428175817681418145"))
    if at < 0:
        return None, None
    words = [bytes([prog[at + i + 1], prog[at + i]]) for i in range(0, 128, 2)]
    return [w.decode("cp932", "replace") for w in words], words


def _keep(cfg, prog):
    words = _kana(cfg, prog)[1]
    return (lambda raw: widen(raw, words)) if words else None


def _exe_strings(cfg, adv):
    return find_strings(adv, kana=_kana(cfg, adv)[0], add=[int(a, 16) for a in cfg.get("exe_add", [])],
                        skip=[int(a, 16) for a in cfg.get("exe_skip", [])])


def _prog_path(cfg, name):
    return (cfg["game_dir"] + "/" if cfg["game_dir"] else "") + name


def _cells(jp):
    return sum(1 if ord(c) < 0x80 else 2 for c in jp) // 2


def run_extract(here, src):
    out = os.path.join(here, "strings.json")
    img = DiskImage(src)
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    table = kana_table(img.volumes[0].read(_adv_path(cfg)))
    if table:
        set_kana_table(table)
    cfg, vol, games = _games(here, img, src)
    docs = [g.extract(cfg["title"], sha256(src)) for g in games]
    doc = docs[0] if len(docs) == 1 else _merge(docs)
    adv = vol.read(_adv_path(cfg))
    for n, st in enumerate(_exe_strings(cfg, adv), 1):
        doc["strings"].append({"id": "e%05d" % n, "kind": "exe", "jp": st["jp"], "en": "",
                               "refs": ["adv:%04x" % st["addr"]], "max_bytes": st["max_bytes"]})
    n = 0
    for name in cfg.get("demos", []):  # opening/demo programs: same in-place rules
        prog = vol.read(_prog_path(cfg, name))
        for st in find_strings(prog, kana=_kana(cfg, prog)[0]):
            n += 1
            doc["strings"].append({"id": "d%05d" % n, "kind": "demo", "jp": st["jp"], "en": "",
                                   "refs": ["demo:%s:%04x" % (name, st["addr"])],
                                   "max_bytes": st["max_bytes"], "max_cells": _cells(st["jp"])})
    if os.path.exists(out):  # keep translations and hand-tuned fields
        old = {(e["kind"], e["jp"]): e for e in json.load(open(out, encoding="utf-8"))["strings"]}
        for e in doc["strings"]:
            prev = old.get((e["kind"], e["jp"]))
            if prev:
                for k in ("en", "max_cells", "note"):
                    if k in prev:
                        e[k] = prev[k]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    kinds = {}
    for e in doc["strings"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print("wrote %s: %d strings %s" % (out, len(doc["strings"]), kinds))


def _fixed(e, mode):
    """Text for a string replaced in place: the translation, or in pseudo mode
    filler exactly as wide as the Japanese (these slots cannot grow)."""
    if mode == "pseudo":
        return pseudo(e["id"], sum(1 if ord(c) < 0x80 else 2 for c in e["jp"]), factor=2.0)
    return e["en"]


def _font(cfg, prog, room=0x1000):
    """Add the English display patch for the game's encoding to a program."""
    if cfg["encoding"] == "halfkana":
        return alice3_font.build(prog, room=room)
    if cfg["encoding"] == "packed":
        return alice2_font.build(prog, room=room)
    if cfg["encoding"] == "textvram":
        return alice1_text.build(prog)
    return prog


def _strings_and_font(cfg, prog, texts, sizes, encode, label, report, room=0x1000):
    """Display patch first, then the strings: a run too long for its place
    spills into the memory between the hook and the moved stack.  Opening
    demos get more room, since their narration is mostly 1-byte kana that
    English outgrows."""
    keep = _keep(cfg, prog)                     # from the original kana table
    patched = _font(cfg, prog, room)
    top = dosmem.stack_top(patched)
    spill = (ORG + len(patched), top - 0x400) if top else None
    out, warn = apply_strings(patched, texts, encode, sizes, label=label, keep=keep, spill=spill)
    report += warn
    return out


DOS_FILES = {"IO.SYS", "MSDOS.SYS", "COMMAND.COM", "CONFIG.SYS", "AUTOEXEC.BAT"}


def _hdd_install(cfg, src):
    """For floppy games whose scenario disks can't hold a long English script
    (D.P.S SG Set 2/3): lay the game out on a DOS hard-disk image the way its
    own HDD installer does, and return (image, config for patching there).

    cfg["hdd"]: {"base": DOS hard-disk image (relative to the collection),
    "remove": [base's own game files], "dir": install directory,
    "rename": {system-disk file: root name} (e.g. the installer's SET2A.ORG
    that becomes \\SET2.BAT), "run": the command AUTOEXEC.BAT ends with,
    "order": set prefixes in the installer's scenario order (optional)}.
    Each scenario set goes to <dir>/SNR<n> (its xDISK/xCG/xMUS files), and
    set 1 is also the default copy in <dir>, as after installation."""
    h = cfg["hdd"]
    img = DiskImage(os.path.join(COLLECTION, h["base"]))
    vol = img.volumes[0]
    for name in h.get("remove", []):
        vol.delete(name)
    sysvol = DiskImage(src).volumes[0]
    d = h["dir"]
    vol.mkdir(d)
    for e in sysvol.listdir(0):
        if e["is_dir"] or e["name"].upper() in DOS_FILES:
            continue
        data = sysvol.read(e["name"])
        vol.create(h.get("rename", {}).get(e["name"].upper(), d + "/" + e["name"]), data)
    base = os.path.dirname(src)
    sets = []
    order = h.get("order")  # set prefixes in the installer's SNR order
    ordered = sorted(cfg["sets"], key=lambda st: order.index(st["prefix"])) if order else cfg["sets"]
    for n, st in enumerate(ordered, 1):
        setvol = DiskImage(os.path.join(base, st["image"])).volumes[0]
        snr = "%s/SNR%d" % (d, n)
        vol.mkdir(snr)
        letters = {os.path.basename(p)[0].upper() for p in st["disks"].values()}
        for e in setvol.listdir(0):
            nm = e["name"].upper()
            if nm[0] in letters and nm[1:] in ("DISK.DAT", "CG.DAT", "MUS.DAT"):
                vol.create(snr + "/" + nm, setvol.read(e["name"]))
        sets.append({"prefix": st["prefix"], "disks": {k: "%s/%s" % (snr, os.path.basename(p).upper())
                                                        for k, p in st["disks"].items()}})
    auto = vol.read("AUTOEXEC.BAT").decode("cp932").split("\r\n")
    gone = {os.path.splitext(r)[0].upper() for r in h.get("remove", [])}
    auto = [h["run"] if ln.strip().upper() in gone else ln for ln in auto]
    vol.write("AUTOEXEC.BAT", "\r\n".join(auto).encode("cp932"))
    pcfg = dict(cfg, game_dir=d, sets=sets)
    return img, pcfg


def _hdd_default_set(cfg, vol):
    """Refresh the default scenario copy in the install directory from SNR1."""
    for p in cfg["sets"][0]["disks"].values():
        snr = os.path.dirname(p)
        for e in vol.listdir(vol.find(snr)["cluster"]):
            vol.create(cfg["game_dir"] + "/" + e["name"], vol.read(snr + "/" + e["name"]))


def run_patch(here, src, dst, mode="en"):
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    if cfg.get("hdd"):
        img, pcfg = _hdd_install(cfg, src)
        cfg, vol, games = _games(here, img, src, pcfg)
    else:
        img = DiskImage(src)
        cfg, vol, games = _games(here, img, src)
    report = []
    for g in games:
        g.patch(doc, mode=mode, report=report)
    adv_path = _adv_path(cfg)
    adv = vol.read(adv_path)
    exe = [e for e in doc["strings"] if e["kind"] == "exe"]
    texts = {int(e["refs"][0][4:], 16): _fixed(e, mode) for e in exe if _fixed(e, mode)}
    sizes = {int(e["refs"][0][4:], 16): e["max_bytes"] for e in exe}
    vol.write(adv_path, _strings_and_font(cfg, adv, texts, sizes, games[0].enc.encode, "ADV.COM", report))
    for name in cfg.get("demos", []):
        path = _prog_path(cfg, name)
        ents = [e for e in doc["strings"] if e["kind"] == "demo" and e["refs"][0].split(":")[1] == name]
        texts = {int(e["refs"][0].split(":")[2], 16): _fixed(e, mode) for e in ents if _fixed(e, mode)}
        sizes = {int(e["refs"][0].split(":")[2], 16): e["max_bytes"] for e in ents}
        vol.write(path, _strings_and_font(cfg, vol.read(path), texts, sizes, games[0].enc.encode, name,
                                          report, room=0x2000))
    vol.create((cfg["game_dir"] + "/" if cfg["game_dir"] else "") + "MTL_NOTE.TXT",
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
    if cfg.get("hdd"):
        _hdd_default_set(cfg, vol)
    img.save(dst)
    stem, ext = os.path.splitext(dst)
    for g in games:  # scenario floppies patched alongside the main image
        if getattr(g, "set_image", None) is not None:
            extra = "%s - %s" % (stem, os.path.basename(g.set_name))
            g.set_image.save(extra)
            print("patched %s" % extra)
    done = sum(1 for e in doc["strings"] if e["en"])
    print("patched %s (%s mode, %d/%d strings translated)" % (dst, mode, done, len(doc["strings"])))
    for line in report:
        print("  " + line)
