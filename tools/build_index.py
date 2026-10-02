"""Build the collection index and attach known English patches.

    python tools/build_index.py

Inputs (all optional except the scan):
  index/scan/*.json                       tools/scan_collection.py (deep scan of the collection)
  index/catalog/*.json, index/folders.json  tools/extract_collection.py (unpacked layout)
  index/collection.json                   the fields of the two above this builder uses; tracked,
                                          refreshed whenever index/scan is present, and the only
                                          scan input a fresh clone needs
  research/ia_translations.json           archive.org/metadata/nec-pc-9801-translations
  research/kairo98_matches.json           Kairo98 catalog/research/matches-v1.json
  research/patches_manual.json            hand-verified extra links:
      {"<Publisher.zip>/<Title>": [{"label": ..., "url": ..., "source": ...}], ...}
Outputs:
  index/index.json   one record per title
  index/INDEX.md     same, grouped by publisher, translated titles marked
"""
import glob
import json
import os
import re
import sys
import urllib.parse
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
IA_ITEM = "nec-pc-9801-translations"
HOMEBREW = "doujinHomebrew.zip"   # grouped by creator; one entry per game here


def p(*a):
    return os.path.join(ROOT, *a)


def load(path, default=None):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def slug(s):
    """Case/punctuation-insensitive key; keeps kana/kanji so Japanese titles stay distinct."""
    import unicodedata
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFKC", s).casefold())


def ia_title(fname):
    """'Alternates/Innocent Tour [T-En by Svipur v1.2] [Censored].zip' -> 'Innocent Tour'"""
    base = fname.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return re.split(r"\s*[\[(]", base, maxsplit=1)[0].strip()


def ia_tags(fname):
    return re.findall(r"\[([^\]]+)\]", fname)


def _md_link(l):
    label = l["label"].replace("|", "/")
    return "[%s](%s)" % (label, l["url"]) if l["url"] else label


MANIFEST_FIELDS = ("inner", "image", "size", "kind", "content_id")


def collection_manifest():
    """The scan data the index is built from, as [{"archive", "extracted",
    "images": [...]}].  index/scan and index/catalog (large, local, untracked)
    win when present, and index/collection.json (tracked) is refreshed from
    them; a fresh clone builds from index/collection.json alone."""
    scans = sorted(glob.glob(p("index", "scan", "*.json")))
    path = p("index", "collection.json")
    if not scans:
        doc = load(path)
        if doc is None:
            sys.exit("no index/scan and no index/collection.json: nothing to build from")
        return doc["archives"]
    extracted = {os.path.basename(f)[:-5] for f in glob.glob(p("index", "catalog", "*.json"))}
    archives = []
    for sf in scans:
        scan = load(sf)
        archives.append({"archive": scan["archive"], "extracted": scan["archive"] in extracted,
                         "images": [{k: r[k] for k in MANIFEST_FIELDS if k in r} for r in scan["images"]]})
    doc = {"_note": "Written by tools/build_index.py from index/scan (tools/scan_collection.py) and "
                    "index/catalog (tools/extract_collection.py), which stay local; the fields "
                    "build_index.py needs, so a fresh clone rebuilds the index.",
           "archives": archives}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("{\n \"_note\": %s,\n \"archives\": [\n" % json.dumps(doc["_note"]))
        f.write(",\n".join("  " + json.dumps(a, ensure_ascii=False, separators=(",", ":")) for a in archives))
        f.write("\n ]\n}\n")
    return archives


def collection():
    """Titles from the deep scan (index/collection.json, see collection_manifest),
    which outlives the deleted zips.  Adds each title's folder under the
    collection root and its disk images with content IDs."""
    from extract_collection import game_of
    folders = load(p("index", "folders.json"), {})
    titles = {}
    for scan in collection_manifest():
        zname = scan["archive"]
        for rec in scan["images"]:
            parts = rec["inner"].split("/")
            if len(parts) < 3:
                continue
            publisher, title, variant = game_of(zname, rec["inner"])
            key = "%s/%s" % (zname, title)
            t = titles.setdefault(key, {"key": key, "archive": zname, "publisher": publisher,
                                        "title": title, "folder": folders.get(key), "media": set(),
                                        "files": [], "images": [], "patches": []})
            inner_name = rec["inner"].split("/", 2)[2]
            if inner_name not in t["files"]:
                t["files"].append(inner_name)
            for tag in re.findall(r"\[([A-Za-z]+)", parts[-1]):
                if tag in ("FD", "HD", "CD", "ROM", "extras"):
                    t["media"].add(tag)
            is_cd_img = rec["image"].lower().endswith(".img") and rec["size"] > 4 << 20
            if (rec.get("kind") in ("hdi", "fd") or "content_id" in rec) and not is_cd_img:
                img = {"variant": variant, "image": rec["image"], "size": rec["size"],
                       "content_id": rec.get("content_id")}
                if scan["extracted"] and t["folder"]:
                    img["path"] = os.path.join(t["folder"], *variant.split("/"), *rec["image"].split("/"))
                t["images"].append(img)
    return titles


def classify_adult(titles, name_to_keys):
    """Set t["heart"] (True = adult content: translated by the user with their
    own model; False = translated in this repo) and t["heart_basis"].
    Precedence: scan of the game's own script text > VNDB > publisher record."""
    from collections import Counter
    by_vndb = defaultdict(list)
    for r in load(p("research", "vndb_p98_all.json"), []):
        names = [r["title"], r.get("alttitle") or ""]
        for v in r["vns"]:
            names += [v["title"], v.get("alttitle") or ""]
        keys = set()
        for n in names:
            if slug(n) and slug(n) in name_to_keys:
                keys |= name_to_keys[slug(n)]
        for k in keys:
            by_vndb[k].append(r)
    text = load(p("research", "adult_text.json"), {})
    pub_votes = defaultdict(Counter)
    for t in titles.values():
        rels = by_vndb.get(t["key"], [])
        if t["key"] in text:
            v = text[t["key"]]
            t["heart"], t["heart_basis"] = v["adult"], "script text: " + v["summary"]
        elif rels:
            ero = [r for r in rels if r["has_ero"] or (r.get("minage") or 0) >= 18]
            t["heart"] = bool(ero)
            r = (ero or rels)[0]
            t["heart_basis"] = "VNDB %s (%s)" % (r["id"], "erotic content" if ero else "no erotic content")
        else:
            t["heart"], t["heart_basis"] = None, None
        if t["heart"] is not None:
            pub_votes[t["publisher"]][t["heart"]] += 1
    for t in titles.values():
        if t["heart"] is None:
            votes = pub_votes[t["publisher"]]
            n = sum(votes.values())
            if n >= 2 and votes[True] / n >= 0.8:
                t["heart"] = True
                t["heart_basis"] = "provisional: %d of %d classified %s titles are adult" % (votes[True], n, t["publisher"])
            else:
                t["heart"] = False
                t["heart_basis"] = "provisional: not listed as adult on VNDB"


def main():
    titles = collection()
    by_group = {"pc98:%s:%s" % (t["archive"], t["title"]): t for t in titles.values()}

    ia = load(p("research", "ia_translations.json"), {"files": []})
    ia_files = [f["name"] for f in ia["files"] if f["name"].endswith(".zip")]
    k98 = load(p("research", "kairo98_matches.json"), {"entries": []})["entries"]
    slug_to_groups = defaultdict(set)
    for e in k98:
        groups = e.get("sourceGroups", [])
        tr = [g.split(":", 1)[1] for g in groups if g.startswith("translated:")]
        own = [g for g in groups if g.startswith("pc98:")]
        for s in tr:
            slug_to_groups[s].update(own)
        # also allow matching by the record's title/aliases
        for name in [e.get("title", "")] + e.get("aliases", []):
            if own and tr and slug(name):
                slug_to_groups[slug(name)].update(own)

    ia_manual = load(p("research", "ia_manual.json"), {})
    unmatched = []
    for f in ia_files:
        s = slug(ia_title(f))
        groups = set(slug_to_groups.get(s, set()))
        groups.update(g for g, t in by_group.items() if slug(t["title"]) == s)
        groups.update("pc98:" + k.replace("/", ":", 1) for k in ia_manual.get(f, []))
        link = {"label": f.rsplit("/", 1)[-1].rsplit(".", 1)[0],
                "url": "https://archive.org/download/%s/%s" % (IA_ITEM, urllib.parse.quote(f)),
                "source": "archive.org PC-98 translation archive (pre-patched)",
                "tags": ia_tags(f)}
        if f.startswith("Incomplete/"):
            link["partial"] = True
            link["label"] += " (incomplete)"
        hit = False
        for g in groups:
            if g in by_group:
                by_group[g]["patches"].append(link)
                hit = True
        if not hit:
            unmatched.append(f)

    # ---- VNDB: English PC-98 releases (api.vndb.org/kana) -------------------
    name_to_keys = defaultdict(set)
    for t in titles.values():
        name_to_keys[slug(t["title"])].add(t["key"])
    for e in k98:
        own = [g for g in e.get("sourceGroups", []) if g.startswith("pc98:") and g in by_group]
        for name in [e.get("title", "")] + e.get("aliases", []):
            for g in own:
                if slug(name):
                    name_to_keys[slug(name)].add(by_group[g]["key"])
    vndb_manual = load(p("research", "vndb_manual.json"), {})
    vndb_unmatched = []
    for r in load(p("research", "vndb_p98_en.json"), []):
        names = [r["title"], r.get("alttitle") or ""]
        for v in r["vns"]:
            names += [v["title"], v.get("alttitle") or ""] + [x["title"] for x in v.get("titles", [])]
        keys = set(vndb_manual.get(r["id"], []))
        if not keys:
            for n in names:
                if slug(n) and slug(n) in name_to_keys:
                    keys |= name_to_keys[slug(n)]
        kind = "fan patch" if r["patch"] else "official English release"
        mtl = any(l.get("mtl") for l in r.get("languages", []) if l["lang"] == "en")
        links = [{"label": "%s: VNDB %s (%s%s)" % (r["title"], r["id"], kind, ", MTL" if mtl else ""),
                  "url": "https://vndb.org/" + r["id"], "source": "VNDB"}]
        links += [{"label": "%s: %s" % (r["title"], x["label"]), "url": x["url"], "source": "VNDB extlink"}
                  for x in r["extlinks"]]
        if not keys:
            vndb_unmatched.append(links[0])
        for k in keys:
            if k not in titles:  # title's archive not scanned yet
                continue
            for l in links:
                if l["url"] not in {x["url"] for x in titles[k]["patches"]}:
                    titles[k]["patches"].append(l)

    # English builds already present in the collection itself
    for t in titles.values():
        for f in t["files"]:
            if re.search(r"\(English|English (patch|version)", f):
                t["patches"].append({"label": "Already in collection: " + f, "url": "",
                                     "source": "collection"})

    manual = load(p("research", "patches_manual.json"), {})
    for key, links in manual.items():
        if key.startswith("_"):
            continue
        if key in titles:
            for l in links:
                if l["url"] not in {x["url"] for x in titles[key]["patches"]}:
                    titles[key]["patches"].append(l)
        else:
            print("manual key not in collection:", key)

    out = sorted(titles.values(), key=lambda t: (t["publisher"].lower(), t["title"].lower()))
    engines = load(p("index", "engines.json"), {})
    classify_adult(titles, name_to_keys)
    announced = load(p("research", "announced.json"), {})
    for t in out:
        t["engine"] = engines.get(t["key"], "unlisted")
        t["media"] = sorted(t["media"])
        human = [l for l in t["patches"] if l.get("source") != "this repo"]
        t["english"] = any(not l.get("wip") and not l.get("partial") for l in human)
        t["in_progress"] = any(l.get("wip") or l.get("partial") for l in human)
        t["announced"] = announced.get(t["key"], [])
        ours = any(l.get("source") == "this repo" for l in t["patches"])
        # skip = a human translation exists, or a team with finished releases announced one
        t["skip"] = t["english"] or any(a["proven"] for a in t["announced"])
        t["status"] = ("human translation" if t["english"] else
                       "announced by proven team" if t["skip"] else
                       "machine translation (this repo)" if ours else
                       "in progress elsewhere" if t["in_progress"] or t["announced"] else "untranslated")
    os.makedirs(p("index"), exist_ok=True)
    n_wip = sum(t["in_progress"] and not t["english"] for t in out)
    json.dump({"titles": out, "unmatched_translations": unmatched, "vndb_unmatched": vndb_unmatched},
              open(p("index", "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    n_en = sum(t["english"] for t in out)
    lines = ["# PC-98 collection index", "",
             "%d titles from %d publisher archives in `E:\\PC98`. **%d have a known English patch** (marked EN); "
             "%d more have a translation in progress." % (len(out), len({t['archive'] for t in out}), n_en, n_wip), "",
             "Generated by `tools/build_index.py`; sources are listed in `index/SOURCES.md`; "
             "engine families (`backticks`) come from `tools/engine_survey.py`, see `index/ENGINES.md`.", "",
             "**♥ = adult content.** Every script is translated by a separate translation model, which also "
             "classifies it; this repo extracts the scripts and builds the patchers. The mark is provisional "
             "(VNDB or publisher record) until the script has been classified; each title's basis is in "
             "`index.json` (`heart_basis`).", "",
             "## Titles with English patches", ""]
    lines += ["| Publisher | Title | Media | Patches |", "|---|---|---|---|"]
    for t in out:
        if t["english"]:
            lines.append("| %s | %s%s | %s | %s |" % (t["publisher"], "♥ " if t["heart"] else "", t["title"],
                         " ".join(t["media"]), "<br>".join(_md_link(l) for l in t["patches"])))
    lines += ["", "## Announced by teams with finished releases (this repo skips these)", "",
              "| Publisher | Title | Team | Status | Source |", "|---|---|---|---|---|"]
    for t in out:
        for a in t["announced"]:
            if a["proven"] and not t["english"]:
                lines.append("| %s | %s | %s | %s (checked %s) | [link](%s) |" % (
                    t["publisher"], t["title"], a["team"], a["status"], a["checked"], a["url"]))
    lines += ["", "## Translations in progress elsewhere (no finished English patch)", "",
              "| Publisher | Title | Media | Projects |", "|---|---|---|---|"]
    for t in out:
        if t["in_progress"] and not t["english"]:
            lines.append("| %s | %s | %s | %s |" % (t["publisher"], t["title"], " ".join(t["media"]),
                         "<br>".join(_md_link(l) for l in t["patches"] if l.get("source") != "this repo")))
    lines += ["", "## Machine translations in this repo", "",
              "AI/MTL-driven, not human translations. Each is retired when a human translation appears.", "",
              "| Publisher | Title | Status |", "|---|---|---|"]
    for t in out:
        for l in t["patches"]:
            if l.get("source") == "this repo":
                lines.append("| %s | %s | %s |" % (t["publisher"], t["title"], _md_link(l)))
    if unmatched:
        lines += ["", "## Translations not yet matched to a collection title", ""]
        lines += ["- [%s](https://archive.org/download/%s/%s)" % (f, IA_ITEM, urllib.parse.quote(f)) for f in unmatched]
    lines += ["", "## Full collection", ""]
    cur = None
    for t in out:
        if t["publisher"] != cur:
            cur = t["publisher"]
            lines += ["", "### %s (`%s`)" % (cur, t["archive"]), ""]
        mark = {"human translation": " — **EN**", "announced by proven team": " — *announced (skip)*",
                "machine translation (this repo)": " — *MTL (this repo)*",
                "in progress elsewhere": " — *in progress elsewhere*"}.get(t["status"], "")
        eng = "" if t["engine"] in ("unknown", "unlisted") else " `%s`" % t["engine"]
        lines.append("- %s%s [%s]%s%s" % ("♥ " if t["heart"] else "", t["title"], " ".join(t["media"]), eng, mark))
    open(p("index", "INDEX.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("%d titles, %d with English patches, %d archive / %d VNDB entries unmatched"
          % (len(out), n_en, len(unmatched), len(vndb_unmatched)))


if __name__ == "__main__":
    main()
