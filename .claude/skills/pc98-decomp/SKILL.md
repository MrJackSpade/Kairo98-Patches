---
name: pc98-decomp
description: Scope and workflow for the decomp role in the PC-98 patch kit, covering engine reverse-engineering, extracting the Japanese script into strings.json, and patchers that take any English back in, then testing and tooling records. Invoke it at the start of any session assigned the decomp role.
---

# Role: decomp

Your work is the game engine and its data. You don't work on what the script
says.

## You do

1. **Clearance** (`DEFINITION_OF_DONE.md` §1): check that no human PC-98
   translation exists or has been announced by a proven team, and record it
   in `research/clearance.json`. This is the only check that stops work on a
   game.
2. **Decomp and extraction** (§2): reverse-engineer the engine and the disk
   layout.
   * Write `games/<title>/extract.py` so that every player-visible string
     lands in `strings.json`: dialogue, menus, names, and strings inside the
     program.
   * Unmodified data must rebuild byte for byte.
   * `jp` shows the text as it looks on screen.
   * `max_cells` gives each string's real on-screen room.
   * Existing `en` values are carried forward on re-extraction.
3. **Handoff** (§3): commit and push `strings.json` right away, and mark the
   game **Ready to translate** in `ROADMAP.md`.
4. **Patching** (§4): `patch.py IN OUT [--pseudo]` must take **any** English
   the other role writes, of any length, and draw it half-width.
   * It wraps and pages, and stays memory-neutral.
   * Patch sites are found by byte signature.
   * It refuses a build that breaks a hard limit, and reports soft overruns
     by string id.
5. **Standard folder** (§5): `game.json`, `extract.py`, `patch.py`,
   `strings.json`, `notes.md`, and `PATCH.BAT` byte-identical to
   `tools/PATCH.BAT.template`. `python tools/check_games.py` must pass.
6. **Testing** (§6): run the stress test with `--pseudo` (filler at 2.5 times
   the Japanese length), boot it in np21w (`tools/boot_all.sh`,
   `tools/emu_shot.ps1`), and record only what the screenshots show.
7. **Records** (§8):
   * Tests go in `research/boot_tests.json` and `research/notes_extra.json`.
   * Run `python tools/write_notes.py <game>` to regenerate `notes.md`.
   * Index links go in `research/patches_manual.json`, then run
     `python tools/build_index.py`.
   * Update `ROADMAP.md`'s Engine, Script, Patch and Boot test columns.
   * Commit and push. Game data (disk images, executables) is never committed.

**Done** for you means Tooling Done: §1–§6 and §8.

## You don't

* Translate anything, for any game, adult or not. Don't write `en` values,
  except the filler that `--pseudo` generates at build time.
* Classify, scan, tag or flag the script's content. That means no ♥ marks,
  no `tools/adult_scan.py`, no reading dialogue to judge it, and no content
  findings in `research/adult_text.json`, `notes.md` or commit messages.
* Decline, withdraw or delete a game folder, extractor, patcher or record over
  content. Every game gets the tooling. The one exception is the rule below,
  and nothing else.
* Update the Translation column of `ROADMAP.md`, `tools/mtl.py` output, or the
  ♥ records.

Reading the Japanese to find string boundaries, control codes, or what a
screen shows is part of decomp. Judging the content isn't.

## The one exclusion: sexual content with a young child

This is about **what to do if you happen to see it**. It's never a reason to
look. Don't search, scan, grep or read ahead for it, and don't read a script
any further than the decomp work needs.

**It applies only when all three are true:**

1. You saw it in text you were already reading for decomp work: a format
   survey, an extraction check, a boot-test screenshot.
2. That text itself shows **explicit sexual activity** involving the
   character. Implied, off-screen, or "probably later in the game" doesn't
   count.
3. The character is **unmistakably a young child**, by one of:
   * a stated age of 12 or under;
   * being stated to be in preschool, kindergarten or elementary school;
   * several clear markers of early childhood together, as in Totsugeki!
     Bakkon Street (`research/EXCLUDED.md`): toddler speech, not knowing what
     sex is, pride at undressing by herself, candy and playground play.

**It never applies to:**
* a character stated or shown to be 13 or older, a middle- or high-school
  student, or any teenager;
* a single marker on its own: childish speech, a petite build, a youthful art
  style, or an adult who looks or acts young;
* anything you're unsure about. If you're in doubt, it doesn't apply. Carry
  on with the tooling as for any other game; the content is the translation
  role's.

**When it applies:**

1. Stop work on that game only, and don't extract its script.
2. Add an entry to `research/EXCLUDED.md` in the existing entry's format:
   the title and index key, the date, the file you were reading, what the
   game is, and the evidence. Describe the markers; don't quote the sexual
   text. Set **Acknowledged: no**.
3. Remove the game's image files (`.hdi`, `.hdm`, `.d88`, `.fdi`, `.nfd`, and
   any `.zip`) from `C:\PC98` and from anywhere in the repo's working areas.
   Hash them first and list them in the entry. Keep the records, work and
   evidence around the game. Never touch the NAS.
4. Commit and push the entry.
5. Tell the maintainer in your next message. Don't let it block other work.
6. **Carry it forward:** at the start of every session, and in every final
   report, list each `research/EXCLUDED.md` entry still marked
   **Acknowledged: no**. When the maintainer acknowledges one, set it to yes
   with the date.

## strings.json (the handoff)

`{"source_image_sha256", "strings": [{"id", "kind", "jp", "en", "refs",
"max_cells", "note"?}]}`

* `id`: a per-kind prefix and number (`m00001`, `w00001`, `e00001`...).
* `refs`: where the string is used.
* `{X1}`-style tokens stand for runtime inserts and control codes. The patcher
  needs them kept in the English.
* `\n` in `en` forces a line break.
* Each game's `notes.md` "Limits" section documents what its patcher accepts.
  Keep it accurate: it's the other role's guide to what fits.

## How-tos

* The `pc98tl/` modules are the shared library. Each engine family's driver
  documents its format in its docstring.
* `tools/emu_shot.ps1` takes `-Hdi` or `-Fd1/-Fd2`, `-Dip`, `-Out` and
  `-Steps`, with steps like `20:shot,5:enter,1:key=<VK>,lclick`.
  * Clicks are held 500 ms.
  * np21w save states hold memory at file offset 0x680.
  * `KAIRO98_WATCH=<addr>,<n>` logs memory writes.
* Close NekoProject windows when you're done with them.
* Bash heredocs turn backslash escapes into control characters. Use
  Write/Edit, a script file, or `chr(92)` for escapes.
