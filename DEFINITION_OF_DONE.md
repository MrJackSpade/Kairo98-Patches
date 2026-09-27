# Definition of Done

This is the checklist for calling a game **Done**. A goal like *"bring Funny Bee
to Done"* means: work through every item below that applies, in order, until
all of them are true, and don't stop at "it works on my machine".

The order matters: the script is extracted **first** and handed off, so the
translation model can start while the patching work goes on. Nobody waits for
the patcher.

> **Who does what**
>
> * **Claude does decomp only:** reverse-engineering the engine, extracting
>   the Japanese script into `strings.json`, and building a patcher that takes
>   arbitrary, longer English back in. It also sets up the standard folder,
>   runs the boot tests and keeps the tooling records. Claude doesn't
>   translate any game, adult or not.
> * **The translation model does everything to do with the script's
>   content:** translating, the adult (♥) classification, and any tagging or
>   flagging of what's in the script. Claude doesn't read scripts for
>   content, scan them, or record content findings. The scripts are then left
>   to other people and teams to use as they choose.
> * **The only thing that stops work** on a game is §1: a human translation
>   already exists, or a team with finished releases has announced one. Then
>   the game is recorded as skipped and is finished.
> * **Content never stops the tooling.** Every game gets the tooling. Never
>   decline, withdraw or delete a game folder, extractor, patcher or record
>   over content.

**Done** means **Tooling Done**: the script is extracted and handed off, and
the game is fully patchable with any English and tested (§1–§6 and §8).

---

## 1. Clearance (before any work)

- [ ] The game has **no human English translation for the PC-98**, not even a
      partial one we could extend: a patch for the PC-98 version or a
      pre-patched PC-98 image. It must not show *human translation* in
      `index/INDEX.md`. A translation of another version (Windows, DOS/V, other
      computers) does **not** stop work: many of those are Win95-era releases
      that no longer run or can't be obtained. Link it in the index, and use its
      script as the source for our English where it can be matched.
- [ ] The same goes for announcements: only a PC-98 translation announced by a
      proven team stops work.
- [ ] No team with a finished release has **announced** it
      (`research/announced.json`, `index/TEAMS.md`). If a team with no finished
      release announced it, the game is still ours, and the announcement stays
      linked.
- [ ] You checked it **now**, not from memory: VNDB (English releases, noting
      which platform each is for), the AliceSoft wiki where relevant, the project pages of active
      teams (BabaJeanmel, Alpharobo and others in `index/TEAMS.md`), GitHub, and
      one web search for the title plus "English translation".
- [ ] The result is recorded in `research/clearance.json` with the date and sources.

If a proven team covers it: add it to `research/announced.json`, rebuild the
index, and **stop**. That game is not ours.

## 2. Extraction

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
- [ ] **Re-extraction never loses translations.** `extract.py` carries every
      existing `en` (and hand-tuned `max_cells`/`note`) forward by matching kind
      and Japanese text. If a later tooling change alters the displayed `jp`,
      migrate the existing translations in the same commit.

## 3. Handoff: right after extraction

- [ ] Commit and push `strings.json` right away, and mark the game **Ready to
      translate** in `ROADMAP.md`'s status table. The translation model takes
      it from there (translation, ♥ classification, any content flags) while
      Claude **carries on with §4–§8 for this same game**. Handing off the
      script isn't the end of Claude's work on it, and the script isn't held
      back until the patcher is finished.
- [ ] Claude doesn't classify, scan, tag or flag the script's content, and
      doesn't write content findings into `research/adult_text.json`,
      `notes.md` or anywhere else. That record belongs to the translation model.

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

## 7. Translation: not Claude's

Translation belongs to the translation model for every game, with or without
♥. So do the ♥ mark (`research/adult_text.json`, `tools/adult_scan.py`) and any
content tagging or flagging. Claude's part ends when any English the model
writes, of any length, goes in through `patch.py` (§4, proven by the §6 stress
test).

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
- *"Get `<game>` ready to translate"*: §1–§3. This is the fast path that
  gives the translation model something to translate.
- *"Bring the `<engine>` family to Tooling Done"*: §1–§6 and §8 for each game
  on that engine. Do §1–§3 for **every** game in the family before starting
  the patch work on any of them.
- A game that fails §1 is finished once it's recorded as skipped. That counts
  as done for that game.
