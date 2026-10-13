# Ace of Spades (LoveGun)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Ace of Spades/Ace of Spades [HD]/Ace of Spades.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`ACE.EXE` with its scripts in `*.S` files: a length and a line count, then lines of JIS characters stored as words, low byte first, each ended by a 0.  The program draws a line a 16x16 cell a character, each glyph read from the font ROM (int 18h AH=14h), into a line buffer of 36 cells.  `pc98tl/ace.py` documents the format, `pc98tl/ace_tl.py` the English.  Unchanged files rebuild byte for byte.

* Half-width English: two letters go in one cell, written as one word (the second letter with bit 7 set, which no JIS row has).  The program's glyph reader is given a helper that draws such a cell from the BIOS's 8x16 font, a letter in each half; the helper goes in after the code segment's last routine, the segments after it moved up.
* The program pages a scene's lines in its message window itself (▼ and a key).

## Script

828 strings: 63 program strings (the menus), 757 script paragraphs, 8 speaker lines.

Translation and the content classification (♥) are done by the translation model; 0 of 828 strings have English so far.

## Limits

* Script paragraphs (`m` ids): any length.  The patcher breaks the English between words at 72 half-width letters (the line's 36 cells) and writes the script again with as many lines as it needs; `\n` forces a new line.
* Speaker lines (`n` ids): one line, 72 half-width letters.
* Program strings (`u` ids, the menus): written in place, `max_cells` half-width letters (two to a word); longer is cut and reported.
* English is ASCII; another character is written full-width when JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the title logo, the cards).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (AH.BAT: NA.COM, ACE.EXE): the title menu, Enter for the start menu | OK: every menu item in filler half-width, two letters a cell, inside its box; the title picture intact |
| Start: the opening scene's message window, Enter through its pages | OK: the speaker line and the paragraphs in filler half-width, broken between words at 72 letters a line, paged by the program with its marker |

Not reached in this test: poker and blackjack play, the scenes past the opening, the graphics and music rooms.
