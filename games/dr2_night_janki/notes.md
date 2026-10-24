# DR^2 Night Janki (Leaf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `DR^2 Night Janki/DR^2 Night Janki [HD]/DR^2 Night Janki.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Leaf's mahjong program `NJ\NJ.EXE` (a C program, run by `HDNJ.BAT`), on the hard disk.  Every text of the game is a string in its data group: the story's and the matches' lines, the menus, the cards', characters' and hands' names, DOS's messages.  `pc98tl/leafnj_tl.py` documents it and writes the English.  A build with no English leaves the disk as it is.

* The program draws a string with one routine: a two-byte character from the CG ROM's kanji, a byte from its half-width row - but it swapped the code's bytes for a byte, so a byte was drawn as nothing.  The patch takes the swap out (two bytes), so English is drawn half-width as ASCII.
* Each string is written in place.
* `MTL_NOTE.TXT` is put in the game's folder (`NJ`).

## Script

358 strings: 354 lines, 4 program messages.

Translation and the content classification (♥) are done by the translation model; 0 of 358 strings have English so far.

## Limits

* Lines (`l` ids): each is drawn at its place on the screen (a speaker's name, its padding, the speech); up to `max_cells` letters, the Japanese's bytes (two letters for each full-width character); longer is cut and reported by string id.  `@` in a line starts a new line (keep the Japanese's ones where they are), and keep `%s`, `%d`, `%$d`.
* Program messages (`e` ids): DOS's, before their `$`: up to `max_cells` letters.
* English is ASCII; other characters are written as `?` (curly quotes, dashes and `…` are made ASCII).

## Not handled

* Text drawn into the pictures (`.LFG`: the title, its menu, the fonts' pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (HDNJ.BAT, NJ.EXE): the sound source menu, the title, the continue menu | OK: the menus' items in filler, half-width (the title and its menu are pictures) |
| A new game: the opening's narration and the first scene's message window | OK: each line in filler, half-width, at its place |

Not reached in this test: the matches' lines, the cards and the endings, so they are not seen on screen.
