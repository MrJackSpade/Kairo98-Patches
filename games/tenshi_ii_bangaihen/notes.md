# Tenshi-tachi no Gogo II Bangaihen (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Gogo II Bangaihen/Tenshi-tachi no Gogo II Bangaihen [FD h01]/Tenshi-tachi no Gogo II Bangaihen (Disk A).d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's menu engine on self-booting 2HD floppies (D88, 256-byte sectors, records 1-19 of each track side), a sibling of Tenshi II - Minako's engine with commands picked from menus.  The boot sector loads the engine, the word block and the font block (system messages, then the font), and draws the title screen (the sound setup) from a run-length text-layer image.  54 scenes on the second disk are found through a directory on its first track; each is a header, a command table, the messages (found by count) and the menus (lists of word numbers).  `pc98tl/jast_menu12.py` documents the layout.

## English display (`pc98tl/jast_menu12.py`)

* The game draws every character itself from its own font of 12x10 glyphs
  (text is one glyph number a byte).  English is two letters to a cell: a
  letter pair is two bytes, a first byte from glyph numbers that are blank
  and unused by the script, and a second byte numbering the pair.  The
  message draw's and the menu draw's glyph lookups go to helpers that build
  the pair's glyph from a 6x10 font (`pc98tl/font6x10.py`) and hand it to
  the game's own draw; Japanese draws as before.
* Message lines are padded with blank glyphs to the window edge, where the
  engine wraps.  The main box is 3 lines of 40 cells that scroll; its
  scroll goes through a pager, which waits for a key before a scroll once 3
  lines of the message have been shown.  The opening's one-line window wraps
  at its frame, and a wrap there waits for a key, blanks the line and goes
  on in place.
* The helpers and the 6x10 font sit in the unused tail of the font's third
  bank, which the boot already loads.  The nouns move above the engine (the
  boot's engine load grows to cover them); the verbs, system messages and
  the save and load prompts are rebuilt in the word block, which the boot's
  word load reads over the old system messages.
* Scenes are rebuilt with the English; one that outgrows its sectors moves to
  free sectors of the scene disk.
* The title screen's Japanese is rewritten in its text-layer image.

## Script

1225 strings (10 title screen, 175 menu words, 1040 scene text).

Translation and the content classification (♥) are done by the translation model; 0 of 1225 strings have English so far.

## Limits

* Messages (`m` ids: scene text, the system messages and the engine's save and load prompts): `{A<n>}` are the talking face's animation controls (not drawn; keep them), `\n` starts a new line.  Letters and `.,'!?-` are drawn in pairs; digits and characters in the game's font (Japanese, brackets) use its own glyphs; anything else shows as `?`.
* The main box is 40 cells a line and pages by itself (any number of lines).  The opening's one-line window (the messages of scenes 4, 5 and the load prompt) is 44 cells; longer messages there page a line at a time.
* Menu words (`w` ids: `verb:` and `noun:` refs): 8 cells (16 letters); longer ones are cut and reported.
* Title screen (`t` ids): the cells of the Japanese (`max_cells`), two letters each.
* A rebuilt scene must fit the engine's 4 KB scene buffer, the nouns the space above the engine (2816 bytes) and the verbs, system messages and prompts the word block (2560 bytes); the patcher refuses a build that breaks one.  Grown scenes move to free sectors of their disk and their directory entry is updated.
* The disks have no file system, so the machine-translation notice is `MTL_NOTE.TXT` next to the patched images instead of a file on the disk.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title screen (sound setup, text-layer image) | OK: filler in the Japanese's cells, boxes kept |
| Opening's one-line window | OK: half-width letter-pair filler inside the frame; a long line waits for a key, then goes on in the cleared line (checked with a 3-page test line) |
| Main message box | OK: filler wrapped to 40 cells inside the frame; a 7-line test message pages 1-3, 4-6, then 5-7 |
| Verb and noun menus | OK: 16-letter filler in the 8-cell menu entries; cursor and noun lists work |
| Scenes past the opening (night exterior, living room; grown scenes moved on the scene disk) | OK |
| Save and load prompts | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
