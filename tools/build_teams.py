"""Write index/TEAMS.md: every translation team with finished releases, their
home pages, their releases (with links) and their announced projects.

    python tools/build_teams.py      (run after tools/build_index.py)
"""
import json
import os
import re
import urllib.parse

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
IA_ITEM = "nec-pc-9801-translations"


def load(*parts):
    path = os.path.join(ROOT, *parts)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def main():
    ia = load("research", "ia_translations.json").get("files", [])
    links = load("research", "team_links.json")
    announced = load("research", "announced.json")
    releases = {}
    for f in ia:
        n = f["name"]
        if not n.endswith(".zip"):
            continue
        base = n.rsplit("/", 1)[-1][:-4]
        url = "https://archive.org/download/%s/%s" % (IA_ITEM, urllib.parse.quote(n))
        for grp in re.findall(r"\[([^\]]+)\]", n):
            m = re.match(r"(?:T-En(?: v[\d.a-z]+)? by|Port(?: & Add)? by|Add by|Bugfixes by|Real Hardware Fix by)\s+(?:by\s+)?(.*)", grp)
            if not m:
                continue
            s = re.sub(r"\s+v[\d.]+[a-z]*$", "", m.group(1))
            for t in re.split(r",\s*|\s+&\s+|\s+and\s+", s):
                t = re.sub(r"\s+v[\d.]+.*$|\s+RC\d+$", "", t.strip())
                if t:
                    releases.setdefault(t, []).append((base, url, n.startswith("Incomplete/")))
    ann_by_team = {}
    for key, items in announced.items():
        if key.startswith("_"):
            continue
        for a in items:
            for t in re.split(r",\s*|\s+&\s+|\s+and\s+|\s*\(with\s+|\)", a["team"]):
                t = t.strip()
                if t:
                    ann_by_team.setdefault(t, []).append((key.split("/", 1)[1], a))

    lines = ["# PC-98 translation teams", "",
             "Human translators and hackers whose English PC-98 work we know of. Their "
             "translations always take precedence over this repo's machine translations: "
             "we link to them, skip games they've announced, and retire our version of any game "
             "they release.", "",
             "Built from the credits in the [archive.org PC-98 translation archive](https://archive.org/details/%s) "
             "plus team pages (`tools/build_teams.py`). Please support the teams directly." % IA_ITEM, ""]
    for team in sorted(releases, key=lambda t: (-len(releases[t]), t.lower())):
        rel = releases[team]
        lines += ["## %s" % team, ""]
        for u in links.get(team, []):
            lines.append("- Home: <%s>" % u)
        for base, url, incomplete in sorted(rel):
            lines.append("- [%s](%s)%s" % (base, url, " (incomplete)" if incomplete else ""))
        for title, a in ann_by_team.get(team, []):
            lines.append("- *Announced:* %s: %s ([source](%s), checked %s)" % (title, a["status"], a["url"], a["checked"]))
        lines.append("")
    open(os.path.join(ROOT, "index", "TEAMS.md"), "w", encoding="utf-8").write("\n".join(lines))
    print("%d teams" % len(releases))


if __name__ == "__main__":
    main()
