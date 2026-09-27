# ♥ Setsujuu - Yuganda Kioku (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Setsujuu - Yuganda Kioku/Setsujuu - Yuganda Kioku [HD]/Setsujuu - Yuganda Kioku.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's scene engine (`SETU/SETU.EXE`): 136 scene files (`*.OVL`) holding text and scene code in one stream (`pc98tl/jast_ovl.py` documents the format).

## English display (`pc98tl/jast_game.py`)

* The engine draws single-byte ASCII half-width from its own ANK font, so the
  English needs no font work.  Its character check dropped ASCII punctuation;
  the patch marks bytes 21-3F (but digits and `%`, the name placeholder) as
  single-byte characters in the engine's character class table.
* Scene files are never rearranged: each Japanese text run is overwritten
  with the engine's own goto (`0B 36` + file offset) to its English, appended
  at the end of the file, which ends with a goto back to just after the run.
  Every offset the scene code holds stays valid.
* English lines are padded with spaces so the engine's own wrap (78 columns,
  a speaker's lines hanging after the colon at 62) falls between words.
  Messages longer than the three-line box page as in the original.

## Script

6966 strings (6923 scene text, 43 engine strings).

Translation and the content classification (♥) are done by the translation model; 0 of 6966 strings have English so far.

## Limits

* Speaker lines are written `Name: text` (the name up to 14 columns, or a `%nnn` placeholder); `\n` starts a new paragraph.
* A scene file, with its English appended, must fit the engine's 16 KB scene buffer; the patcher leaves a scene that would not fit in Japanese and reports it.
* Engine strings (`e` ids: menus, prompts, item and character names, bonus texts) are rewritten in place in the program (`pc98tl/engine_strings.py`): their original byte length, two letters per full-width cell; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (logos, menus drawn as pictures).
* The name-entry character grids stay Japanese: the engine picks characters from them by position.
* Driver messages (mouse and music drivers).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Opening narration | OK |
| Message window | OK: half-width filler, wrapped between words inside the frame; speaker names from the engine's name table |
| Engine strings (title menu, labels) rewritten in place | OK: filler inside the menus, game runs on |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
