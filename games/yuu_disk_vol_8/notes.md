# Yuu Disk Vol. 8 - Cybernoid Alpha Yuu Disk-ban (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Yuu Disk Vol. 8 - Cybernoid Alpha Yuu Disk-ban/Yuu Disk Vol. 8 - Cybernoid Alpha Yuu Disk-ban [HD]/Yuu Disk Vol. 8 - Cybernoid Alpha Yuu Disk-ban.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ADL98S** engine (`ADL98S.EXE`): 27 scripts with text (`PA_01.EDT`, `PA_02.EDT`, `PA_03.EDT`, `PA_04.EDT`, `PA_05.EDT`, `PA_06.EDT`, `PA_06A.EDT`, `PA_07.EDT`, `PA_08.EDT`, `PA_08A.EDT`, `PA_08B.EDT`, `PA_09.EDT`, `PA_10.EDT`, `PA_11.EDT`, `PA_12.EDT`, `PA_12A.EDT`, `PA_13.EDT`, `PA_14.EDT`, `PA_BA.EDT`, `PA_BA2.EDT`, `PA_M.EDT`, `PA_UR.EDT`, `PA_UR2.EDT`, `PA_ZK.EDT`, `S_05.EDT`, `S_40.EDT`, `S_41.EDT`), the speaker name table (`NAME_F0.EDT`); `pc98tl/adl5.py` documents the script format (ADL98's scripts are coded: after a 4-byte prefix, each byte inverted) and the program patch (`pc98tl/adl.py` the characters and the tables), `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start to its end (where a table the walker never steps onto sits among the statements, the walk is picked up again at the next entry and the table moves as it is), and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `SYB/`); the scripts and the tables are members of the archive `EDT00` (a word, the entries' size; entries of a 12-byte name and a dword offset; the members), which the patch lays out anew.

* A script starts with its entries (the targets of its gotos, calls and menus, as offsets), so a rebuilt script has them moved with its statements.
* `ADL98S.EXE` gets a helper in 512 bytes put in at the end of its code segment (the data and work segments after it move up, every relocation with them).  In a run of text, 20h (a character the engine skips) switches to half-width letters: ASCII drawn 8 dots wide from the BIOS 8x16 font into the graphics planes, in the text's colour (bold where the engine's text is), with the engine's own character wait and paging (a new line whose row would run past the window's bottom pages first).  Before each English word the helper measures it against the window's right edge and starts a new line when it would not fit (a space at a line's start is not drawn): the windows a script uses change as it calls and jumps, so the wrap is the program's, not the patcher's.
* The speaker's name indents the text 10 cells; the engine's new line (06) waits for a key itself before it clears a full window.
* Speaker names, menu commands and the program's own strings take ASCII as well.

## Script

1466 strings: 7 program strings, 1442 messages, 17 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 1466 strings have English so far.

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
| The hard-disk release; PA_01.EDT's setup menus (display, sound, wait), clicked | OK: boots (ADL98S.EXE with the helper; the scripts and tables read from and written back to the EDT00 archive); filler half-width in the framed windows, wrapped by the helper between words at each window's edge |
| The story (PA_02 ...), the battle scenes (S_xx), save/load, endings | not yet seen (the clicks keep choosing the same setup item) |

The scripts and ADL98S.EXE are byte for byte those of Cybernoid Alpha (its full release); a translation of this folder serves both.

KOM_F0.EDT (the command table) is not extracted: no script loads it (op 18h), so it is never shown.

Some scripts (the battle scenes S_xx, PA_14) hold tables the walker never steps onto (after AFh, records of 14h bytes the entries reach); the tokenizer picks the walk up again at the next entry and the tables move as they are.
