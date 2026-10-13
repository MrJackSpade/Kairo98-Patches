"""Classify every title by game engine from the files inside its disk images.

    python tools/engine_survey.py

Reads index/scan/*.json (file listings of HDI/HDM images).  Floppy images the
scanner couldn't list (D88/FDI) are opened from the unpacked collection when
available.  Writes index/engines.json ({title key: engine id}) and
index/ENGINES.md (families ranked by untranslated titles).
"""
import glob
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from extract_collection import game_of  # noqa: E402

COLLECTION = r"E:\PC98"
DOS_DIRS = ("DOS/", "TOOLS/", "WINDOWS/", "BIN/", "UTIL/", "DRIVER/")

# (id, family name, note, test(names, exts, publisher)).  First match wins.
ENGINES = [
    ("alice-sys", "Alice Soft System 1-3", "ADISK.DAT scenario; Dalk is done (games/dalk)",
     lambda n, e, p: "ADISK.DAT" in n),
    ("adv98v", "Cocktail Soft / Fairytale ADV engine", "*.MES + *.TCM/*.GPC/*.USO, ADV98V.OVL or ADVH.EXE; cracked by existing patches (Dead of the Brain, Dengeki Nurse, X-Girl)",
     lambda n, e, p: "ADV98V.OVL" in n or "ADVH.EXE" in n or ("TCM" in e and ("GPC" in e or "USO" in e)) or ("USO" in e and "MES" in e)),
    ("elf-ai5", "Elf AI5", "AI5.EXE, *.MES scripts",
     lambda n, e, p: "AI5.EXE" in n or ("START.MES" in n and ("S4" in e or "M" in e) and p in ("elf", "Silky's"))),
    ("silkys", "Silky's SIL engine", "SIL.EXE / SILKn.DAT",
     lambda n, e, p: "SIL.EXE" in n or any(re.fullmatch(r"SILK\d\.DAT", x) for x in n)),
    ("elf-other", "Elf (pre-AI5)", "older Elf engines",
     lambda n, e, p: p == "elf"),
    ("dante98", "RPG Tsukuru Dante98", "RPG.EXE + PLAYER/ENEMY/ITEM.DAT (contest RPGs)",
     lambda n, e, p: "RPG.EXE" in n and "PLAYER.DAT" in n),
    ("sogna-sgs", "Sogna / Silence SGS", "SGS.COM, *.SZH",
     lambda n, e, p: "SGS.COM" in n or "SZH" in e),
    ("compile-ds", "Compile Disc Station shell", "S_TXT.COM, DSH.COM",
     lambda n, e, p: "S_TXT.COM" in n or "DSH.COM" in n),
    ("do", "D.O. engine", "DA/DB/DO + ORDER.DEF, *.GF",
     lambda n, e, p: "ORDER.DEF" in n or ({"DA", "DO"} <= n and "GF" in e)),
    ("active", "Active AGG/ADV", "*.AGG + *.ADV",
     lambda n, e, p: "AGG" in e and "ADV" in e),
    ("jast", "JAST MEGSHL", "MEGSHL.COM, JAST.FNT",
     lambda n, e, p: "MEGSHL.COM" in n or "JAST.FNT" in n),
    ("cdos98", "CDOS98 shell (Mediax / Fairy Dust)", "CDOS98.COM + SHELL.RC, *.SCR",
     lambda n, e, p: "CDOS98.COM" in n or "SHELL.RC" in n),
    ("mink", "Mink", "NAX.COM + *.GPP",
     lambda n, e, p: "NAX.COM" in n and "GPP" in e),
    ("great-na", "NA.COM engine (Great / KSS)", "NA.COM + *.O + TONES.DTA",
     lambda n, e, p: "NA.COM" in n and "O" in e),
    ("bio100", "Bio_100% (doujin)", "*.EFS/*.SCR/*.FNT",
     lambda n, e, p: p == "Bio_100%"),
    ("tmexec", "TMEXEC engine (Illusion / Heart Soft / Interheart / Dott Plan)", "TMEXEC.ASC, SDN.COM, BGMnn.X",
     lambda n, e, p: "TMEXEC.ASC" in n or "SDN.COM" in n),
    ("ascii-rpgkit", "ASCII contest RPG kit", "BGM_A..Z.MML + KAn.ANI",
     lambda n, e, p: "KA1.ANI" in n and "BGM_A.MML" in n),
    ("n88basic", "N88-BASIC programs", "N88BASIC.EXE / .LIB runtime",
     lambda n, e, p: "N88BASIC.EXE" in n or "N88BASIC.LIB" in n),
]


def names_of(files):
    names, exts = set(), set()
    for path, _size in files:
        if path.upper().startswith(DOS_DIRS):
            continue
        b = path.rsplit("/", 1)[-1].upper()
        names.add(b)
        if "." in b:
            exts.add(b.rsplit(".", 1)[-1])
    return names, exts


def main():
    folders = json.load(open(os.path.join(ROOT, "index", "folders.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(ROOT, "index", "folders.json")) else {}
    titles = defaultdict(lambda: {"names": set(), "exts": set(), "publisher": None, "unlisted": []})
    for sf in glob.glob(os.path.join(ROOT, "index", "scan", "*.json")):
        scan = json.load(open(sf, encoding="utf-8"))
        for r in scan["images"]:
            if r.get("kind") not in ("hdi", "fd") and "content_id" not in r:
                continue
            pub, title, variant = game_of(scan["archive"], r["inner"])
            key = "%s/%s" % (scan["archive"], title)
            t = titles[key]
            t["publisher"] = pub
            if r.get("files"):
                n, e = names_of(r["files"])
                t["names"] |= n
                t["exts"] |= e
            elif key in folders:
                t["unlisted"].append(os.path.join(COLLECTION, folders[key], *variant.split("/"), *r["image"].split("/")))

    from pc98tl.disk import DiskImage
    opened = 0
    for key, t in titles.items():
        if t["names"] or not t["unlisted"]:
            continue
        for path in t["unlisted"]:
            try:
                img = DiskImage(path)
                files = [[p, ent["size"]] for v in img.volumes for p, ent in v.walk() if not p.endswith("/")]
            except Exception:  # noqa: BLE001 - unreadable/non-DOS disk
                continue
            n, e = names_of(files)
            t["names"] |= n
            t["exts"] |= e
            opened += 1

    result = {}
    for key, t in titles.items():
        eng = "unknown" if t["names"] else "unlisted"
        for eid, _name, _note, test in ENGINES:
            if t["names"] and test(t["names"], t["exts"], t["publisher"]):
                eng = eid
                break
        result[key] = eng
    json.dump(result, open(os.path.join(ROOT, "index", "engines.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)

    index = json.load(open(os.path.join(ROOT, "index", "index.json"), encoding="utf-8"))["titles"]
    english = {t["key"] for t in index if t["english"]}
    by = defaultdict(list)
    for key, eng in result.items():
        by[eng].append(key)
    meta = {e[0]: (e[1], e[2]) for e in ENGINES}
    meta["unknown"] = ("Not yet identified", "files listed, no rule matched; per-publisher engines")
    meta["unlisted"] = ("No readable file listing", "copy-protected / non-DOS floppies, CD-only titles")
    rows = sorted(by.items(), key=lambda kv: -sum(k not in english for k in kv[1]))
    lines = ["# Engine survey", "",
             "%d titles classified from the files inside their disk images (%d floppies opened directly). "
             "Families are ranked by how many titles without an English patch they cover." % (len(result), opened), "",
             "| Engine | Titles | Have English | Untranslated | Notes |", "|---|---|---|---|---|"]
    for eng, keys in rows:
        name, note = meta[eng]
        en = sum(k in english for k in keys)
        lines.append("| %s (`%s`) | %d | %d | %d | %s |" % (name, eng, len(keys), en, len(keys) - en, note))
    for eng, keys in rows:
        if eng in ("unknown", "unlisted"):
            continue
        lines += ["", "## %s" % meta[eng][0], ""]
        for k in sorted(keys, key=str.lower):
            lines.append("- %s%s" % (k.split("/", 1)[1], " — **EN**" if k in english else ""))
    open(os.path.join(ROOT, "index", "ENGINES.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    for eng, keys in rows:
        print("%-12s %5d titles, %4d untranslated" % (eng, len(keys), sum(k not in english for k in keys)))


if __name__ == "__main__":
    main()
