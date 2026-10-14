# Wizard and the Princess (Starcraft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Wizard and the Princess/Wizard and the Princess (2HD conversion) [FD]/Wizard and the Princess (2HD conversion).d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).  The English releases VNDB lists are Sierra's original game and a remake, not a translation of this one.

## Engine

An N88-DISK BASIC disk: `M98` (a protected BASIC program) loads the engine `WIDRY.ASM` (machine code) at segment 1800h, which reads each room's record from `RDA` (and a common record from `MDA`) by absolute sectors and prints its messages (runs `01h text 0`, a room's description at its record's 500h) through BASIC's console, a whole span at a time.  `pc98tl/widry.py` documents it, `pc98tl/widry_tl.py` the English.  A build with no English leaves the files as they are.

* English at any length: the engine's span printer is made to go through a helper put after it; the helper looks the span's Japanese up in a table (`WIDRY.ENG`, which `M98` loads at 3000h:0) and prints the English a word at a time through the printer's own path, which breaks lines between words and waits for a key after four lines.
* The data files stay as they are: the parser takes the game's own katakana words (the player types katakana commands, as in the original).

## Script

731 strings: 731 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 731 strings have English so far.

## Limits

* Messages (`m` ids): any length; lines broken between words at 79 columns by the engine, `\n` a new line.  The same Japanese is one string everywhere (the engine finds its English by the Japanese).  Some messages are pieces the game prints one after another (an object's name, then a verb's ending): their English follows on the same line.
* English is ASCII; anything else is written as `?`.
* The English all together goes in one 64K table: a build over it is refused.

## Not handled

* The parser's vocabulary (the player types the game's katakana words).
* The engine's few strings printed at a length of their own (its function keys' labels, the save slot prompt) and text drawn into the pictures.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the floppy (BASIC, M98): the first room | OK: its description in filler, half-width, on the picture's text rows |
| Type LOOK (not a word of the game's) | OK: the parser's reply in filler, broken between words, the description again in filler |
| Kana lock, type ｷﾀ (north) | OK: the next room (the snake) with its description in filler; another command's reply in filler |

Not reached in this test: the rooms past the second, saving and loading, the ending.
