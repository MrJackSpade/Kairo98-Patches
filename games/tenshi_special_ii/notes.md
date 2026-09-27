# ♥ Tenshi-tachi no Gogo Special II (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Gogo Special II/Tenshi-tachi no Gogo Special II [FD]/Tenshi-tachi no Gogo Special II (Disk A).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's later scene engine: 64 scene files (`*.SCM`), command tables then messages ended by `00 00`, found by count (`pc98tl/jast_scm.py`).
The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image (every disk's files in `TENSHI/`, started as the floppy's batch file does, with the engine's hard-disk switch `/h`); the base image is the collection's `Kankin/Kankin [HD]/Kankin.hdi` with its own game removed.

## English display (`pc98tl/jast_scm.py`)

* The engine draws every character from the kanji ROM.  Its glyph fetch is
  rewritten: a code whose first byte is below 80 is two ASCII letters, drawn
  as the kanji ROM's two 8x16 ANK glyphs side by side in one cell (a far
  routine in a small DOS block from the entry stub); Japanese draws as before.
* English is one stream of lines padded to the window's width, words
  stopping two columns short of the edge; the engine pages a full box itself
  (waits for a click).

## Script

1879 strings (1633 scene text, 42 engine strings, 204 menu words).

♥ by the script-text scan (20 of 1677 strings match the sexual-vocabulary list (4 distinct terms)). The maintainer translates it; 0 strings have English so far.

## Limits

* Speaker lines are written `Name: text` (the name up to 14 columns, or a `%nnn` placeholder); `\n` starts a new paragraph.
* A scene file, with its English appended, must fit the engine's 16 KB scene buffer; the patcher leaves a scene that would not fit in Japanese and reports it.
* Engine strings (`e` ids: menus, prompts, item and character names, bonus texts) are rewritten in place in the program (`pc98tl/engine_strings.py`): their original byte length, two letters per full-width cell; longer ones are cut and reported.
* Noun table words (`w` ids, NTBL.BIN: the objects of the command menus): 16 letters.
* Batch files' Japanese echo lines (`b` ids) are rewritten as they are.

## Not handled

* Text drawn into the artwork (logos, menus drawn as pictures).
* The name-entry character grids stay Japanese: the engine picks characters from them by position.
* Driver messages (mouse and music drivers).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Hard-disk layout boots (engine's /h mode) | OK |
| Opening and title | OK |
| Message window | OK: half-width filler inside the frame, wrapped between words; the engine pages a full box (▼) |
| Command menu (engine strings) | OK: filler in place |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
