"""Three-way merge for games/<title>/strings.json, matching strings by their Japanese text.

Git runs this as the merge driver for strings.json (see tools/install_merge_driver.py), so a
pull that brings in a re-extraction keeps the English written locally, and the reverse.

  merge_strings.py BASE OURS THEIRS [PATH]

The result is written over OURS, as git expects. Exit status 0 means merged cleanly; 1 means
conflicts, which are listed on stderr while OURS is left untouched.

A side "re-extracted" the file when anything other than `en` changed in its strings: ids,
Japanese text, refs, limits, entries added or removed. The result takes that side's strings
and carries the other side's English across by matching each entry to the base entries with the
same Japanese text (see match_base). Only one side may re-extract; when neither did, entries
line up by id.

Per entry, English merges three ways: whichever side changed it from base wins; both sides
making the same change is fine; both sides changing it differently is a conflict, as is an
entry folded from base entries whose English merges to different values. A conflict is
also raised when English changed on the side that did not re-extract but the re-extraction no
longer has an entry with that Japanese text, since merging would silently drop the translation.
"""

import json
import sys
from pathlib import Path

MISSING = object()


class Conflicts(Exception):
    def __init__(self, problems):
        super().__init__(f"{len(problems)} conflict(s)")
        self.problems = problems


def shape(entry):
    return {key: value for key, value in entry.items() if key != "en"}


def english(entry):
    return entry.get("en", "")


def three_way(base, ours, theirs):
    """The merged value, or MISSING when both sides changed it differently."""
    if ours == base:
        return theirs
    if theirs == base or ours == theirs:
        return ours
    return MISSING


def merge_value(name, base, ours, theirs, problems):
    value = three_way(base, ours, theirs)
    if value is MISSING:
        problems.append(f"{name}: changed on both sides\n  base:   {base!r}\n  ours:   {ours!r}\n  theirs: {theirs!r}")
        return ours
    return value


def merge_top_level(base, ours, theirs, problems):
    keys = list(theirs) + [key for key in ours if key not in theirs]
    keys = [key for key in keys if key != "strings"]
    merged = {}
    for key in keys:
        value = merge_value(key, base.get(key, MISSING), ours.get(key, MISSING), theirs.get(key, MISSING), problems)
        if value is not MISSING:
            merged[key] = value
    return merged


def match_base(entry, by_jp, by_trimmed_jp):
    """The base entries that `entry` from the re-extracted side replaces.

    A re-extraction can fold several base entries into one (a menu item and the message that
    repeats it), widening its refs to cover them all, or include padding spaces that used to sit
    outside the text. So every base entry sharing a ref is a candidate, whether its Japanese is
    identical or identical apart from surrounding spaces. Without shared refs, the entries with
    identical Japanese are narrowed by kind and then id.
    """
    refs = set(entry.get("refs", []))
    exact = by_jp.get(entry["jp"], [])
    loose = by_trimmed_jp.get(entry["jp"].strip(), [])
    overlapping = [e for e in loose if refs & set(e.get("refs", []))]
    if overlapping:
        return overlapping
    candidates = exact
    for keep in (lambda e: e.get("kind") == entry.get("kind"), lambda e: e["id"] == entry["id"]):
        narrowed = [e for e in candidates if keep(e)]
        if len(candidates) > 1 and narrowed:
            candidates = narrowed
    return candidates


def merge_english(entry, candidates, other_by_id, ours_reextracted, problems):
    """English for `entry`, merged with the other side's changes to the base entries it replaces.

    Candidates whose English the other side left alone contribute nothing. A candidate matched
    only by ignoring surrounding spaces is compared the same way, so the padded twin of a string
    agrees with it when only the padding differs; the exact match supplies the value.
    """
    extracted_en = english(entry)
    contributions = []
    for source in candidates:
        base_en, other_en = english(source), english(other_by_id[source["id"]])
        if other_en == base_en:
            continue
        ours_en, theirs_en = (extracted_en, other_en) if ours_reextracted else (other_en, extracted_en)
        contributions.append((source, base_en, ours_en, theirs_en, three_way(base_en, ours_en, theirs_en)))
    if not contributions:
        return extracted_en

    values = [value for *_, value in contributions]
    exact = {value for source, *_, value in contributions if source["jp"] == entry["jp"]}
    loose = [value for source, *_, value in contributions if source["jp"] != entry["jp"]]
    if MISSING not in values:
        if len(exact) == 1:
            chosen = next(iter(exact))
            if all(value.strip() == chosen.strip() for value in loose):
                return chosen
        elif not exact and len(set(loose)) == 1:
            return loose[0]
    detail = "\n".join(
        f"  base {source['id']} {source['jp']!r}: base {b!r}, ours {o!r}, theirs {t!r}"
        for source, b, o, t, _ in contributions
    )
    problems.append(f"{entry['id']} {entry['jp']!r} en: does not merge to one value\n{detail}")
    return MISSING


def merge(base, ours, theirs):
    problems = []
    merged = merge_top_level(base, ours, theirs, problems)

    base_shape = [shape(e) for e in base["strings"]]
    ours_reextracted = [shape(e) for e in ours["strings"]] != base_shape
    theirs_reextracted = [shape(e) for e in theirs["strings"]] != base_shape
    if ours_reextracted and theirs_reextracted:
        raise Conflicts(problems + ["strings: re-extracted on both sides; merge the extractions first"])

    # `extracted` supplies the entries; `other` only changed English, so it lines up with base by id.
    if ours_reextracted:
        extracted, other, extracted_label = ours["strings"], theirs["strings"], "ours"
    else:
        extracted, other, extracted_label = theirs["strings"], ours["strings"], "theirs"
    other_by_id = {e["id"]: e for e in other}
    by_jp, by_trimmed_jp = {}, {}
    for entry in base["strings"]:
        by_jp.setdefault(entry["jp"], []).append(entry)
        by_trimmed_jp.setdefault(entry["jp"].strip(), []).append(entry)

    strings, used = [], set()
    for entry in extracted:
        candidates = match_base(entry, by_jp, by_trimmed_jp)
        result = dict(entry)
        strings.append(result)
        if not candidates:
            continue
        used.update(e["id"] for e in candidates)
        value = merge_english(entry, candidates, other_by_id, ours_reextracted, problems)
        if value is not MISSING and (value or "en" in result):
            result["en"] = value

    for entry in base["strings"]:
        if entry["id"] in used:
            continue
        changed = english(other_by_id[entry["id"]])
        if changed != english(entry):
            problems.append(
                f"{entry['id']} {entry['jp']!r}: English changed to {changed!r}, "
                f"but {extracted_label} no longer has an entry with this Japanese text"
            )

    if problems:
        raise Conflicts(problems)
    merged["strings"] = strings
    return merged


def read(path):
    text = Path(path).read_bytes().decode("utf-8")
    return json.loads(text), "\r\n" if "\r\n" in text else "\n"


def write(path, data, newline):
    text = json.dumps(data, ensure_ascii=False, indent=1).replace("\n", newline)
    Path(path).write_bytes(text.encode("utf-8"))


def main(argv):
    if len(argv) not in (3, 4):
        raise SystemExit(__doc__)
    base_path, ours_path, theirs_path = argv[:3]
    label = argv[3] if len(argv) == 4 else ours_path
    (base, _), (ours, newline), (theirs, _) = read(base_path), read(ours_path), read(theirs_path)
    try:
        merged = merge(base, ours, theirs)
    except Conflicts as conflicts:
        sys.stderr.reconfigure(encoding="utf-8")
        print(f"{label}: {conflicts}", file=sys.stderr)
        for problem in conflicts.problems:
            print(problem, file=sys.stderr)
        return 1
    write(ours_path, merged, newline)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
