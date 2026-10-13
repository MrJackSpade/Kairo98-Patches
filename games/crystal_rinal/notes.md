# Crystal Rinal (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Crystal Rinal/Crystal Rinal (CD version) [HD]/Crystal Rinal (CD version).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ADL21** engine (`ADL21.EXE`): 85 scripts with text (`BATLE.EDT`, `CX00.EDT`, `CX01.EDT`, `CX02.EDT`, `CX03.EDT`, `CX06.EDT`, `CX08.EDT`, `CX11.EDT`, `CX13.EDT`, `CX14.EDT`, `CX15.EDT`, `CX17.EDT`, `CX18.EDT`, `CX19.EDT`, `CX20.EDT`, `CX21.EDT`, `CX22.EDT`, `CX23.EDT`, `CX24.EDT`, `CX26.EDT`, `CX28.EDT`, `CX29.EDT`, `CX30.EDT`, `CX32.EDT`, `CX34.EDT`, `CX35.EDT`, `CX36.EDT`, `CX37.EDT`, `CX41.EDT`, `CX43.EDT`, `CX44.EDT`, `CX45.EDT`, `CX46.EDT`, `CX47.EDT`, `CX48.EDT`, `CX49.EDT`, `CX50.EDT`, `CX51.EDT`, `CX52.EDT`, `CX53.EDT`, `CX54.EDT`, `CX55.EDT`, `CX56.EDT`, `CX57.EDT`, `CX58.EDT`, `CX59.EDT`, `CX60.EDT`, `CX61.EDT`, `CX62.EDT`, `CX63.EDT`, `CX64.EDT`, `CX65.EDT`, `CX66.EDT`, `CX67.EDT`, `CX68.EDT`, `CX69.EDT`, `CX70.EDT`, `CX71.EDT`, `CX72.EDT`, `CX78.EDT`, `CX79.EDT`, `CX80.EDT`, `CX83.EDT`, `CX84.EDT`, `CX85.EDT`, `CX86.EDT`, `CX88.EDT`, `CX90.EDT`, `CX91.EDT`, `CX92.EDT`, `CX93.EDT`, `CX95.EDT`, `M01F.EDT`, `M02F.EDT`, `M03F.EDT`, `M04F.EDT`, `M05F.EDT`, `M06F.EDT`, `M07F.EDT`, `M08F.EDT`, `M09F.EDT`, `MDF.EDT`, `MENU.EDT`, `MSF.EDT`, `MWF.EDT`), the speaker name table and the menu command table (`KOM_F0.EDT`, `NAME_F0.EDT`, `POWER.EDT`); `pc98tl/adl5.py` documents the script format (the scripts are coded: after a 4-byte prefix, each byte inverted) and the program patch (`pc98tl/adl.py` the characters and the tables), `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start to its end (where a table the walker never steps onto sits among the statements, the walk is picked up again at the next entry and the table moves as it is), and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `CL/`); the scripts and the tables are members of the archive `EDT` (a word, the entries' size; entries of a 12-byte name and a dword offset; the members), which the patch lays out anew.

* A script starts with its entries (the targets of its gotos, calls and menus, as offsets), so a rebuilt script has them moved with its statements.
* `ADL21.EXE` gets a helper in 512 bytes put in at the end of its code segment (the data and work segments after it move up, every relocation with them).  In a run of text, 20h (a character the engine skips) switches to half-width letters: ASCII drawn 8 dots wide from the BIOS 8x16 font into the graphics planes, in the text's colour (bold where the engine's text is), with the engine's own character wait and paging (a new line whose row would run past the window's bottom pages first).  Before each English word the helper measures it against the window's right edge and starts a new line when it would not fit (a space at a line's start is not drawn): the windows a script uses change as it calls and jumps, so the wrap is the program's, not the patcher's.
* The speaker's name indents the text by its name table's slot; the engine's new line (06) waits for a key itself before it clears a full window.
* Speaker names, menu commands and the program's own strings take ASCII as well.

## Script

4374 strings: 89 menu commands, 7 program strings, 4257 messages, 21 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 4374 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A menu's choices (the messages right after a menu) should stay within one line: their `max_cells` is the widest the screen allows the menu's window.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* `{X1}`, `{X2}`...: the script's controls between the runs of a message (a key wait, a colour change, a new line, the next statement going on along the same line); the note says what each does.  Keep each once, in any order; a message without them all is refused.
* A script is read whole into a 64 KB segment: with its English it may take 65536 bytes.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build whose script outgrows its segment is refused and names the script and its strings.
* Speaker names (`n` ids): `max_cells` letters (10, the slot the script gives the name's table, 19h); the text after a name starts as many cells in as its table's slot.  Longer ones are cut and reported.
* Menu commands (`c` ids): `max_cells` letters (6 to 8 by table: the slot the script gives the command's table, 18h, within the menu boxes drawn while it is loaded); longer ones would run into the next command's, so they are cut and reported.
* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); a character the program writes in at run time (a drive letter, a digit) is `{X1}`..., kept in the English, which is placed so that it stays where the program writes it.  Longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logos, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The CD version's HD Boot disk with the hard-disk image (patched) and the CD: the start menu (a box and its items, 71h) | OK: the items half-width filler, the highlight bar on the first |
| ADL21: the opening's lines, the first scene (the nurse's room): a speaker's name and her lines | OK: filler half-width, wrapped between words in the window, paged; the speaker's name half-width with the text indented |
| The rest of the story, the battles (BATLE.EDT, POWER.EDT's commands), save/load, endings | not yet seen |

The patch works on the CD version's hard-disk image.  It runs from the CD version's HD Boot disk floppy (which loads the CD-ROM driver) with the CD in the drive; on its own it stops at the DOS prompt, and the game started there shows a black screen.  The floppy release's ADL98.EXE is packed (DIET), which the patch does not take.

ADL21.EXE is ADL98's engine with 67h one byte and AEh eleven, and 66h and 97h named (pc98tl/adl5.py, variant adl21).  POWER.EDT, a command table the scripts load with 18h, is named in game.json "tables".

The start menu is a box (12h) with its items drawn at their own places (71h); the box's black background is drawn into the picture behind it, so each item's `max_cells` is the box's (15 letters).
