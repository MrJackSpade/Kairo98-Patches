# Tenkousei (Space Project)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenkousei/Tenkousei [HD]/Tenkousei.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`CHOREOV.EXE`, Arigata-ya's "Choreographer Inter-Book View Finder": the `*.SCE` scenarios are bytecode for a stack machine, the text in them (Shift-JIS, a string with its length).  The patcher writes the scenarios again with the English, the jumps and the calls between scenarios moved to where their operations now are.  `pc98tl/choreo.py` documents the format, `pc98tl/choreo_tl.py` the English.  Unchanged files rebuild byte for byte.

* The game is played with the mouse.
* The program draws ASCII half-width by itself.  The message box is 36 half-width cells wide; the program breaks a line at its edge (mid-word) and pages a full box (▼).  A message is built from pieces (a speaker's name, a paragraph), each going on where the last ended; the patcher breaks the English between words, following the column across a box's pieces.

## Script

899 strings: 247 choices and buttons, 9 pieces of the date line, 3 menu titles, 640 message texts.

Translation and the content classification (♥) are done by the translation model; 0 of 899 strings have English so far.

## Limits

* Message texts (`m` ids, `max_cells` 35): any length; the patcher breaks the English between words at 35 half-width cells (a full line's new line would leave an empty one) and the program pages the box.  `\n` forces a new line; keep a piece's leading `\n` (its paragraph break), as a piece without one goes on from where the last ended.
* The date line (`d` ids: month, day, weekday): its box first shows the line's last 12 half-width cells, the numbers taking 4; `max_cells` is each piece's share (month 2, day 2, weekday 4); past it reported.
* Choices (`c` ids: the choice box, 24 cells; the title menu's buttons, 15; the システム button, 4) and menu titles (`u` ids): one line, `max_cells` the room; past it reported.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk: the title menu (the mouse on its first button, a click) | OK: the game starts; the menu title and the buttons in filler half-width |
| The first scene's messages, a click after each | OK: the messages in filler half-width, broken between words inside the 36-cell box, the box paged by the program; the date line (filler in its pieces) and the clock |
| The first choice (the mouse to the choice box, a click) and the next day's messages | OK: the choice and its menu title in filler; the next scene plays (the scenarios' jumps and calls moved); the paragraphs' breaks kept |
