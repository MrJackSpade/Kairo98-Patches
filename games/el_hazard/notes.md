# El-Hazard - The Magnificent World (Elf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `El-Hazard - The Magnificent World/El-Hazard - The Magnificent World [HD]/El-Hazard - The Magnificent World.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's **AI5** (`AI5.EXE`): the script is 73 `*.MES` files with text, bytecode with a dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every script tokenizes from its start to its end.

The patch works on the game's hard-disk release (the game in `PLDC/ELHAZARD/`), which has room for a longer script.

* Nothing in a script is an address, so the scripts are rebuilt with the English in place of the Japanese.
* English is written as the engine's half-width strings (06 ... 06), between commands that set the character width to one column and back to two; the program is not changed.
* Lines are wrapped between words to the text window the script set up (its own commands, or a subroutine it calls), and a new page (a key wait and a clear) starts before a line would run past the window's bottom.
* Menu items are drawn by the menu itself, which takes characters only: their English is written in full-width letters.

## Script

8390 strings: 167 menu items, 1 labels, 8222 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 8390 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's buffer (below); `\n` starts a new line.  `max_cells` is a line's room in its window (English letters); longer text wraps between words and pages.
* `{X0}` is a pause in the staff roll (the script's subroutine 0): keep it in the English.
* `{X3}` is a key wait and a new page (the script's subroutine 3; the English goes on on a fresh page after it): keep it in the English.
* A script runs where it is loaded, at DS:0000 before the engine's variables at DS:A000h: a script with its English may take 40960 bytes.  Each English letter is one byte; a message takes up to twenty bytes more for the commands around it (two where messages follow one another), and a full-width character or a name call in it about twenty more.  A build whose script outgrows its buffer is refused and names the script and its strings.
* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is written full-width, so it holds half as many letters.  Longer ones are cut and reported.
* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release with its CD in the drive (game.json cd); the animated opening | OK: boots and plays the opening (it needs the CD; without it the screen stays black, as the original's does) |
| The first scenes (the school at night, Makoto, Nanami) | OK: filler wrapped in the bottom window, the speaker's bracket kept, pages waiting for a key |
| Script buffer | A script runs at DS:0000 before the engine's variables at DS:A000h (40960 bytes; read off the running engine) |
| Menus, the later chapters, the staff roll | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
