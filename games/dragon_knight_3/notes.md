# Dragon Knight III (Elf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Dragon Knight III/Dragon Knight III [HD]/Dragon Knight III.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's **AI5** (`AI5.EXE`): the script is 100 `*.MES` files with text, bytecode with a dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every script tokenizes from its start to its end.

The patch works on the game's hard-disk release (the game in `DR3/`), which has room for a longer script.

* Nothing in a script is an address, so the scripts are rebuilt with the English in place of the Japanese.
* English is written as the engine's half-width strings (06 ... 06), between commands that set the character width to one column and back to two; the program is not changed.
* Lines are wrapped between words to the text window the script set up (its own commands, or a subroutine it calls), and a new page (a key wait and a clear) starts before a line would run past the window's bottom.
* Menu items are drawn by the menu itself, which takes characters only: their English is written in full-width letters.

## Script

5214 strings: 276 menu items, 9 labels, 4929 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 5214 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  `max_cells` is a line's room in its window (English letters); longer text wraps between words and pages.
* `{X26}` is the hero's name (the script's subroutine 26 prints it): keep it in the English.
* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is written full-width, so it holds half as many letters.  Longer ones are cut and reported.
* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release; the opening pictures and the title menu | OK: boots; the title menu's items as full-width filler |
| Name entry | OK: its prompt and buttons as half-width filler in their slots; the character grid stays Japanese; the default name is taken |
| Town dialogue (the two-line box) | OK: filler wrapped between words in the box, the hero's name in brackets, pages waiting for a key |
| Event scene (the bottom text) | OK: filler wrapped across the bottom window, pages waiting for a key |
| Shops, battles, camp menu, later towns, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
