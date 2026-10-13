"""Tests for merge_strings.py: python tools/test_merge_strings.py"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_strings import Conflicts, merge  # noqa: E402


def entry(id_, jp, en="", refs=(), kind="msg", max_cells=10):
    return {"id": id_, "kind": kind, "jp": jp, "en": en, "refs": list(refs), "max_cells": max_cells}


def doc(*strings, **top):
    return {"game": "Test", **top, "strings": list(strings)}


def english_by_id(data):
    return {e["id"]: e["en"] for e in data["strings"]}


class SameExtraction(unittest.TestCase):
    def test_each_side_keeps_its_own_changes(self):
        base = doc(entry("m1", "あ"), entry("m2", "い"), entry("m3", "う", "U"))
        ours = doc(entry("m1", "あ", "A"), entry("m2", "い"), entry("m3", "う", ""))
        theirs = doc(entry("m1", "あ"), entry("m2", "い", "I"), entry("m3", "う", "U"))
        self.assertEqual(english_by_id(merge(base, ours, theirs)), {"m1": "A", "m2": "I", "m3": ""})

    def test_different_changes_to_one_entry_conflict(self):
        base = doc(entry("m1", "あ"))
        with self.assertRaises(Conflicts):
            merge(base, doc(entry("m1", "あ", "A")), doc(entry("m1", "あ", "Ah")))


class ReExtraction(unittest.TestCase):
    def setUp(self):
        self.base = doc(entry("m1", "あ", refs=["f:1"]), entry("m2", "い", refs=["f:2"]))
        self.translated = doc(entry("m1", "あ", "A", refs=["f:1"]), entry("m2", "い", "I", refs=["f:2"]))
        # Renumbered, a new string in front, refs moved.
        self.extracted = doc(entry("m1", "新"), entry("m2", "あ", refs=["f:3"]), entry("m3", "い", refs=["f:4"]))

    def test_english_follows_the_japanese_text(self):
        merged = merge(self.base, self.translated, self.extracted)
        self.assertEqual(english_by_id(merged), {"m1": "", "m2": "A", "m3": "I"})
        self.assertEqual([e["refs"] for e in merged["strings"]], [[], ["f:3"], ["f:4"]])

    def test_either_side_may_be_the_re_extraction(self):
        merged = merge(self.base, self.extracted, self.translated)
        self.assertEqual(english_by_id(merged), {"m1": "", "m2": "A", "m3": "I"})

    def test_both_sides_re_extracting_is_refused(self):
        with self.assertRaises(Conflicts):
            merge(self.base, self.extracted, doc(entry("x", "あ")))

    def test_translation_with_no_entry_left_conflicts(self):
        with self.assertRaises(Conflicts) as raised:
            merge(self.base, self.translated, doc(entry("m1", "あ", refs=["f:1"])))
        self.assertIn("no longer has an entry", raised.exception.problems[0])

    def test_top_level_fields_merge_too(self):
        base = doc(entry("m1", "あ"), engine="old")
        merged = merge(base, doc(entry("m1", "あ", "A"), engine="old"), doc(entry("m1", "あ"), engine="new"))
        self.assertEqual(merged["engine"], "new")


class FoldedEntries(unittest.TestCase):
    def test_entries_folded_into_one_keep_their_shared_english(self):
        base = doc(entry("i1", "ロード", refs=["f:1"], kind="item"), entry("m9", "ロード", refs=["f:2"]))
        ours = doc(entry("i1", "ロード", "Load", refs=["f:1"], kind="item"), entry("m9", "ロード", "Load", refs=["f:2"]))
        theirs = doc(entry("i1", "ロード", refs=["f:1", "f:2"], kind="item"))
        self.assertEqual(english_by_id(merge(base, ours, theirs)), {"i1": "Load"})

    def test_padded_twin_agrees_when_only_padding_differs(self):
        base = doc(entry("i3", "キャンセル", refs=["f:1"]), entry("i7", "　キャンセル　", refs=["f:2"]))
        ours = doc(entry("i3", "キャンセル", "Cancel", refs=["f:1"]), entry("i7", "　キャンセル　", "  Cancel  ", refs=["f:2"]))
        theirs = doc(entry("i3", "キャンセル", refs=["f:1", "f:2"]))
        self.assertEqual(english_by_id(merge(base, ours, theirs)), {"i3": "Cancel"})

    def test_padding_moved_into_the_text_still_matches(self):
        base = doc(entry("m1", "いいわ。", refs=["f:2"]))
        ours = doc(entry("m1", "いいわ。", "Fine.", refs=["f:2"]))
        theirs = doc(entry("i7", "いいわ。　　", refs=["f:1", "f:2"]))
        self.assertEqual(english_by_id(merge(base, ours, theirs)), {"i7": "Fine."})

    def test_folded_entries_that_disagree_conflict(self):
        base = doc(entry("a", "はい", refs=["f:1"]), entry("b", "はい", refs=["f:2"]))
        ours = doc(entry("a", "はい", "Yes", refs=["f:1"]), entry("b", "はい", "Okay", refs=["f:2"]))
        with self.assertRaises(Conflicts):
            merge(base, ours, doc(entry("a", "はい", refs=["f:1", "f:2"])))

    def test_untouched_twin_does_not_block_the_merge(self):
        base = doc(entry("a", "はい", refs=["f:1"]), entry("b", "はい", refs=["f:2"]))
        ours = doc(entry("a", "はい", "Yes", refs=["f:1"]), entry("b", "はい", refs=["f:2"]))
        theirs = doc(entry("a", "はい", refs=["f:1", "f:2"]))
        self.assertEqual(english_by_id(merge(base, ours, theirs)), {"a": "Yes"})


class GitDriver(unittest.TestCase):
    def run_driver(self, base, ours, theirs, newline):
        folder = Path(tempfile.mkdtemp())
        paths = []
        for name, data in (("base", base), ("ours", ours), ("theirs", theirs)):
            path = folder / name
            path.write_bytes(json.dumps(data, ensure_ascii=False, indent=1).replace("\n", newline).encode())
            paths.append(str(path))
        script = Path(__file__).resolve().parent / "merge_strings.py"
        result = subprocess.run([sys.executable, str(script), *paths], capture_output=True)
        return result.returncode, Path(paths[1]).read_bytes()

    def test_writes_result_over_ours_in_the_repository_format(self):
        base = doc(entry("m1", "あ"))
        code, written = self.run_driver(base, doc(entry("m1", "あ", "A")), doc(entry("m1", "あ"), engine="x"), "\r\n")
        self.assertEqual(code, 0)
        expected = json.dumps(merge(base, doc(entry("m1", "あ", "A")), doc(entry("m1", "あ"), engine="x")), ensure_ascii=False, indent=1)
        self.assertEqual(written, expected.replace("\n", "\r\n").encode())

    def test_conflict_leaves_ours_untouched(self):
        ours = doc(entry("m1", "あ", "A"))
        code, written = self.run_driver(doc(entry("m1", "あ")), ours, doc(entry("m1", "あ", "Ah")), "\n")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(written), ours)


if __name__ == "__main__":
    unittest.main()
