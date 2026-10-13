# Collector D (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Collector D/Collector D [HD]/Collector D.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ADL3B** engine (`ADL3B.EXE`): 53 scripts with text (`09.EDT`, `10.EDT`, `11.EDT`, `12.EDT`, `13.EDT`, `14.EDT`, `15.EDT`, `16.EDT`, `17.EDT`, `18.EDT`, `19.EDT`, `20.EDT`, `21.EDT`, `22.EDT`, `23.EDT`, `24.EDT`, `25.EDT`, `26.EDT`, `27.EDT`, `28.EDT`, `29.EDT`, `30.EDT`, `A.EDT`, `AH_T.EDT`, `AH_V.EDT`, `B.EDT`, `BAT.EDT`, `BH_T.EDT`, `BH_V.EDT`, `C.EDT`, `CH_T.EDT`, `CH_V.EDT`, `D.EDT`, `DH_T.EDT`, `DH_V.EDT`, `E.EDT`, `EDFD.EDT`, `EH_T.EDT`, `EH_V.EDT`, `ELV.EDT`, `F.EDT`, `FH_T.EDT`, `FH_V.EDT`, `G.EDT`, `GH_T.EDT`, `GH_V.EDT`, `H.EDT`, `HH_T.EDT`, `HH_V.EDT`, `K.EDT`, `MENU.EDT`, `MENU2.EDT`, `OPFD.EDT`), the speaker name table and the menu command table (`KOM_F0.EDT`, `NAME_10.EDT`, `NAME_F0.EDT`, `NAME_F5.EDT`, `NAME_F6.EDT`, `NAME_F8.EDT`); `pc98tl/adl5.py` documents the script format and the program patch (`pc98tl/adl.py` the characters and the tables), `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start to its end (where a table the walker never steps onto sits among the statements, the walk is picked up again at the next entry and the table moves as it is), and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `DL03/`).

* A script starts with its entries (the targets of its gotos, calls and menus, as offsets), so a rebuilt script has them moved with its statements.
* `ADL3B.EXE` gets a helper in 512 bytes put in at the end of its code segment (the data and work segments after it move up, every relocation with them).  In a run of text, 20h (a character the engine skips) switches to half-width letters: ASCII drawn 8 dots wide from the BIOS 8x16 font into the graphics planes, in the text's colour (bold where the engine's text is), with the engine's own character wait and paging (a new line whose row would run past the window's bottom pages first).  Before each English word the helper measures it against the window's right edge and starts a new line when it would not fit (a space at a line's start is not drawn): the windows a script uses change as it calls and jumps, so the wrap is the program's, not the patcher's.
* The speaker's name indents the text by its name table's slot; the engine's new line (06) waits for a key itself before it clears a full window.
* Speaker names, menu commands and the program's own strings take ASCII as well.
* `PCMSET.EXE` (run before the game) draws its lines with the same graphics drawer: it gets the same half-width letters (a 256-byte helper, put in the same way), and its lines are `e` strings too.

## Script

1062 strings: 10 menu commands, 28 program strings, 1006 messages, 18 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 1062 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A menu's choices (the messages right after a menu) should stay within one line: their `max_cells` is the widest the screen allows the menu's window.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* `{X1}`, `{X2}`...: the script's controls between the runs of a message (a key wait, a colour change, a new line, the next statement going on along the same line); the note says what each does.  Keep each once, in any order; a message without them all is refused.
* A script is read whole into a 64 KB segment: with its English it may take 65536 bytes.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build whose script outgrows its segment is refused and names the script and its strings.
* Speaker names (`n` ids): `max_cells` letters (6 to 20 by table, the slot the script gives the name's table, 19h); the text after a name starts as many cells in as its table's slot.  Longer ones are cut and reported.
* Menu commands (`c` ids): `max_cells` letters (6: the slot the script gives the command's table, 18h, within the menu boxes drawn while it is loaded); longer ones would run into the next command's, so they are cut and reported.
* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); a character the program writes in at run time (a drive letter, a digit) is `{X1}`..., kept in the English, which is placed so that it stays where the program writes it.  Longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logos, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| PCMSET.EXE (patched), the voice speed setting | OK: its lines half-width filler; the OK button goes on to the game |
| ADL3B: the opening's full-screen text window | OK: filler half-width (8x16, graphics planes), wrapped between words, a blank line between messages, paged with the window cleared whole |
| Menus, the rest of the story, save/load, endings | not yet seen |
