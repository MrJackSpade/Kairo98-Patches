# Kurayami (Melody)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Kurayami/Kurayami [HD]/Kurayami.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).  VNDB lists an English release for Windows (*In Darkness*), another platform's: its script may be ported.

## Engine

Melody's MAX Adventure Scenario Driver (`MAXG.EXE`, encrypted over LZEXE) under MS-DOS, started by `YAMI.COM`; the files are in PCK archives served by Melody's disk driver EXDD (`pc98tl/maxpck.py`: the archive, and MAXPACK, its LZSS).  The scenario is bytecode scripts (`*.MDR` in `MDR.PCK`): messages, dialogue with a speaker's name, chapter titles, menus of choices, string variables and the staff roll.  `pc98tl/maxadv.py` documents it, `pc98tl/maxadv_tl.py` the English.  A build with no English leaves the disk as it is.  The game needs the GDC at 2.5 MHz (game.json `dipsw`).

* English at any length: each record with English is written again, in its place when it fits, else in the room another moved record left or at the script's end, with a goto to it and one back; nothing else in the script moves.  The scripts are packed again into `MDR.PCK`.
* The engine draws ASCII half-width itself.  The patcher breaks the English between words at 54 columns and makes a page of every three lines, each page but the last ending with the game's own wait; a line of dialogue repeats its speaker's name on each page.
* The engine's own strings (its system menu, save and load screens, messages) are written in place and the engine is written out unpacked; the settings' values kept in `SYSTEM.DAT` follow the menu's English.  The launcher's text is written in place.
* `MTL_NOTE.TXT` is put in the game's folder (`MELODY\YAMI`).

## Script

15901 strings: 367 menu choices, 9653 lines of dialogue, 157 program strings, 6 launcher texts, 5619 messages, 34 speaker names, 1 staff roll, 4 words kept in variables, 60 chapter titles.

Translation and the content classification (♥) are done by the translation model; 0 of 15901 strings have English so far.

## Limits

* Messages (`m`), dialogue (`d`), titles (`t`), choices (`c`), variables (`v`), the staff roll (`r`): any length; messages and dialogue broken between words at 54 columns and paged by three lines; `\n` a new line.  A speaker's name (`n`) counts in its line's first row.
* `{@xx}` codes must be kept: `{@cX}` a colour, `{@sN}` a speed, `{@wN}` a pause, `{@m0}` the hero's name (counted as 8 columns), `{@mN}` another value.  The patcher warns by string id when they differ from the Japanese's.
* A menu choice (`c`) is one line; keep each short (the menu is as wide as its longest item).
* Each script, with its English, must fit the engine's 64K script buffer: a build over it is refused with the script's name.
* Program strings (`e`) and the launcher's text (`l`): in place, `max_cells` bytes; longer is cut and reported by string id.  In `l`, `\n` takes two bytes.
* English is ASCII; anything else is written as `?`, and `@` (the codes' mark) as `?` too.

## Not handled

* Text drawn into the pictures (the title, the name-entry screen's letters, which stay as they are so a name can be picked).
* The installer (`HDINST.EXE`), which the hard-disk image does not use.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (GDC 2.5 MHz): the launcher (YAMI.COM) | OK: its menu in filler, in place, half-width DOS text |
| The title, then the start-up messages | OK: messages in filler, half-width, broken between words in the message window |
| The start menu (choices) | OK: every choice in filler; the second picked opens the name screen, the first (Up, Return) starts the game |
| The opening narration (YM001) and the first dialogue (YM002), about 70 clicks | OK: lines in filler; a long message pages after three lines with the game's wait cursor and goes on; dialogue shows its speaker's name in filler before the line |
| Right click: the engine's system menu | OK: its items and the settings' values in filler (the engine written out unpacked) |

Not reached in this test: the menus of choices inside the scenes, saving and loading, the endings and the staff roll.
