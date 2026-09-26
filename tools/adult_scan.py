"""Decide a game's ♥ (adult) mark from its own script text.

    python tools/adult_scan.py <collection key> games/<title>/strings.json

Counts the strings containing unambiguous sexual vocabulary.  Stores only the
counts (never the text) in research/adult_text.json, which build_index.py
prefers over VNDB/publisher-based marks.  Each matching string's id is also
listed so those lines can be routed to the maintainer's own model.
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# Terms chosen to be unambiguous in game scripts (bare 犯 = "crime" etc. are excluded).
TERMS = [
    "挿入", "挿れ", "精液", "膣", "乳首", "陰部", "陰茎", "ペニス", "肉棒", "セックス",
    "愛液", "射精", "フェラ", "勃起", "秘部", "クリトリス", "オナニー", "処女膜", "絶頂",
    "犯して", "犯され", "犯す", "犯し", "レイプ", "強姦", "淫乱", "淫ら", "媚薬", "中出し",
    "ザーメン", "おまんこ", "ちんぽ", "ちんちん", "あそこが", "喘ぎ", "よがり",
]
PATTERN = re.compile("|".join(map(re.escape, TERMS)))
THRESHOLD = 5  # strings with a hit before a game counts as adult


def scan(strings):
    hits = [e["id"] for e in strings if PATTERN.search(e["jp"])]
    return hits


def main():
    key, path = sys.argv[1], sys.argv[2]
    doc = json.load(open(path, encoding="utf-8"))
    hits = scan(doc["strings"])
    adult = len(hits) >= THRESHOLD
    out_path = os.path.join(ROOT, "research", "adult_text.json")
    data = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    data[key] = {"adult": adult, "hits": len(hits), "strings": len(doc["strings"]),
                 "summary": "%d of %d strings match the sexual-vocabulary list" % (len(hits), len(doc["strings"])),
                 "adult_ids": hits}
    json.dump(data, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%s: %s (%s)" % (key, "♥ adult" if adult else "not adult", data[key]["summary"]))


if __name__ == "__main__":
    main()
