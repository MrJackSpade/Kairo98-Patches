# Tenshi-tachi no Gogo Bangaihen (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Gogo Bangaihen/Tenshi-tachi no Gogo Bangaihen (uncensored) [FD h01]/Tenshi-tachi no Gogo Bangaihen (uncensored).d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

A scene viewer on JAST's first engine (one self-booting 2HD floppy laid out like an N88-BASIC disk): the player types a digit and the engine shows that scene's picture and its message; 11 scenes come from a table of 4-byte entries in the engine (`pc98tl/jast_typed.py` documents the layout).  Its message box is 3 lines of 53 cells, empty at each scene; it pages at every third scrolled line from the first, so no line scrolls out unread.

## English display (`pc98tl/jast_typed.py`)

* The game draws every character itself from its own 12x10 font (text is
  one glyph number a byte, FF before a second-bank glyph).  English is two
  letters to a cell: a letter pair is two bytes, a first byte from glyph
  numbers that are blank and unused by the script, and a second byte
  numbering the pair.  The message draw's glyph lookup goes to a helper that
  builds the pair's glyph from a 6x10 font (`pc98tl/font6x10.py`); Japanese
  draws as before.
* Message lines are padded with blank glyphs to the box edge (53 cells),
  where the engine wraps.  The box pages itself, waiting for a key every
  fourth scrolled line; its count now starts at a message's first line, so
  no line scrolls out unread.
* The helpers, the 6x10 font, the engine's English strings and the rebuilt
  command panel sit in the engine load's zero tail, which stays zero in a
  running game; the engine's pointers to them follow.
* Scenes are rebuilt with the English and placed again, first fit, in their
  old sectors and the free ones; the scene table follows.
* Typed commands: the word tables get the English words, typed and shown
  with the game's own capitals; the romaji conversion is bypassed so a typed
  letter is stored as the capital itself.

## Script

11 strings (11 scene text).

Translation and the content classification (♥) are done by the translation model; 0 of 11 strings have English so far.

## Limits

* Messages (`m` ids): `\n` starts a new line.  Letters and `.,'!?-` are drawn in pairs; digits and characters in the game's font (Japanese, brackets) use its own glyphs; anything else shows as `?`.
* Command words (`w` ids: `verb:` and `noun:` refs): up to 4 capital letters or digits, typed by the player; longer ones are cut and reported.  The engine finds a word anywhere in the typed line, so a word holding another (`SEE` in `SEEK`) also matches that word's commands; the patcher reports each such pair.
* Help panel rows (`p` ids): `max_cells` cells (2 letters each); longer ones are cut and reported.
* Engine strings (`e` ids): no length limit.  The save and load prompts are drawn in pieces, one after another: `eng:033a` ("DATAを"), then `eng:0340` ("ロード", load) or `eng:0345` ("セーブ", save), then `eng:034a` ("します。").
* A rebuilt scene must fit the engine's 24 KB scene buffer, and all scenes the disk; the patcher refuses a build that breaks either.
* The disk has no file system, so the machine-translation notice is `MTL_NOTE.TXT` next to the patched image instead of a file on the disk.

## Not handled

* Text drawn into the artwork (the title logo, pictures) and the "Presented by JAST" glyphs on the title screen.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Scene choice by digit (scenes 0, 2, 5 and 9 from the repacked disk) | OK: each scene's picture and its half-width filler message |
| Long message (6-line test): the box's pager | OK: lines 1-3, then 4-6 (lines 1-2 used to scroll out unread) |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
