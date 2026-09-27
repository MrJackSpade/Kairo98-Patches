# ♥ Hunting Roulette - Totsugeki Bakkon Street II (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Hunting Roulette - Totsugeki Bakkon Street II/Hunting Roulette - Totsugeki Bakkon Street II [HD]/Hunting Roulette - Totsugeki Bakkon Street II.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's scene engine (`HNT/HNT_RLT.EXE`): 152 scene files (`*.OVL`) holding text and scene code in one stream (`pc98tl/jast_ovl.py` documents the format).

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

4985 strings (4833 scene text, 152 engine strings).

♥ by the script-text scan (30 of 4833 strings match the sexual-vocabulary list (3 distinct terms)). The maintainer translates it; 0 strings have English so far.

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
| Title menu (engine strings) | OK: filler |
| Town map; building captions and the move menu (engine strings) | OK: filler in place |
| Status panel (engine strings) | OK |
| Going into a building: scene and message window | OK: half-width filler inside the frame |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
