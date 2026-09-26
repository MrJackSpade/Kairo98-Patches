# Definition of Done

This is the checklist for calling a game **Done**. A goal like *"bring Funny Bee
to Done"* means: work through every item below that applies, in order, until
all of them are true, and don't stop at "it works on my machine".

Two kinds of game have different end states:

| Kind | How you tell | Done means |
|---|---|---|
| **♥ adult** | the script-text scan says adult (see §2) | **Tooling Done**: the game is fully patchable and tested. The script goes to the maintainer, who translates it with their own model. Claude does not translate it. |
| **No ♥** | the scan says not adult | **Translated Done**: Tooling Done, *plus* Claude has translated the whole script and the English build is tested. |

---

## 1. Clearance (before any work)

- [ ] The game has **no human English translation**, not even a partial one we
      could extend. It must not show *human translation* in `index/INDEX.md`.
- [ ] No team with a finished release has **announced** it
      (`research/announced.json`, `index/TEAMS.md`). If a team with no finished
      release announced it, the game is still ours, and the announcement stays
      linked.
- [ ] You checked it **now**, not from memory: VNDB (English releases on any
      platform), the AliceSoft wiki where relevant, the project pages of active
      teams (BabaJeanmel, Alpharobo and others in `index/TEAMS.md`), GitHub, and
      one web search for the title plus "English translation".
- [ ] The result is recorded in `research/clearance.json` with the date and sources.

If a proven team covers it: add it to `research/announced.json`, rebuild the
index, and **stop**. That game is not ours.

## 2. Adult (♥) classification

- [ ] Extract the script (§3), then run
      `python tools/adult_scan.py "<index key>" games/<title>/strings.json`.
- [ ] The scan decides the mark, and nothing else does (not the publisher, the
      box art, or VNDB). It flags a game with **5+ matching lines and 3+ distinct
      terms, or 15+ matching lines**, using only single-meaning sexual terms (see
      the list in `tools/adult_scan.py`). Profanity and violence never count.
- [ ] Put the mark in the game's `notes.md` title (`# ♥ Title`) and in the index.
- [ ] **Safety valve:** if explicit sexual text turns up while translating a
      no-♥ game, stop translating. Mark it ♥ (record `"adult": true` with a
      `"summary"` beginning `manual:` in `research/adult_text.json`) and hand the
      rest to the maintainer. Never translate past it.

## 3. Extraction

- [ ] The script disassembles and **rebuilds byte-for-byte** unmodified. This
      proves the tooling understands every command, so no text gets missed.
- [ ] `games/<title>/strings.json` holds every player-visible string: dialogue,
      menus, names, command captions, and strings hard-coded in the executable
      when there are any.
- [ ] `jp` shows the text **as displayed on screen** (e.g. with any engine
      kana conversion applied), so translation works from what the player sees.
- [ ] Identical strings are merged. Runtime inserts are shown as `{X1}`-style tokens.
- [ ] Each string's `max_cells` reflects its real on-screen space (message
      window, menu item width, name slot).
- [ ] Text drawn as graphics (title logos, status panels) is listed in
      `notes.md` as not handled.

## 4. Patching

- [ ] English displays **half-width** (two letters per 16px cell or the
      equivalent) through an engine patch. No full-width stopgap.
- [ ] A partly translated build still shows the untranslated Japanese correctly.
- [ ] **Memory-neutral:** the patched game must run within the free memory of
      the disk image's own DOS setup. No page, buffer or pool may need more memory
      than the image provides. If text outgrows the engine's limits, split it
      (e.g. move overflow into extra script pages) instead of taking memory.
- [ ] Engine patch sites are found **by byte signature**, not fixed addresses,
      where the engine family has more than one build.
- [ ] Lines wrap to the window automatically. `\n` in English forces a break.
      Lines that continue mid-line account for the column they start at.
- [ ] The patcher **refuses** a real build that breaks a hard limit (page size,
      name length) instead of producing a broken image. Soft overruns are
      reported by string id.
- [ ] The patched image contains `MTL_NOTE.TXT` in the game folder, saying it's a
      machine translation.

## 5. Standard game folder

- [ ] `games/<title>/` contains `game.json`, `extract.py`, `patch.py`
      (contract: `patch.py IN OUT [--pseudo]`), `strings.json`, `notes.md`, and
      **`PATCH.BAT`, byte-identical to `tools/PATCH.BAT.template`**.
- [ ] Double-clicking `PATCH.BAT` produces `output/<title> (English MTL).hdi`
      from the collection copy, and dropping an image onto it works too.
- [ ] `python tools/check_games.py` passes.
- [ ] `notes.md` starts with the machine-translation notice and covers the
      engine, the patch, the limits, and a test table (what's verified, and what
      isn't).

## 6. Testing (np21w, `tools/emu_shot.ps1`)

- [ ] **Stress test:** `patch.py IN OUT --pseudo` (filler at 2.5 times the
      Japanese length) builds with **no errors**. The patched image boots, and
      the screenshots show:
  - the title / main menu (menu boxes on screen, items readable)
  - the main message window (lines inside the frame, paging on overflow)
  - at least one scene past the opening
- [ ] The game doesn't crash or hit *Out of memory* during those steps.
- [ ] Anything not reached (battles, dungeons, save/load, endings) is listed
      as **not yet seen** in `notes.md`. Don't claim what wasn't seen.

## 7. Translation (no-♥ games only)

- [ ] Every string in `strings.json` has `en`, and
      `python tools/mtl.py check` shows **no token mismatches**.
- [ ] Names, places and terms are consistent throughout. Settle the `name`
      entries first and use them as the glossary.
- [ ] A real patch (`PATCH.BAT`) builds with **no warnings** (nothing too wide,
      nothing truncated).
- [ ] The English build boots and reads correctly across the screens in §6,
      using real text instead of filler.

(For ♥ games this section belongs to the maintainer. Claude doesn't do it.)

## 8. Record and publish

- [ ] `index/INDEX.md` shows the game's status correctly: *machine translation
      (this repo)* with a link to its folder (`research/patches_manual.json`, then
      `python tools/build_index.py`).
- [ ] `ROADMAP.md`'s status table is updated.
- [ ] Everything is committed and pushed to Kairo98-Patches. No game data (disk
      images, executables) is committed.

## Afterwards: when a human translation appears

- [ ] Re-check before any public release. If a human translation or a proven
      team's announcement now exists, retire ours: mark it superseded in the
      index, link theirs, and remove our patch.

---

## Using this in a goal

- *"Bring `<game>` to Done"*: every applicable section above.
- *"Bring the `<engine>` family to Tooling Done"*: §1–§6 and §8 for each game
  on that engine, plus the translation (§7) for any no-♥ game among them.
- A game that fails §1 is finished once it's recorded as skipped. That counts
  as done for that game.
