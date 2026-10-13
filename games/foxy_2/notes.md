# Foxy 2 (Elf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Foxy 2/Foxy 2 [HD]/Foxy 2.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's **AI4** (`AI4.EXE`): the script is 38 `*.MES` files with text, bytecode with a dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every script tokenizes from its start to its end.

The patch works on the game's hard-disk release (the game in `FOXY2/`), which has room for a longer script.

* Nothing in a script is an address, so the scripts are rebuilt with the English in place of the Japanese.
* This engine draws no half-width strings, so English is written in the PC-98's half-width two-byte letters (85 40-9E, the space 86 40), between commands that set the character width to one column and back to two; each rebuilt script's dictionary is laid out again so its most frequent letters take one byte; the program is not changed.
* Lines are wrapped between words to the text window the script set up (its own commands, or a subroutine it calls), and a new page (a key wait and a clear) starts before a line would run past the window's bottom.  A script that never waits for a key (the opening, timed to its music) gets no new page: its English is cut to its window's lines (reported).
* Menu items are drawn by the menu itself, which takes characters only: their English is written in full-width letters.

## Script

1133 strings: 92 menu items, 4 labels, 1037 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 1133 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's buffer (below); `\n` starts a new line.  `max_cells` is a line's room in its window (English letters); longer text wraps between words and pages.
* `{X26}` is the hero's name (the script's subroutine 26): keep it in the English.
* A script runs where it is loaded, at DS:0000 before the engine's variables at DS:E000h: a script with its English may take 57344 bytes.  Each English letter is one byte; a message takes up to twenty bytes more for the commands around it (two where messages follow one another), and a full-width character or a name call in it about twenty more.  A build whose script outgrows its buffer is refused and names the script and its strings.
* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is written full-width, so it holds half as many letters.  Longer ones are cut and reported.
* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.
* F2.COM's two DOS messages, shown only when it is loaded a second time or removed while not loaded (the game's batch file does neither).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (F2.COM, then AI4.EXE) | OK: the first menu with its filler items |
| Opening (OPEN.MES, timed to its music) | OK: its pages of filler half-width, wrapped between words, no key waits, through to the FOXY 2 logo |
| The first scenes (classmates, the laboratory) | OK: the filler in the window under the pictures, wrapped, the scenes going on with a key |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
