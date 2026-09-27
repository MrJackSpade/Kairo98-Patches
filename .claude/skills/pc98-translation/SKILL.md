---
name: pc98-translation
description: Scope and workflow for the translation role in the PC-98 patch kit, covering translating extracted scripts (strings.json) into English and all classification, tagging and flagging of script content, including the ♥ adult mark. Invoke it at the start of any session assigned the translation role.
---

# Role: translation

Your work is what the script says. You don't work on the engine tooling.

## You do

1. **Classify each script** you're handed (`games/<title>/strings.json`,
   marked **Ready to translate** in `ROADMAP.md`).
   * **The ♥ (adult) mark:** `python tools/adult_scan.py "<index key>"
     games/<title>/strings.json` gives a starting count from single-meaning
     sexual terms. It flags 5+ matching lines with 3+ distinct terms, or 15+
     lines.
   * The final mark is your judgement from the script itself. Record it in
     `research/adult_text.json`. A judgement beyond the scan gets a
     `"summary"` starting with `manual:`.
   * **Any other content tagging or flagging** is yours too. That includes
     deciding which scripts you may translate under your own usage policy.
     Record what you found, where (string ids, scene refs), what you decided,
     and why, in the game's `research/adult_text.json` entry.
   * Then run `python tools/build_index.py` so the index shows the mark.
2. **Translate** the scripts you may translate.
   * `python tools/mtl.py split games/<title>/strings.json work/mtl/<title>`
     writes batches.
   * `python tools/mtl.py merge-work games/<title>/strings.json work/mtl/<title>`
     merges them back, matching by kind and Japanese text.
   * You write only the `en` fields (and `note`, if useful).
   * Settle the names first (the `name` entries, where a game has them) and
     use them as a glossary throughout.
   * Where a human English script exists for another platform, port it and
     match it to the strings.
3. **Check** your work.
   * `python tools/mtl.py check games/<title>/strings.json` must show no
     token mismatches.
   * A real build must give no warnings: `PATCH.BAT`, or
     `python games/<title>/patch.py IN OUT` without `--pseudo`. Warnings name
     the string ids that are too long, too wide or cut.
4. **Status:** update the Translation column of `ROADMAP.md`, for example
   "123 of 4567 done" or "Translated". Commit and push.

## Writing `en`

* Keep every `{X1}`-style token exactly: they're runtime inserts and control
  codes.
* `\n` forces a line break. Otherwise lines wrap by themselves.
* English may be longer than the Japanese. The patchers take the extra
  length.
* Each game's `notes.md` "Limits" section says what fits, such as menu word
  lengths and name slots. The patcher cuts and reports anything over.
* A partly translated script is fine: untranslated strings stay Japanese in
  the build.

## You don't

* Change extractors, patchers, `pc98tl/`, `game.json`, the boot tests, or the
  records of engine work.
* Change `jp`, `refs`, `max_cells` or `id` in `strings.json`, or re-extract.
* Work around a patcher limit by editing tooling. If English can't fit
  where it should, or a build fails, report the string ids and the message
  as a problem for the decomp role, and move on.
