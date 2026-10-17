# Zenith (Himeya Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Zenith/Zenith (FD version) [HD]/Zenith (FD version).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Foster's CINEMA engine in Himeya Soft's build (`ZENITH.COM` loads the archive's driver, FAD.BIN, from `ZENITH/A.FA1`; CINEMA.BIN runs the script, MB3N_H.BIN draws the text).  The archive is Foster's FA1 (a directory at its end, members compressed, a member written back stored).  The whole story is one script, ZT.BIN, run in a 64 KB segment; this build's 48h ops (its table at 57Ah, read by the dispatch with no bound) are in `pc98tl/cinema.py`'s BUILDS, which documents the formats; `pc98tl/cinema_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws bytes below 80h itself as half-width letters, so the English needs no program patch.  A message is the speaker's name on its first line and the speech after it: the name is a string of its own.
* The script is written again with every address in it moved with the text.  It ends with machine code op 00h calls (an animation's interrupt handler): it moves with the rest, its own addresses (found by following its code from op 00h's calls and from the handler it installs) moved with it.
* The patcher breaks the lines between words at 64 letters and, when the window's 3 rows are full, ends the page (\f) and waits for a key (op 11h, this build's wait with the blinking mark) before the rest.

## Script

554 strings: 2 program messages, 16 menu items, 530 messages, 6 speakers' names.

Translation and the content classification (♥) are done by the translation model; 0 of 554 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 64 letters, paged after 3 rows.  `\n` in the English forces a new line.  A message the Japanese splits around a wait (`:1` in its ref) is two strings, shown one after the other.  The script with its English must fit its 64 KB segment: a build past it is refused and names the script.
* Speakers' names (`n` ids): one line, `max_cells` the Japanese's (past it cut).
* Menu items (`i` ids, the save and load menus): one line in the menu's box, `max_cells` the menu's widest Japanese item; past it reported.
* Program messages (`e` ids): ZENITH.COM's, printed by DOS when memory or a file is missing, in their own bytes, `max_cells` the room; past it cut and reported.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`; a backslash (the commands' mark) as `/`.

## Not handled

* Text drawn into the pictures (the title and its sound-source menu, the logo).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (ZENITH.COM, the FD version's): the sound-source menu (FM), the title menu (START) | OK: both menus are the pictures' and as in the original |
| The opening's first scene (ZT.BIN, about 6 keys) | OK: each speaker's name in filler on the first row, the speech in filler under it, half-width; a message the Japanese splits around a wait shown in its two pieces; the blinking key mark after each, a key going on; the pictures changing with the scene |

Not reached in this test: the save and load menus (the menu items), the later scenes, the endings.
