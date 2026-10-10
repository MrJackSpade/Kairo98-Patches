# Tenshin Ranma (Elf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshin Ranma/Tenshin Ranma [HD]/Tenshin Ranma.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's **AI5** (`AI5.EXE`): the script is 76 `*.MES` files with text, bytecode with a dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every script tokenizes from its start to its end.

The patch works on the game's hard-disk release (the game in `TEN/`), which has room for a longer script.

* Nothing in a script is an address, so the scripts are rebuilt with the English in place of the Japanese.
* English is written as the engine's half-width strings (06 ... 06), between commands that set the character width to one column and back to two; the program is not changed.
* Lines are wrapped between words to the text window the script set up (its own commands, or a subroutine it calls), and a new page (a key wait and a clear) starts before a line would run past the window's bottom.
* Menu items are drawn by the menu itself, which takes characters only: their English is written in full-width letters.

## Script

6298 strings: 105 menu items, 22 labels, 6066 messages, 105 names in data tables.

Translation and the content classification (♥) are done by the translation model; 0 of 6298 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's buffer (below); `\n` starts a new line.  `max_cells` is a line's room in its window (English letters); longer text wraps between words and pages.
* `{X0}` is a pause in the staff roll (the script's subroutine 0): keep it in the English.
* `{X16}` is a party member's name (Takami) (the script's subroutine 16): keep it in the English.
* `{X17}` is a party member's name (Yuima) (the script's subroutine 17): keep it in the English.
* `{X18}` is a party member's name (Amano) (the script's subroutine 18): keep it in the English.
* A script runs where it is loaded, at DS:0000 before the engine's variables at DS:E000h: a script with its English may take 57344 bytes.  Each English letter is one byte; a message takes up to twenty bytes more for the commands around it (two where messages follow one another), and a full-width character or a name call in it about twenty more.  A build whose script outgrows its buffer is refused and names the script and its strings.
* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is written full-width, so it holds half as many letters.  Longer ones are cut and reported.
* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.
* Names in data tables (`r` ids: `SENTO.COM`): `max_cells` full-width letters, the room of their fixed fields (12 bytes, ended by a NUL); longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release; the title and its menu | OK: boots; the menu's items as full-width filler, cut to their boxes |
| Name entry (a new game) | OK: its prompt and buttons as half-width filler in their slots, the character grid stays Japanese, the default name is taken; the one-cell closing bracket of the name field (m00007) with its 8-letter filler is drawn again at the screen's left edge |
| The opening scene | OK: the speaker's name (subroutines 16-18) before half-width filler, wrapped in the bottom window, pages waiting for a key |
| Party talk in the dungeon (a shipped save loaded) | OK: filler wrapped in each speaker's box beside the portrait (the box the script picks by its variable) |
| A battle (its one-line message box) | Not OK with the 2.5x filler: a message runs past the box and wraps onto the start of its own line, as the names and numbers the battle prints before it are not counted |
| Monster names (SENTO.COM) in battle, shops, the ending and the staff roll | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

The speech boxes are set by the start script's subroutine 1, which picks one of four windows by a variable the scene sets just before calling it (`0A var n`); the patcher follows the start script's subroutines into every scene and takes the window the variable picks (`pc98tl/ai5.py` windows).

The party's names are typed in the name entry (its kana grid stays Japanese) and printed by subroutines 16-18; the patcher keeps 8 cells for each.

Monster and item names in battle come from `SENTO.COM`, a table of 30-byte records, each with a 12-byte name field ended by a NUL: `r` ids, written in full-width letters, up to `max_cells` (5) letters.

Limit: the battle's one-line message box also holds the names and numbers the battle prints before a message, which the patcher does not count, so keep battle messages about as long as the Japanese; a longer one wraps onto the start of its own line.
