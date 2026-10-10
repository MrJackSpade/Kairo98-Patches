# Hoshi no Suna Monogatari 2 (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Hoshi no Suna Monogatari 2/Hoshi no Suna Monogatari 2 [HD]/Hoshi no Suna Monogatari 2.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ADL2** engine (`ADL2.EXE`): 21 scripts with text (`DAY1.EDT`, `DAY2.EDT`, `DAY3.EDT`, `DAY4.EDT`, `DAY5.EDT`, `EPIR1.EDT`, `EPIR2.EDT`, `EPIR3.EDT`, `EPIR4.EDT`, `GOVER1.EDT`, `GOVER2.EDT`, `GOVER3.EDT`, `HINTO1.EDT`, `HINTO2.EDT`, `HINTO3.EDT`, `HINTO4.EDT`, `HINTO5.EDT`, `HINTOZ.EDT`, `OMAKE.EDT`, `PRORO.EDT`, `Z.EDT`), the speaker name tables and the menu command tables (`KOM_F0.EDT`, `NAME_F0.EDT`); `pc98tl/adl.py` documents the formats and the program patch, and `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start (1000h) to its end (where bytes the walker never steps onto sit among the statements, the walk is picked up again at the next entry and the bytes move as they are), and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `HOSI/`).

* A script starts with its entries (the targets of its gotos and menus, as offsets), so a rebuilt script has them moved with its statements.
* `ADL2.EXE` gets a helper in 768 bytes put in at the end of its code segment (the data and work segments after it move up, every relocation with them).  In a run of text, 20h (a character the engine skips) switches to half-width letters: ASCII drawn one text cell each, with the engine's own character wait, wrapped at the window's right edge and paged (the blinking key-wait mark, then the window cleared) at its bottom.
* Lines are wrapped between words by the patcher to the text window the script set (71h), the speaker's name indenting the text 10 cells; the engine's new line (06) waits for a key itself before it clears a full window.
* Speaker names, menu commands and the save slots' names take ASCII as well (one cell or one 8-dot column each, the menus' from the BIOS 8x16 font).
* A menu's text window (sized by the script to the longest Japanese choice) is widened, with its frame, to the longest English choice, so that each choice stays one line.

## Script

4013 strings: 112 menu commands, 3 save slot names, 3873 messages, 25 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 4013 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A menu's choices (the messages right after a menu) should stay within one line: their `max_cells` is the widest the screen allows the menu's window.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* `{X1}`, `{X2}`...: the script's controls between the runs of a message (a key wait, a colour change, a new line, the next statement going on along the same line); the note says what each does.  Keep each once, in any order; a message without them all is refused.
* A script is read whole into a 64 KB segment: with its English it may take 65536 bytes.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build whose script outgrows its segment is refused and names the script and its strings.
* Speaker names (`n` ids): 8 letters (the table's 9-byte slot), drawn before the colon; the text after them starts 10 cells in.  Longer ones are cut and reported.
* Menu commands (`c` ids): `max_cells` (10) letters fit the menus' boxes; up to 16 are taken (the table's slot), longer ones are cut and reported.
* Save slot names (`e` ids, in `ADL.EXE`): 16 letters (their 17-byte slots).

## Not handled

* Text drawn into the artwork (the title logos, pictures).
* `ADL.EXE`'s disk prompts (insert the system or scenario disk): shown only when the game runs from floppies, never on the hard-disk release the patch builds.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release: the opening menu, the title and the prologue (PRORO.EDT) | OK: boots (ADL2.EXE with the helper); the menu's command box half-width filler; the prologue's filler half-width, wrapped between words and paged in its window |
| The days (DAY1-5), save/load, endings | not yet seen |

The collection's "uncensored" image has the same scripts and tables (only ADL2.EXE and DA differ); its ADL2.EXE takes the same patch, so it can be dropped onto PATCH.BAT (the patcher warns that it is not the image the strings were read from).

Most scripts here hold a 13h after a run of text, then a statement the entries reach: the walker never steps past 13h, so the tokenizer picks the walk up again at the entry (one byte kept as it is each time).

The --pseudo build cuts its filler to fit the 64 KB script segment: DAY4.EDT by 48,829 letters; DAY4's English must stay about as long in bytes as the Japanese (the patcher refuses and names the strings otherwise).
