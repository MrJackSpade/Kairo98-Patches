"""Clearance checks (DEFINITION_OF_DONE.md section 1) for titles, into
research/clearance.json.

    python tools/clearance.py <family> [<count>]
    python tools/clearance.py --add-search <key> "<what the web search found>"

<family> is a family in research/priority.json; the first <count> titles
(default all) are checked:
* VNDB: English releases of the title's VNs, with their platforms.  Only a
  PC-98 English release stops work (a release for another platform is
  linked and its script may be ported).
* The proven teams' translation pages (index/TEAMS.md's sources): whether
  the title is listed.
* GitHub: repositories whose name or description holds the title.
The result is "clear" unless VNDB lists a PC-98 English release or a team
page lists the title; then it is "review" with the evidence, to be settled
by hand.  The web search is recorded with --add-search.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from build_index import slug  # noqa: E402

TEAM_PAGES = ["https://baba-jpc.neocities.org/translations/translations", "https://alpharobo.neocities.org/"]
PATH = os.path.join(ROOT, "research", "clearance.json")


def _get(url, data=None, headers=None):
    req = urllib.request.Request(url, data, headers or {"User-Agent": "Kairo98-Patches clearance"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            time.sleep(2 + 3 * attempt)
    return None


def vndb_english(vns):
    """[(release title, [platforms])] of the VNs' English releases."""
    if not vns:
        return []
    filt = ["and", ["lang", "=", "en"], ["or"] + [["vn", "=", ["id", "=", v]] for v in vns]] if len(vns) > 1 \
        else ["and", ["lang", "=", "en"], ["vn", "=", ["id", "=", vns[0]]]]
    body = json.dumps({"filters": filt, "fields": "title,platforms", "results": 50}).encode()
    raw = _get("https://api.vndb.org/kana/release", body, {"Content-Type": "application/json"})
    if raw is None:
        raise RuntimeError("VNDB did not answer")
    return [(r["title"], r["platforms"]) for r in json.loads(raw)["results"]]


_pages = {}


def team_hits(title):
    want = slug(title.split(" - ")[0])
    out = []
    for url in TEAM_PAGES:
        if url not in _pages:
            raw = _get(url)
            _pages[url] = slug(raw.decode("utf-8", "replace")) if raw else None
        page = _pages[url]
        if page is None:
            out.append("%s: not reachable" % url)
        elif len(want) >= 5 and want in page:
            out.append("%s: LISTED" % url)
        else:
            out.append("%s: not listed" % url)
    return out


def github(title):
    q = urllib.parse.quote('"%s" translation' % title.split(" - ")[0])
    raw = _get("https://api.github.com/search/repositories?q=%s&per_page=5" % q)
    if raw is None:
        return "GitHub search: no answer"
    items = json.loads(raw).get("items", [])
    if not items:
        return "GitHub search (title + translation): nothing"
    return "GitHub search (title + translation): " + "; ".join(i["full_name"] for i in items)


def main():
    doc = json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else {}
    if sys.argv[1] == "--add-search":
        key, found = sys.argv[2], sys.argv[3]
        doc[key]["sources"].append("web search (title + English translation, PC-98): " + found)
    else:
        family = sys.argv[1]
        count = int(sys.argv[2]) if len(sys.argv) > 2 else None
        titles = json.load(open(os.path.join(ROOT, "research", "priority.json"), encoding="utf-8"))[family]["titles"]
        for t in titles[:count]:
            if t["key"] in doc:
                continue
            day = time.strftime("%Y-%m-%d")
            en = vndb_english(t["vndb"])
            pc98 = [r for r in en if "pc9" in r[1]]
            teams = team_hits(t["title"])
            sources = ["VNDB API %s: %s" % (day, "no English release on any platform" if not en else
                                             "English releases: " + "; ".join("%s (%s)" % (n, ", ".join(p))
                                                                             for n, p in en))]
            sources += teams + [github(t["title"])]
            result = "review" if pc98 or any("LISTED" in s for s in teams) else "clear"
            doc[t["key"]] = {"checked": day, "result": result, "sources": sources}
            print("%-7s %s" % (result, t["title"]))
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
