# Minimum Guynarock (TechnoGrard)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Minimum Guynarock/Minimum Guynarock [FD]/Minimum Guynarock.hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-23 (`research/clearance.json`).

## Engine

A compiled QuickBASIC 4.x program (`MG.EXE`, EXEPACKed, run by `AUTOEXEC.BAT` from the self-booting floppy) with the whole script in it: string constants in its data group, each a descriptor (a length and a place).  `pc98tl/qbasic.py` documents the format and the patch, `pc98tl/qbasic_tl.py` the English.  A build with no English leaves the disk as it is.

* Each changed string's descriptor is pointed at its English in a block after the data group's data; the runtime's string space and the start-up's stack are moved past it, and the program is written back unpacked.
* The story's routine draws its text a character at a time, 4 columns a step; a helper in the runtime's padding makes the step 2 for a one-byte character, so ASCII letters stand half a full-width character apart.  The routine breaks a line at the window's edge itself; the patcher breaks the English between words and puts a wait for a key and a cleared window after each window's 5 lines.
* The speakers' names are PRINTed whole: their English is written as NEC's two-byte half-width characters (a full-width character after them shows right only after an even count of letters, so an odd count is evened with two spaces).
* `INSTALL.EXE` (which puts MS-DOS on the game's floppy) has its messages' lines written in place.
* `MTL_NOTE.TXT` is put on the floppy.

## Script

105 strings: 3 opening lines, 71 messages, 8 speakers' names, 23 program messages.

Translation and the content classification (♥) are done by the translation model; 0 of 105 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 26 letters, 5 lines a window, more windows after a key.  `{S1}`-`{S8}` start a speaker's line (the name from `n0000N`), `{S0}` a line without a name, `\n` a new line, `{W}` a key and the window cleared: keep each `{S..}` and `{W}`.
* Opening lines (`l` ids): one line each, up to `max_cells` letters; longer is reported by string id.
* Speakers' names (`n` ids): up to 8 letters; longer is cut and reported by string id.
* Program messages (`e` ids): in place, up to `max_cells` letters; longer is cut and reported by string id.
* All the English must fit the data group (64 KB, about 48 KB of English); a build past it is refused.
* English is ASCII; other characters are written as `?` (curly quotes, dashes and `…` are made ASCII).

## Not handled

* Text drawn into the pictures (`.SZH`: the title, the staff roll).
* `MG.DOC` on the floppy (the installing notes), read outside the game.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Pseudo build boots (np21w) | OK: the opening's lines in ASCII under the pictures, then the title |
| First scenes (pseudo) | OK: speakers' names half-width in the window's column, messages broken between words at 26 letters, 5 lines a window, the rest after a key |
| Installer (pseudo, run from the prompt) | OK: its messages' lines in place, the cancel message after ESC |
| Partly translated build | OK: names and a long message in English over two windows; the rest in Japanese as before |
| Unmodified build | OK: a build with no English is the source image byte for byte |

Past the first scenes the boot test did not play; every message goes through the same routine.
