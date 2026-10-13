# Yuu Disk Vol. 4 - Crystal Rinal Otanoshimi Disk (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Yuu Disk Vol. 4 - Crystal Rinal Otanoshimi Disk/Yuu Disk Vol. 4 - Crystal Rinal Otanoshimi Disk [HD]/Yuu Disk Vol. 4 - Crystal Rinal Otanoshimi Disk.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ADL98** engine (`ADL98.EXE`): 12 scripts with text (`ADV.EDT`, `ASTORY.EDT`, `CML.EDT`, `KOUKI.EDT`, `MOGLA.EDT`, `MYCL.EDT`, `MZ.EDT`, `OM.EDT`, `QUIZ.EDT`, `SHU6.EDT`, `SLOT.EDT`, `VOFS.EDT`), the speaker name table and the menu command table (`KOM_F0.EDT`, `NAME_F0.EDT`); `pc98tl/adl5.py` documents the script format and the program patch (`pc98tl/adl.py` the characters and the tables), `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start to its end (where a table the walker never steps onto sits among the statements, the walk is picked up again at the next entry and the table moves as it is), and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `UD/`); the scripts and the tables are members of the archives `EDT00` and `EDT01` (a word, the entries' size; entries of a 12-byte name and a dword offset; the members), which the patch lays out anew.

* A script starts with its entries (the targets of its gotos, calls and menus, as offsets), so a rebuilt script has them moved with its statements.
* `ADL98.EXE` gets a helper in 512 bytes put in at the end of its code segment (the data and work segments after it move up, every relocation with them).  In a run of text, 20h (a character the engine skips) switches to half-width letters: ASCII drawn 8 dots wide from the BIOS 8x16 font into the graphics planes, in the text's colour (bold where the engine's text is), with the engine's own character wait and paging (a new line whose row would run past the window's bottom pages first).  Before each English word the helper measures it against the window's right edge and starts a new line when it would not fit (a space at a line's start is not drawn): the windows a script uses change as it calls and jumps, so the wrap is the program's, not the patcher's.
* The speaker's name indents the text by its name table's slot; the engine's new line (06) waits for a key itself before it clears a full window.
* Speaker names, menu commands and the program's own strings take ASCII as well.

## Script

900 strings: 5 menu commands, 7 program strings, 878 messages, 10 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 900 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A menu's choices (the messages right after a menu) should stay within one line: their `max_cells` is the widest the screen allows the menu's window.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* `{X1}`, `{X2}`...: the script's controls between the runs of a message (a key wait, a colour change, a new line, the next statement going on along the same line); the note says what each does.  Keep each once, in any order; a message without them all is refused.
* A script is read whole into a 64 KB segment: with its English it may take 65536 bytes.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build whose script outgrows its segment is refused and names the script and its strings.
* Speaker names (`n` ids): `max_cells` letters (8, the slot the script gives the name's table, 19h); the text after a name starts as many cells in as its table's slot.  Longer ones are cut and reported.
* Menu commands (`c` ids): `max_cells` letters (6: the slot the script gives the command's table, 18h, within the menu boxes drawn while it is loaded); longer ones would run into the next command's, so they are cut and reported.
* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); a character the program writes in at run time (a drive letter, a digit) is `{X1}`..., kept in the English, which is placed so that it stays where the program writes it.  Longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logos, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| ADL98: the title, the main menu (its eleven items, 71h text drawn at their places) | OK: the items half-width filler, one line each, the highlight bar on the item under the cursor; a click starts that item |
| The slot machine corner (the menu's fourth item): the speakers' lines, its command box | OK: filler half-width, wrapped between words in the window, paged; the command box's items half-width (cut at the screen's right edge, where the box sits) |
| The other corners, save/load | not yet seen |

This ADL98.EXE is an earlier build than Zatsuon Ryouiki's: its scripts are not coded, 9Ch is three bytes and AEh eleven, 0Dh is a control with a byte, and some scripts go on after an end (FFh) that their entries reach (pc98tl/adl5.py, variant adl98u).

The code segment's last routine runs on 11 bytes into the next segment (an instruction across the boundary); the helper's room goes in after that routine, not at the segment's start (pc98tl/adl.py _code_end).  At the segment's start the menu's highlight was lost.
