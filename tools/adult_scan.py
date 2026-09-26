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

# Only terms that can mean one thing: sex acts, sexual fluids, sexual slang.
# Excluded on purpose: anatomy with medical uses (膣, 乳首, 陰茎, 勃起...),
# words with innocent readings (挿入 "insert disk", 犯す "commit a crime",
# 絶頂 "peak", 凌辱 "insult", よがり in 独りよがり "self-righteous",
# あそこ "over there", 喘ぎ "panting"), and violence/profanity.  Checked
# 2026-09-26 against the raw files of 481 mainstream titles vs 200 adult titles.
TERMS = [
    "精液", "愛液", "射精", "肉棒", "オナニー", "中出し", "ザーメン",
    "おまんこ", "ちんぽ", "淫乱", "媚薬",
]
PATTERN = re.compile("|".join(map(re.escape, TERMS))
                     + r"|フェラ(?![ーガリ])"                  # not フェラーリ (Ferrari) / フェラガモ
                     + r"|(?<!ユニ)セックス(?!アピール)")       # not ユニセックス (unisex) / sex appeal
MIN_LINES = 5   # strings with a hit
MIN_TERMS = 3   # distinct terms among them, so one odd word can't flag a game


def scan(strings):
    hits, terms = [], set()
    for e in strings:
        found = PATTERN.findall(e["jp"])
        if found:
            hits.append(e["id"])
            terms.update(found)
    return hits, terms


def main():
    key, path = sys.argv[1], sys.argv[2]
    doc = json.load(open(path, encoding="utf-8"))
    hits, terms = scan(doc["strings"])
    adult = len(hits) >= MIN_LINES and len(terms) >= MIN_TERMS
    out_path = os.path.join(ROOT, "research", "adult_text.json")
    data = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    data[key] = {"adult": adult, "hits": len(hits), "strings": len(doc["strings"]),
                 "distinct_terms": len(terms),
                 "summary": "%d of %d strings match the sexual-vocabulary list (%d distinct terms)"
                            % (len(hits), len(doc["strings"]), len(terms)),
                 "adult_ids": hits}
    json.dump(data, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%s: %s (%s)" % (key, "♥ adult" if adult else "not adult", data[key]["summary"]))


if __name__ == "__main__":
    main()
