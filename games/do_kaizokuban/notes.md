# D.O. Kaizokuban (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `D.O. Kaizokuban/D.O. Kaizokuban [HD]/D.O. Kaizokuban (Disk A-B) (DOR).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ADL** engine (`ADL'.EXE`): 10 scripts with text (`D1_1.EDT`, `D1_2.EDT`, `D1_3.EDT`, `D2_1.EDT`, `D2_2.EDT`, `D2_3.EDT`, `D3_1.EDT`, `D3_2.EDT`, `D3_3.EDT`, `MENU.EDT`), the speaker name tables and the menu command tables (`KOM_F0.EDT`, `NAME_F0.EDT`); `pc98tl/adl.py` documents the formats and the program patch, and `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start (1000h) to its end (where bytes the walker never steps onto sit among the statements, the walk is picked up again at the next entry and the bytes move as they are), and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `DOR123/`).

* A script starts with its entries (the targets of its gotos and menus, as offsets), so a rebuilt script has them moved with its statements.
* `ADL'.EXE` gets a helper in 768 bytes put in at the end of its code segment (the data and work segments after it move up, every relocation with them).  In a run of text, 20h (a character the engine skips) switches to half-width letters: ASCII drawn one text cell each, with the engine's own character wait, wrapped at the window's right edge and paged (the blinking key-wait mark, then the window cleared) at its bottom.
* Lines are wrapped between words by the patcher to the text window the script set (71h), the speaker's name indenting the text 10 cells; a full window that the script's new line (06) would clear waits for a key first when text was drawn since the last wait.
* Speaker names, menu commands and the save slots' names take ASCII as well (one cell or one 8-dot column each, the menus' from the BIOS 8x16 font).
* A menu's text window (sized by the script to the longest Japanese choice) is widened, with its frame, to the longest English choice, so that each choice stays one line.

## Script

1810 strings: 11 menu commands, 3 save slot names, 1760 messages, 36 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 1810 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A menu's choices (the messages right after a menu) should stay within one line: their `max_cells` is the widest the screen allows the menu's window.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* `{X1}`, `{X2}`...: the script's controls between the runs of a message (a key wait, a colour change, a new line, the next statement going on along the same line); the note says what each does.  Keep each once, in any order; a message without them all is refused.
* A script is read whole into a 64 KB segment: with its English it may take 65536 bytes.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build whose script outgrows its segment is refused and names the script and its strings.
* Speaker names (`n` ids): 8 letters (the table's 9-byte slot), drawn before the colon; the text after them starts 10 cells in.  Longer ones are cut and reported.
* Menu commands (`c` ids): `max_cells` (6) letters fit the menus' boxes; up to 16 are taken (the table's slot), longer ones are cut and reported.
* Save slot names (`e` ids, in `ADL.EXE`): 16 letters (their 17-byte slots).

## Not handled

* Text drawn into the artwork (the title logos, pictures).
* `ADL.EXE`'s disk prompts (insert the system or scenario disk): shown only when the game runs from floppies, never on the hard-disk release the patch builds.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk image of Disks A-B (DOR, ADL'.EXE): the opening, the menu, the first scenario (the planetarium) | OK: boots; speaker names with the text indented; filler half-width, wrapped between words and paged; the menu's command box half-width filler |
| The other scenarios, save/load, endings | not yet seen |

D.O. Kaizokuban is two games on two images: this folder is Disks A-B (DOR's three scenarios, ADL'.EXE, on the ADL driver); games/do_kaizokuban_hoshi is Disk C (Hoshi no Suna Monogatari, ADL2.EXE).
