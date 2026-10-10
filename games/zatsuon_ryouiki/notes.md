# Zatsuon Ryouiki (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Zatsuon Ryouiki/Zatsuon Ryouiki [HD]/Zatsuon Ryouiki.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ADL98** engine (`ADL98.EXE`): 30 scripts with text (`DAY1.EDT`, `DAY1A.EDT`, `DAY2.EDT`, `DAY2A.EDT`, `DAY2N.EDT`, `DAY2P.EDT`, `DAY2Z.EDT`, `END1.EDT`, `END10.EDT`, `END11.EDT`, `END12.EDT`, `END13.EDT`, `END14.EDT`, `END15.EDT`, `END16.EDT`, `END2.EDT`, `END3.EDT`, `END4.EDT`, `END5.EDT`, `END6.EDT`, `END7.EDT`, `END8.EDT`, `END9.EDT`, `EPL1.EDT`, `EPL2.EDT`, `FIN.EDT`, `GST.EDT`, `MENU2.EDT`, `PLO1.EDT`, `REPLAY.EDT`), the speaker name table (`NAME_F0.EDT`); `pc98tl/adl5.py` documents the script format (ADL98's scripts are coded: after a 4-byte prefix, each byte inverted) and the program patch (`pc98tl/adl.py` the characters and the tables), `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start to its end, every entry lands on a statement, and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `ZR/`).

* A script starts with its entries (the targets of its gotos, calls and menus, as offsets), so a rebuilt script has them moved with its statements.
* `ADL98.EXE` gets a helper in 512 bytes put in at the end of its code segment (the data and work segments after it move up, every relocation with them).  In a run of text, 20h (a character the engine skips) switches to half-width letters: ASCII drawn 8 dots wide from the BIOS 8x16 font into the graphics planes, in the text's colour (bold where the engine's text is), with the engine's own character wait and paging.  Before each English word the helper measures it against the window's right edge and starts a new line when it would not fit (a space at a line's start is not drawn): the windows a script uses change as it calls and jumps, so the wrap is the program's, not the patcher's.
* The speaker's name indents the text 10 cells; the engine's new line (06) waits for a key itself before it clears a full window.
* Speaker names, menu commands and the program's own strings take ASCII as well.

## Script

4660 strings: 7 program strings, 4642 messages, 11 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 4660 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A menu's choices (the messages right after a menu) should stay within one line: their `max_cells` is the widest the screen allows the menu's window.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* `{X1}`, `{X2}`...: the script's controls between the runs of a message (a key wait, a colour change, a new line, the next statement going on along the same line); the note says what each does.  Keep each once, in any order; a message without them all is refused.
* A script is read whole into a 64 KB segment: with its English it may take 65536 bytes.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build whose script outgrows its segment is refused and names the script and its strings.
* Speaker names (`n` ids): 10 letters (the slot the script gives the table, 19h); the text after them starts 10 cells in.  Longer ones are cut and reported.
* Menu commands (`c` ids): 16 letters (the slot the script gives the table, 18h); longer ones would run into the next command's, so they are cut and reported.
* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); a character the program writes in at run time (a drive letter, a digit) is `{X1}`..., kept in the English, which is placed so that it stays where the program writes it.  Longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logos, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release; MENU2.EDT, the display setting menu, clicked through | OK: boots (ADL98.EXE with the helper); filler half-width (8x16, graphics planes) in the white windows, wrapped by the helper between words at each window's own edge, paged; the menu's choices in their window (the choices come before the menu op: no widening, their max_cells is the window) |
| The game's days (DAY1 ...), the replay menu, save/load, endings | not yet seen |

KOM_F0.EDT (the command table) is not extracted: no script loads it (op 18h), so it is never shown.

In the menus here the choices are text statements before the menu op, in a window sized for the Japanese: an English choice longer than its max_cells wraps onto a second line, past the menu's rows.

The --pseudo build cuts its filler to fit the 64 KB script segment: DAY1.EDT by 13,572 letters, DAY1A.EDT by 1,653, DAY2.EDT (63,656 bytes in Japanese) by 53,446 and DAY2P.EDT by 36,444; DAY2.EDT leaves 1,880 bytes for English beyond the Japanese, so its English must stay about as long in bytes as the Japanese (the patcher refuses and names the strings otherwise).
