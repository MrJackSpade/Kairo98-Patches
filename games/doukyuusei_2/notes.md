# Doukyuusei 2 (Elf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Doukyuusei 2/Doukyuusei 2 (with Special Disk) [HD]/Doukyuusei 2 (with Special Disk).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's **AI5** (`AI5.EXE`): the script is 564 `*.MES` files with text, bytecode with a dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every script tokenizes from its start to its end.

The patch works on the game's hard-disk release (the game in `NANPA2/`), which has room for a longer script.  The scripts are in Elf's archives `ELFSYS.DAT`, `SPECIAL.DAT` (`pc98tl/elfarc.py`): the archive holds name hashes only, so the scripts are found from `start.mes` through the script names the scripts give; a rebuilt script is compressed again and the archive laid out anew.

* Nothing in a script is an address, so the scripts are rebuilt with the English in place of the Japanese.
* English is written as the engine's half-width strings (06 ... 06), between commands that set the character width to one column and back to two; the program is not changed.
* Lines are wrapped between words to the text window the script set up (its own commands, or a subroutine it calls), and a new page (a key wait and a clear) starts before a line would run past the window's bottom.
* Menu items are drawn by the menu itself, which takes characters only: their English is written in full-width letters.

## Script

55034 strings: 1316 menu items, 37 labels, 53681 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 55034 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's buffer (below); `\n` starts a new line.  `max_cells` is a line's room in its window (English letters); longer text wraps between words and pages.
* `{X0}` is the hero's name (the script's subroutine 0): keep it in the English.
* `{X57}` is a key wait and a new page (the script's subroutine 57; the English goes on on a fresh page after it): keep it in the English.
* A script runs where it is loaded, at DS:0000 before the engine's variables at DS:E000h: a script with its English may take 57344 bytes.  Each English letter is one byte; a message takes up to twenty bytes more for the commands around it (two where messages follow one another), and a full-width character or a name call in it about twenty more.  A build whose script outgrows its buffer is refused and names the script and its strings.
* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is written full-width, so it holds half as many letters.  Longer ones are cut and reported.
* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release (both games from its menu); the logo and the start menu | OK: boots; the start menu's items as full-width filler |
| Name entry | The entry's prompt is a picture; its window takes no emulated key or click (the original's neither), so the scenes below were run in a test image with the name entry left out |
| Prologue (the classroom, the teacher) | OK: filler wrapped in the bottom window, the speaker's bracket kept, pages waiting for a key |
| Scripts over the 57344-byte buffer with full filler | the --pseudo build cuts their filler to fit (reported per script); a real build over it is refused |
| The town map, the other girls' scenes, the Special Disk, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

Script room: in these scripts the English (with its commands) has fewer than three bytes for each Japanese character, so their English must be kept short (bytes for English / Japanese characters): `17.mes` 25419 / 17354; `27.mes` 25029 / 16595; `14.mes` 25503 / 15815; `15.mes` 27286 / 16268; `30.mes` 27066 / 15378; `39.mes` 25406 / 14291; `16a.mes` 23921 / 12915; `42.mes` 28230 / 15057; `41.mes` 25307 / 13292; `01.mes` 28598 / 14886; `26.mes` 27184 / 13514; `22.mes` 30917 / 15196; `21.mes` 29086 / 13196; `36.mes` 30258 / 13111; `43.mes` 31126 / 13468; `25.mes` 39443 / 16099; `SPECIAL.DAT/hint.mes` 49002 / 19738; `38.mes` 28762 / 11545; `31.mes` 31897 / 11756; `02.mes` 30631 / 11224; `40.mes` 33932 / 12069; `37.mes` 32798 / 11087; `39_sub.mes` 35471 / 11940; `62b.mes` 35715 / 11951.
