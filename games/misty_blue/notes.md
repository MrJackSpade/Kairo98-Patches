# Misty Blue (Enix)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Misty Blue/Misty Blue [FD]/Misty Blue (Disk A).hdm` (sha256 in `strings.json`), with disks B and C beside it.
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Enix's own engine on its own DOS (ENIX.DOS), three floppies.  Disks A and C each have a `MAIN.EXE` (EXEPACK) that loads scene modules and, per scene, a text bundle (`*.BUN`) into its data segment; the text is a code of its own (one or two bytes a character).  Disk B also carries the bonus game (*えにっくす くえすと*, booted from disk B): its own `MAIN.EXE` running `.MES` scripts with Shift-JIS text.  `pc98tl/misty.py` documents the story's engine, `pc98tl/misty_mes.py` the bonus game's, `pc98tl/misty_tl.py` the English.  A build with no English leaves the disks as they are.

* Story: English drawn two half-width letters a cell from the BIOS font by a helper the decoder goes through; the helper breaks lines between words at the window's edge.  The English's most frequent words are kept in a dictionary in `MAIN.EXE` (a code each) so the bundles fit their room.  The helper and dictionary are appended after the program's image (EXEPACK repacked, the unpacker's stack moved up with it).
* The program's prompts (disk change, save and load) and the opening credits in the scene modules are written in place.  The modules' text-screen writer (the bonus game's start-up screen, the disk prompts) is rewritten in its own bytes to take half-width letters.
* Bonus game: each text in a script becomes a reference to a table of English put after its `MAIN.EXE`'s image, with a helper that draws it half-width, breaks lines between words and, when a window is full, waits for Return and clears it.  The scripts get shorter (the scripts place their own music and maps right after themselves).  The names the bonus game keeps (the hero, the monsters) are references too, and the save on disk A (`FLAG0`) has its names rewritten the same way.
* `MTL_NOTE.TXT` is put on disk A; the patched B and C are written as `<out> - Misty Blue (Disk B).hdm` and `(Disk C)`.

## Script

4668 strings: 10 bonus-game menu choices, 4637 messages, 12 program prompts, 9 text-screen and DOS texts.

Translation and the content classification (♥) are done by the translation model; 0 of 4668 strings have English so far.

## Limits

* Messages (`m`): any length, broken between words at the window's edge; `\n` a new line.  The story's bundles must fit their room in the data segment (B000h-FC00h): a build over it is refused with the bundle's name (the dictionary of frequent words keeps the English compact).  The bonus game's English must fit its program's segment (about 50 KB): a build over it is refused.
* Prompts (`p`): in place, `max_cells` letters; keep each `{D}` (a digit), in order.
* Texts (`t`): in place, `max_cells` letters, a letter a column.
* Choices (`c`): the bonus game's menus draw each choice in a box of a fixed width: `max_cells` letters.
* Longer `p`, `t` or `c` is cut and reported by string id.
* Story English uses letters, digits and `.,'"!?-:;()`; the bonus game's any ASCII (`"` is written as `'`, `|` as `/`); anything else as `?`.

## Not handled

* Text drawn into the pictures (titles, the bonus game's status panel).
* `SOC.DAT` on disk B: a leftover directory listing nothing reads.
* The bonus game's debug screens (flag editor) are written in place like the other texts but are not reachable in normal play.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot disk A (disk B in drive 2): the start menu | OK: its four choices in filler, half-width, the cursor bar on the first |
| Start from the beginning: the opening's pictures, the title, then the first scene (about 180 s, Return) | OK: messages in filler, half-width two letters a cell, broken between words; a message's next line in the window; the wait cursor shows |
| The menu's second choice (load): the load prompt | OK: the prompt in filler in place, its two digits kept |
| The menu's fourth choice: the bonus game's start-up screen (the text-screen writer) | OK: both lines in filler, half-width, in place |
| The bonus game (disk B in drive 1, disk A in drive 2): the opening talk | OK: messages in filler, half-width, broken between words; a full window waits for Return, is cleared and goes on |
| F1 (load), Return: the town from the save on disk A; F3 (items); F2 (save) | OK: the load and save prompts and their choices in filler (choices cut to their boxes); the item list in filler over three lines with the counts; the town as in the original |
| Walking the town to a battle (the Benz man), Return through two rounds | OK: the battle's choices and messages in filler, the monster's name (kept in its buffer) and the damage numbers in the lines |

Not reached in this test: the disk-change prompts (later in the story), the story's own save and load screens, the bonus game's shops and its ending, the end of the story.
