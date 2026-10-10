# Metal Eye 2 (Elf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Metal Eye 2/Metal Eye 2 [HD]/Metal Eye 2.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's **AI5** (`AI5.EXE`): the script is 48 `*.MES` files with text, bytecode with a dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every script tokenizes from its start to its end.

The patch works on the game's hard-disk release (the game in `METAL2/`), which has room for a longer script.

* Nothing in a script is an address, so the scripts are rebuilt with the English in place of the Japanese.
* English is written as the engine's half-width strings (06 ... 06), between commands that set the character width to one column and back to two; the program is not changed.
* Lines are wrapped between words to the text window the script set up (its own commands, or a subroutine it calls), and a new page (a key wait and a clear) starts before a line would run past the window's bottom.
* Menu items are drawn by the menu itself, which takes characters only: their English is written in full-width letters.

## Script

3899 strings: 246 menu items, 37 labels, 3616 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 3899 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's buffer (below); `\n` starts a new line.  `max_cells` is a line's room in its window (English letters); longer text wraps between words and pages.
* `{X26}` is the hero's name (the script's subroutine 26): keep it in the English.
* A script runs where it is loaded, at DS:0000 before the engine's variables at DS:E000h: a script with its English may take 57344 bytes.  Each English letter is one byte; a message takes up to twenty bytes more for the commands around it (two where messages follow one another), and a full-width character or a name call in it about twenty more.  A build whose script outgrows its buffer is refused and names the script and its strings.
* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is written full-width, so it holds half as many letters.  Longer ones are cut and reported.
* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release; the logos, the opening and the title | OK: boots; the opening's lines as half-width filler |
| The start menu (load data 1-9, start from the beginning) | OK: items as full-width filler, picked with the arrow keys |
| The prologue (the floating city) | OK: filler wrapped across the bottom text window, pages waiting for a key |
| Status screens, battles, the Special Disk (separate floppies, not in the hard-disk release), endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
