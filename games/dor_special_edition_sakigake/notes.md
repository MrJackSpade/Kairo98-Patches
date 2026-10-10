# DOR Special Edition Sakigake (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `DOR Special Edition Sakigake/DOR Special Edition Sakigake [HD]/DOR Special Edition Sakigake.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ADL3A** engine (`ADL3A.EXE`): 20 scripts with text (`H1.EDT`, `H2.EDT`, `H3.EDT`, `H4.EDT`, `H5.EDT`, `H6.EDT`, `H7.EDT`, `KAI.EDT`, `NEBU.EDT`, `SAKI_OP.EDT`, `SES00.EDT`, `SES01.EDT`, `SES02.EDT`, `SES04.EDT`, `SES05.EDT`, `SES06.EDT`, `SES07.EDT`, `SES08.EDT`, `SES09.EDT`, `SES10.EDT`), the speaker name table and the menu command table (`KOM_F1.EDT`, `NAME_F0.EDT`, `NAME_F1.EDT`, `NAME_F2.EDT`); `pc98tl/adl5.py` documents the script format and the program patch (`pc98tl/adl.py` the characters and the tables), `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start to its end (where a table the walker never steps onto sits among the statements, the walk is picked up again at the next entry and the table moves as it is), and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `DORSE0/`).

* A script starts with its entries (the targets of its gotos, calls and menus, as offsets), so a rebuilt script has them moved with its statements.
* `ADL3A.EXE` gets a helper in 512 bytes put in at the end of its code segment (the data and work segments after it move up, every relocation with them).  In a run of text, 20h (a character the engine skips) switches to half-width letters: ASCII drawn 8 dots wide from the BIOS 8x16 font into the graphics planes, in the text's colour (bold where the engine's text is), with the engine's own character wait and paging (a new line whose row would run past the window's bottom pages first).  Before each English word the helper measures it against the window's right edge and starts a new line when it would not fit (a space at a line's start is not drawn): the windows a script uses change as it calls and jumps, so the wrap is the program's, not the patcher's.
* The speaker's name indents the text 10 cells; the engine's new line (06) waits for a key itself before it clears a full window.
* Speaker names, menu commands and the program's own strings take ASCII as well.
* `PCMSET.EXE` (run before the game) draws its lines with the same graphics drawer: it gets the same half-width letters (a 256-byte helper, put in the same way), and its lines are `e` strings too.

## Script

2771 strings: 7 menu commands, 25 program strings, 2716 messages, 23 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 2771 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A menu's choices (the messages right after a menu) should stay within one line: their `max_cells` is the widest the screen allows the menu's window.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* `{X1}`, `{X2}`...: the script's controls between the runs of a message (a key wait, a colour change, a new line, the next statement going on along the same line); the note says what each does.  Keep each once, in any order; a message without them all is refused.
* A script is read whole into a 64 KB segment: with its English it may take 65536 bytes.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build whose script outgrows its segment is refused and names the script and its strings.
* Speaker names (`n` ids): 10 letters (the slot the script gives the table, 19h); the text after them starts 10 cells in.  Longer ones are cut and reported.
* Menu commands (`c` ids): 4 letters (the slot the script gives the table, 18h); longer ones would run into the next command's, so they are cut and reported.
* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); a character the program writes in at run time (a drive letter, a digit) is `{X1}`..., kept in the English, which is placed so that it stays where the program writes it.  Longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logos, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| PCMSET.EXE (patched), the voice speed setting | OK: its lines half-width filler; the OK button goes on to the game |
| ADL3A: the title, the opening (the elf in the forest), the first menu | OK: filler half-width (8x16, graphics planes), wrapped between words in the small text window, paged; the menu's message window and its command box (4 letters, the table's slot) |
| The rest of the story, save/load, endings | not yet seen |

The title screen waits for Return (clicks do not go on), in the unpatched game as well.
