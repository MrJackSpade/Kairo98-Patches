# De-Ja II (Elf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `De-Ja II/De-Ja II [HD]/De-Ja II.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's **AI5** (`AI5.EXE`): the script is 132 `*.MES` files with text, bytecode with a dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every script tokenizes from its start to its end.

The patch works on the game's hard-disk release (the game in `DEJA2/`), which has room for a longer script.

* Nothing in a script is an address, so the scripts are rebuilt with the English in place of the Japanese.
* English is written as the engine's half-width strings (06 ... 06), between commands that set the character width to one column and back to two; the program is not changed.
* Lines are wrapped between words to the text window the script set up (its own commands, or a subroutine it calls), and a new page (a key wait and a clear) starts before a line would run past the window's bottom.
* Menu items are drawn by the menu itself, which takes characters only: their English is written in full-width letters.

## Script

32096 strings: 718 menu items, 5 labels, 31373 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 32096 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's buffer (below); `\n` starts a new line.  `max_cells` is a line's room in its window (English letters); longer text wraps between words and pages.
* `{X7}` is the hero's family name (the name entry's, はつしば by default) (the script's subroutine 7): keep it in the English.
* `{X8}` is the hero's given name (the name entry's, りゅうすけ by default) (the script's subroutine 8): keep it in the English.
* `{X9}` is an ellipsis (three ・, printed in Japanese) (the script's subroutine 9): keep it in the English.
* `{X18}` is an island's name (083.MES's subroutine, its own text a string of its own) (the script's subroutine 18): keep it in the English.
* `{X21}` is a place's name (083.MES's subroutine, its own text a string of its own) (the script's subroutine 21): keep it in the English.
* `{X22}` is a guide's name (083.MES's subroutine, its own text a string of its own) (the script's subroutine 22): keep it in the English.
* A script runs where it is loaded, at DS:0000 before the engine's variables at DS:E000h: a script with its English may take 57344 bytes.  Each English letter is one byte; a message takes up to twenty bytes more for the commands around it (two where messages follow one another), and a full-width character or a name call in it about twenty more.  A build whose script outgrows its buffer is refused and names the script and its strings.
* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is written full-width, so it holds half as many letters.  Longer ones are cut and reported.
* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release; its first menu (the monitor type) | OK: boots; the prompt as half-width filler, the items as full-width filler cut to their boxes |
| Picking a menu item | blocked: in np21w no key (Return, Space, Z, X, the keypad), mouse button or mouse move picks an item, in the original game as in the patched one; the arrow keys move the highlight |
| Scenes, the name entry, the ending | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

Subroutines 7 and 8 print the hero's family and given name from the name entry (its kana grid stays Japanese; the defaults はつしば and りゅうすけ are poked by OPEN.MES); the patcher keeps 12 cells for each.  Subroutine 9 prints an ellipsis (three ・) in Japanese; 6 cells.  Subroutines 18, 21 and 22 (083.MES) print an island's, a place's and a guide's name, their text strings of their own; 16 cells each.

The speaker tags (【...】) are subroutine bodies the script defines in a table (12 n, the text), which the driver treats as menu items: full-width letters within the Japanese tag's width.

The boot test stops at the first menu: np21w passes no key or mouse input that picks an item, in the original game too (AUTOEXEC.BAT loads Elf's ELF.COM, and START.MES the mouse cursor MOUSE.DAT).
