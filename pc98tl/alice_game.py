"""Shared extract/patch driver for Alice Soft System 2/3 games.

A game folder holds game.json:
  {"title": ..., "key": "<index key>", "game_dir": "BEE", "version": 3,
   "encoding": "halfkana", "config": {...optional Sys2Game overrides}}
and thin extract.py / patch.py wrappers that call run_extract / run_patch.
"""
import json
import os
import re

from .disk import DiskImage
from .alice_sys2_tl import Sys2Game, sha256, set_kana_table
from . import alice3_font, alice2_font, alice1_text
from .alice_exe import find_strings, apply_strings

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


def _games(here, img, src=None):
    """One Sys2Game per scenario set.  Without "sets": a single game.  With
    "sets" (e.g. Super D.P.S): the shared ADISK pages once, then each set's
    own disks, e.g. {"prefix": "s1:", "disks": {"2": "SDPS/SDPS0001/BDISK.DAT"}}."""
    cfg = json.load(open(os.path.join(here, "game.json"), encoding="utf-8"))
    vol = img.volumes[0]
    conf = dict(cfg.get("config", {}))
    conf.setdefault("encoding", cfg["encoding"])
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
        g = Sys2Game(set_vol, cfg["game_dir"], version=cfg["version"], config=conf,
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
    prefix = {"msg": "m", "menu": "u", "name": "n", "verb": "v", "obj": "o", "exe": "e"}
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


def _exe_strings(cfg, adv):
    return find_strings(adv, add=[int(a, 16) for a in cfg.get("exe_add", [])],
                        skip=[int(a, 16) for a in cfg.get("exe_skip", [])])


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


def run_patch(here, src, dst, mode="en"):
    doc = json.load(open(os.path.join(here, "strings.json"), encoding="utf-8"))
    if sha256(src) != doc["source_image_sha256"]:
        print("warning: source image differs from the one strings.json was extracted from")
    img = DiskImage(src)
    cfg, vol, games = _games(here, img, src)
    report = []
    for g in games:
        g.patch(doc, mode=mode, report=report)
    adv_path = _adv_path(cfg)
    adv = vol.read(adv_path)
    exe = [e for e in doc["strings"] if e["kind"] == "exe"]
    texts = {int(e["refs"][0][4:], 16): e["en"] for e in exe if e["en"]}
    sizes = {int(e["refs"][0][4:], 16): e["max_bytes"] for e in exe}
    adv, warn = apply_strings(adv, texts, games[0].enc.encode, sizes)
    report += warn
    if cfg["encoding"] == "halfkana":
        adv = alice3_font.build(adv)
    elif cfg["encoding"] == "packed":
        adv = alice2_font.build(adv)
    elif cfg["encoding"] == "textvram":
        adv = alice1_text.build(adv)
    vol.write(adv_path, adv)
    vol.create((cfg["game_dir"] + "/" if cfg["game_dir"] else "") + "MTL_NOTE.TXT",
               MTL_NOTE.format(title=cfg["title"]).replace("\n", "\r\n").encode("ascii"))
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
