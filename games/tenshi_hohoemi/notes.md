# ♥ Tenshi-tachi no Hohoemi (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Hohoemi/Tenshi-tachi no Hohoemi [HD]/Tenshi-tachi no Hohoemi.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's scene engine (`TENHO/TENHO.EXE`): 92 scene files (`*.OVL`) holding text and scene code in one stream (`pc98tl/jast_ovl.py` documents the format).

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

7353 strings (7302 scene text, 51 engine strings).

Translation and the content classification (♥) are done by the translation model; 0 of 7353 strings have English so far.

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
| Name entry: character grid kept, prompt and buttons in place | OK |
| Weekly schedule and status panel (engine strings) | OK |
| Message window | OK: half-width filler inside the frame |
| Scene past the opening (the park) | OK |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
