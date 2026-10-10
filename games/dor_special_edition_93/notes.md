# DOR Special Edition '93 (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `DOR Special Edition '93/DOR Special Edition '93 (FD version) [HD]/DOR Special Edition '93 (FD version).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ADL5** engine (`ADL5.EXE`): 71 scripts with text (`AMAZO1.EDT`, `AMAZO2.EDT`, `AMAZO3.EDT`, `AMAZO4.EDT`, `B1.EDT`, `B2.EDT`, `B3.EDT`, `B4.EDT`, `DOOR.EDT`, `ENDING.EDT`, `FIRST.EDT`, `G1.EDT`, `G2.EDT`, `G3.EDT`, `G4.EDT`, `G5.EDT`, `G6.EDT`, `GOVER.EDT`, `H01.EDT`, `H02.EDT`, `H03.EDT`, `H04.EDT`, `H05.EDT`, `H06.EDT`, `H1.EDT`, `H2.EDT`, `ISEKI0.EDT`, `ISEKI3.EDT`, `ISEKI5.EDT`, `ITEM00.EDT`, `JUNG5B.EDT`, `JUNGLE1.EDT`, `JUNGLE2.EDT`, `JUNGLE3.EDT`, `JUNGLE4.EDT`, `JUNGLE5.EDT`, `JUNGLE6.EDT`, `JUNGLE7.EDT`, `JUNGLE8.EDT`, `JUNGLE9.EDT`, `MOVE.EDT`, `MOVIE.EDT`, `MS01.EDT`, `MS02.EDT`, `MS03.EDT`, `OP.EDT`, `Q.EDT`, `SC01.EDT`, `SC02A.EDT`, `SC02B.EDT`, `SC03.EDT`, `SC04A.EDT`, `SC04B.EDT`, `SC05A.EDT`, `SC05B.EDT`, `SC05BTA.EDT`, `SC05BTB.EDT`, `SC06A.EDT`, `SC06B.EDT`, `SC07A.EDT`, `SC07B.EDT`, `SC08A.EDT`, `SC08B.EDT`, `SC09A.EDT`, `SC09B.EDT`, `SENTOU1.EDT`, `SENTOU2.EDT`, `SENTOU6.EDT`, `SENTOU8.EDT`, `SENTOU9.EDT`, `SHOUJO.EDT`), the speaker name table and the menu command table (`COM_G1.EDT`, `COM_R.EDT`, `COM_S1.EDT`, `COM_S2.EDT`, `COM_S3.EDT`, `COM_S4.EDT`, `KOM_F0.EDT`, `NAME_F0.EDT`, `NAME_G1.EDT`, `NAME_S1.EDT`, `NA_R3.EDT`); `pc98tl/adl5.py` documents the script format and the program patch (`pc98tl/adl.py` the characters and the tables), `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start to its end (where a table the walker never steps onto sits among the statements, the walk is picked up again at the next entry and the table moves as it is), and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `DORSE1/`).

* A script starts with its entries (the targets of its gotos, calls and menus, as offsets), so a rebuilt script has them moved with its statements.
* `ADL5.EXE` gets a helper in 512 bytes put in at the end of its code segment (the data and work segments after it move up, every relocation with them).  In a run of text, 20h (a character the engine skips) switches to half-width letters: ASCII drawn 8 dots wide from the BIOS 8x16 font into the graphics planes, in the text's colour (bold where the engine's text is), with the engine's own character wait and paging (a new line whose row would run past the window's bottom pages first).  Before each English word the helper measures it against the window's right edge and starts a new line when it would not fit (a space at a line's start is not drawn): the windows a script uses change as it calls and jumps, so the wrap is the program's, not the patcher's.
* The speaker's name indents the text by its name table's slot; the engine's new line (06) waits for a key itself before it clears a full window.
* Speaker names, menu commands and the program's own strings take ASCII as well.
* `PCMSET2.EXE` (run before the game) draws its lines with the same graphics drawer: it gets the same half-width letters (a 256-byte helper, put in the same way), and its lines are `e` strings too.

## Script

7376 strings: 76 menu commands, 28 program strings, 7222 messages, 50 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 7376 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A menu's choices (the messages right after a menu) should stay within one line: their `max_cells` is the widest the screen allows the menu's window.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* `{X1}`, `{X2}`...: the script's controls between the runs of a message (a key wait, a colour change, a new line, the next statement going on along the same line); the note says what each does.  Keep each once, in any order; a message without them all is refused.
* A script is read whole into a 64 KB segment: with its English it may take 65536 bytes.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build whose script outgrows its segment is refused and names the script and its strings.
* Speaker names (`n` ids): `max_cells` letters (8 to 10 by table, the slot the script gives the name's table, 19h); the text after a name starts as many cells in as its table's slot.  Longer ones are cut and reported.
* Menu commands (`c` ids): `max_cells` letters (4 to 14 by table: the slot the script gives the command's table, 18h, within the menu boxes drawn while it is loaded); longer ones would run into the next command's, so they are cut and reported.
* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); a character the program writes in at run time (a drive letter, a digit) is `{X1}`..., kept in the English, which is placed so that it stays where the program writes it.  Longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logos, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| PCMSET2.EXE (patched), the voice speed setting | OK: its lines half-width filler, the two digits the program writes kept in place; the OK button goes on to the game |
| ADL5: the title, the opening (OP.EDT): a speaker's name and her lines, then the town | OK: the speaker name half-width with the text indented by its slot (the lines after it indented the same, no name, as in the unpatched game); filler half-width, wrapped between words, paged; the town map (MOVE.EDT) drawn |
| The town's command menus, the story's sections, save/load, endings | not yet seen |

The game's last routine in ADL5.EXE's code segment runs 13 bytes on into the next segment; the helper's room, put in between them, starts with a jump over itself so that routine goes on where its bytes moved (without it the town map stayed black).

Its tables are named NAME_/NA_ (names) and KOM_/COM_ (commands); each table's `max_cells` is the slot the scripts give it (19h, 18h), and for commands also the menu boxes drawn while it is loaded.
