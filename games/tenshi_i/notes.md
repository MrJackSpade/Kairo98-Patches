# Tenshi-tachi no Gogo (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Gogo/Tenshi-tachi no Gogo [FD hdb]/Tenshi-tachi no Gogo.d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's first typed-command engine on one self-booting 2HD floppy laid out like an N88-BASIC disk (track 0 of 128-byte records, the game reading records 1-16 of the other tracks).  The boot loads the font and the engine; 60 scenes are found through a table of 6-byte entries in the engine, each a run-length picture, the messages and a command table.  The player types romaji commands, looked up in two tables of 4-glyph words; a framed help panel lists the commands (`pc98tl/jast_typed.py` documents the layout).

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

582 strings (148 menu words, 7 engine strings, 13 help panel rows, 414 scene text).

Translation and the content classification (♥) are done by the translation model; 0 of 582 strings have English so far.

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
| Title screen and opening message | OK: half-width letter-pair filler, wrapped to 53 cells |
| Help panel (command list) | OK: 12-letter filler in each framed row |
| Typed command to the next scene (school yard to the gym entrance, from the repacked disk) | OK: typed capitals shown; new scene's picture and filler message |
| Long message (9-line test): the box's own pager | OK: lines 1-4, 5-8, then 7-9 (line 1 used to scroll out unread) |
| Save and load prompts, game over | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
