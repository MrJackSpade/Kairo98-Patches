# De.FaNa (Himeya Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `De.FaNa/De.FaNa (FD version) [HD]/De.FaNa (FD version).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Foster's CINEMA engine in Himeya Soft's build (`DEFANA.COM` loads the archive's driver, FAD.BIN, from `DEFANA/A.FA1`; CINEMA.BIN runs the script, MB3N_H.BIN draws the text).  The archive is Foster's FA1 (a directory at its end, members compressed, a member written back stored).  The scripts (DE_*.BIN, DI.BIN) run one at a time in a 16 KB buffer; this build's ops (3Dh ops and 7Fh-8Fh, its table at 238Ch; 31h the gosub, 32h the return, 8Dh a message too) are in `pc98tl/cinema.py`'s BUILDS, which documents the formats; `pc98tl/cinema_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws bytes below 80h itself as half-width letters, so the English needs no program patch.  A message is the speaker's name on its first line and the speech after it: the name is a string of its own.
* A script is written again with every address in it moved with the text.
* The patcher breaks the lines between words at 68 letters and, when the window's 3 rows are full, ends the page (\f) and waits for a key (op 11h, this build's wait with the blinking mark) before the rest.

## Script

1279 strings: 2 program messages, 80 menu items, 1188 messages, 9 speakers' names.

Translation and the content classification (♥) are done by the translation model; 0 of 1279 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 68 letters, paged after 3 rows.  `\n` in the English forces a new line.  A message the Japanese splits around a wait (`:1` in its ref) is two strings, shown one after the other.  A script with its English must fit its 16 KB buffer: a build past it is refused and names the script.
* Speakers' names (`n` ids): one line, `max_cells` the Japanese's (past it cut).
* Menu items (`i` ids, the save and load menus): one line in the menu's box, `max_cells` the menu's widest Japanese item; past it reported.
* Program messages (`e` ids): DEFANA.COM's, printed by DOS when memory or a file is missing, in their own bytes, `max_cells` the room; past it cut and reported.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`; a backslash (the commands' mark) as `/`.

## Not handled

* Text drawn into the pictures (the title and its sound-source menu, the logo).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (DEFANA.COM: CINEMA.BIN, DI.BIN): the sound choice and the title menu | OK: the line under the sound choice in filler, half-width, broken between words (the menus are pictures) |
| Start a game: the first scene (DE_01.BIN) and its messages | OK: the speaker's name and each message in filler, half-width, broken between words at the program's 68-letter lines, the rest after a key |

Not reached in this test: the menus of choices inside the story, the save screen and op 8Dh's animated messages, so they are not seen on screen.
