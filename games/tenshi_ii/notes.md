# Tenshi-tachi no Gogo II - Minako (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Gogo II - Minako/Tenshi-tachi no Gogo II - Minako [FD h01]/Tenshi-tachi no Gogo II - Minako (Disk A).d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's typed-command engine on self-booting 2HD floppies (D88, 256-byte sectors, records 1-19 of each track side).  The boot sector loads the engine, the word tables, the system messages and the font, and draws the title screen (the sound setup) from a run-length text-layer image.  61 scenes on the second disk are found through a table of 6-byte entries in the engine; each is a picture, a command table and the messages, found by count.  The player types commands, looked up in two tables of 5-glyph words (`pc98tl/jast_font12.py` documents the layout).

## English display (`pc98tl/jast_font12.py`)

* The game draws every character itself from its own font of 12x10 glyphs
  (text is one glyph number a byte).  English is two letters to a cell: a
  letter pair is two bytes, a first byte 09-16 (blank, unused glyph numbers)
  and a second byte numbering the pair.  The message draw's glyph call goes
  to a helper that builds the pair's glyph from a 6x10 font
  (`pc98tl/font6x10.py`) and draws it with the game's own routine; Japanese
  draws as before.
* Lines are padded with blank glyphs to the box edge (46 columns, 47 on the
  first line), where the engine wraps; the line scrolls in the message draw
  go through a pager.  The box shows 2 lines and starts each message empty:
  the pager waits for a key before a line would scroll out unread (at the
  message's first scroll, then every second one).
* The helpers, the 6x10 font and the moved system messages are one new
  block, loaded from a free track of the boot disk by the boot's own table
  load.
* Scenes are rebuilt with the English and written back to back on the second disk using all 26 records of a track (the engine's reader takes 26 a track on that disk and still 19 on the boot disk); the scene table follows.
* Typed commands: the word tables get the English words, typed and shown with the game's own A-Z glyphs, and the key tables give capitals for the letter keys.
* The title screen's Japanese is rewritten in its text-layer image.

## Script

1230 strings (908 scene text, 312 menu words, 10 title screen).

Translation and the content classification (♥) are done by the translation model; 0 of 1230 strings have English so far.

## Limits

* Messages (`m` ids, scene text and the system messages): `\n` starts a new line.  Letters and `.,'!?-` are drawn in pairs; digits and characters in the game's font (Japanese, brackets) use its own glyphs; anything else shows as `?`.
* Command words (`w` ids: `verb:` and `noun:` refs): up to 5 capital letters or digits, typed by the player; longer ones are cut and reported.
* The engine finds each command word anywhere in the typed line, trying the table's words in order, so a word must not contain an earlier word of its own table or a word of the other table (`SEE` inside `SEEK` makes `SEEK` read as `SEE`); the patcher reports each such pair by string id.
* Title screen (`t` ids): the cells of the Japanese (`max_cells`), two letters each.
* A rebuilt scene must fit the engine's 32 KB scene buffer, and all scenes the second disk; the patcher refuses a build that breaks either.
* The disks have no file system, so the machine-translation notice is `MTL_NOTE.TXT` next to the patched images instead of a file on the disk.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title screen (sound setup, text-layer image) | OK: filler in the Japanese's cells, boxes kept |
| Opening scene, message window | OK: half-width letter-pair filler inside the frame |
| Long message (7-line test): waits before a line would scroll out unread | OK: line 1, then lines 2-3, 4-5, 6-7, each pair after a key |
| Typed command (capitals from the letter keys) | OK: typed letters shown with the game's A-Z glyphs |
| Typed command to the next scene (scene 2 loaded from the repacked second disk) | OK: new scene's picture, its messages half-width filler inside the frame |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
