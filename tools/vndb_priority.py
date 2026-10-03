"""Order a family's untranslated titles by VNDB vote count.

    python tools/vndb_priority.py <family> (--engine <engine id> | --keys <key> ...)

Titles come from index/index.json (status "untranslated"; with --engine,
every title of that engine family).  Each is matched to VNDB through the
PC-98 release list (research/vndb_p98_all.json, by title the way
build_index.py matches), falling back to a VNDB title search; the vote
counts of its VNs are summed.  The ranking goes to research/priority.json
under <family>, most votes first; unmatched titles get 0 votes and keep
index order at the end.
"""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from build_index import slug  # noqa: E402

API = "https://api.vndb.org/kana/vn"


def _post(payload):
    req = urllib.request.Request(API, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 + 3 * attempt)
    raise RuntimeError("VNDB API did not answer")


def votecounts(ids):
    out = {}
    ids = sorted(set(ids))
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        filt = ["or"] + [["id", "=", v] for v in chunk] if len(chunk) > 1 else ["id", "=", chunk[0]]
        res = _post({"filters": filt, "fields": "votecount", "results": 100})
        out.update({r["id"]: r["votecount"] or 0 for r in res["results"]})
    return out


def search(title):
    """A VNDB title search: the full title, then without its subtitle or
    parenthetical; a result counts when one title holds the other."""
    import re
    queries = [title, title.split(" - ")[0], re.sub(r"\s*\(.*?\)", "", title)]
    for q in dict.fromkeys(q.strip() for q in queries if q.strip()):
        res = _post({"filters": ["search", "=", q], "fields": "title,alttitle,votecount", "results": 10})
        want = slug(q)
        for r in res["results"]:
            for name in (r["title"], r.get("alttitle") or ""):
                got = slug(name)
                if got and len(min(got, want, key=len)) >= 4 and (got == want or want in got or got in want):
                    return r["id"]
    return None


def main():
    args = sys.argv[1:]
    family = args[0]
    index = json.load(open(os.path.join(ROOT, "index", "index.json"), encoding="utf-8"))["titles"]
    if args[1] == "--engine":
        titles = [t for t in index if t["engine"] == args[2] and t["status"] == "untranslated"]
    else:
        keys = args[2:]
        titles = [t for k in keys for t in index if t["key"] == k]
    by_name = {}
    for r in json.load(open(os.path.join(ROOT, "research", "vndb_p98_all.json"), encoding="utf-8")):
        names = [r["title"], r.get("alttitle") or ""] + [n for v in r["vns"] for n in (v["title"], v.get("alttitle") or "")]
        for n in names:
            if slug(n):
                by_name.setdefault(slug(n), set()).update(v["id"] for v in r["vns"])
    vns = {}
    for t in titles:
        ids = by_name.get(slug(t["title"]), set())
        if not ids or not sum(votecounts(sorted(ids)).values()):
            v = search(t["title"])
            ids = {v} if v else set()
        vns[t["key"]] = sorted(ids)
    counts = votecounts([v for ids in vns.values() for v in ids]) if any(vns.values()) else {}
    rows = [{"key": t["key"], "title": t["title"], "vndb": vns[t["key"]],
             "votes": sum(counts.get(v, 0) for v in vns[t["key"]])} for t in titles]
    order = sorted(range(len(rows)), key=lambda i: (-rows[i]["votes"], i))
    path = os.path.join(ROOT, "research", "priority.json")
    doc = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    doc[family] = {"checked": time.strftime("%Y-%m-%d"), "basis": "VNDB vote count (sum over the title's VNs)",
                   "titles": [rows[i] for i in order]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    for i in order:
        print("%5d  %s" % (rows[i]["votes"], rows[i]["title"]))


if __name__ == "__main__":
    main()
