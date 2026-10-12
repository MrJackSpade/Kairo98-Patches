# Mashou no Kao (Mink)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Mashou no Kao/Mashou no Kao [HD]/Mashou no Kao.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`AVS96.EXE`, Mink's "Game System AVS96" (Microsoft EXEPACK): the `*.BIN` scripts are packed bytecode with the text in them.  The patcher writes a changed script again (its jumps and calls moved) and packs it; a script past its 64 KB segment is split into further files, its scenes reached through a variable and the script-loading command both ways.  `pc98tl/avs96.py` documents the format, `pc98tl/avs96_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws only its own 24-dot font (the game's kana and kanji, a few capitals).  The patched program draws English as letter pairs, two kanji-ROM ANK letters in one 24-dot cell, 12 dots each (as for pc98tl/illusion_font24.py); a cell is two half-width letters.
* The game is played with the mouse; the right button opens the program's menu.

## Script

5743 strings: 137 menu items, 31 program strings (its menu, the save slots), 5574 messages, 1 a character's name.

Translation and the content classification (♥) are done by the translation model; 0 of 5743 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` 52, letters a line holds): any length.  The window is 26 cells (52 letters) by two rows; the patcher breaks the English between words and pads a line to the window's edge, and the program waits for a click when the window is full.  `\n` forces a new line.  `{NAME}` is the hero's name (＠００), counted as 5 cells; keep it.
* Menu items (`i` ids): one line in the menu's box, 18 letters; past it reported.
* The hero's name as the game starts (`n` id): 20 letters at most (the program keeps 20 bytes); past it cut and reported.
* Program strings (`l` ids: its menu, the save slots): in place, `max_cells` their room in letters; past it cut and reported.
* English is ASCII (pairs); another character is written full-width (a cell) when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the title's logo, the staff's names in the opening).
* The name-entry screen (CONFIG.BIN, `m00009`-`m00022`): its rows of kana are the grid the player picks the hero's name from (the program's kana table); a name entered there is kana.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk: the load menu (CONFIG.BIN), its first item clicked | OK: the menu's title and items in filler, letter pairs half-width; the items kept to the box |
| The opening (timed) and the first scene's messages, a click after each | OK: the messages in filler half-width, broken between words, a line padded to the window's edge, two rows then a click; the game goes on into the first room scene |
| The right button in the first scene: the program's menu | OK: the program's own strings in filler, in place, each within its room |
| A test build with S001.BIN split (every scene moved to S001A.BIN), the same steps | OK: the same screens: the scenes are reached from the hub in the other file and return to it |
