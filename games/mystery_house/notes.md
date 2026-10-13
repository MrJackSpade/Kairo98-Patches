# Mystery House (Starcraft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Mystery House/Mystery House [FD]/Mystery House.d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

A program in N88-BASIC(86), on an N88-DISK BASIC floppy that starts it: `MYS 98`, `M98`.  The programs are saved protected (every byte rotated a bit) and tokenized; the text is their string literals, half-width katakana printed on the text layer.  The patcher writes each program again with the English in its literals and every line's length set anew (jumps name line numbers, so lines may grow).  `pc98tl/n88prog.py` documents the format, `pc98tl/n88prog_tl.py` the English.  A program with no English is left as it is.

* English goes out as ASCII on the same text layer: no drawing change.
* A changed program loses the spaces kept between its tokens (only LIST shows them), which leaves it room: the game's program and its parser words must fit the memory BASIC leaves them, `MYS 98` 52415 bytes (measured: the game started with the program padded to 53,000 bytes and ran out of memory at 54,000; 1,024 kept for what play needs).  A build past it is refused.
* A program's end mark is kept off a sector of its own (the disk does not start a program whose last sector holds only zeros).
* The machine-translation notice is `MTL_NO.TXT` on the disk (N88 names are 6+3).

## Script

281 strings: 35 rows of the title and instruction pages, 139 messages, 107 parser words.

Translation and the content classification (♥) are done by the translation model; 0 of 281 strings have English so far.

## Limits

* Messages (`m` ids): any length.  The patcher breaks the English between words at 79 half-width cells (the text layer's last column is left free) and prints each further line with a PRINT of its own; after each 2 lines it waits for a key (the window under the picture shows 4 rows, with the line before and the cursor's).  A message that goes on after something on its line (a noun the game prints, then `ｦ ﾄﾘﾏｼﾀ｡`) starts its first line that much further on.  `\n` forces a new line.  `max_cells` is one page.
* Rows of the title and instruction pages (`l` ids): one line each, its room (`max_cells`) the rest of its row from the column the game puts it at; longer English is cut and reported.  A row ending in the input box `[ ]` (the game puts its cursor in it) keeps the box at its column: end the English with `[ ]`.
* Parser words (`w` ids): what the player types is matched against them.  The verb and noun lists are searched for in the typed line, the spaces around a word part of the match (a Japanese verb has its space before it, coming after the noun; put the spaces where the English order needs them), and the commands `ﾓﾁﾓﾉ`, `ｾｰﾌﾞ ｹﾞｰﾑ`, `ﾘｽﾄｱ ｹﾞｰﾑ` are compared whole.  Written as given, spaces included; at most 79 cells (reported past it), 255 bytes (refused).
* English is ASCII; a double quote becomes `'`, another character `?`.

## Not handled

* The title logo (drawn from coordinates in `M98`'s DATA lines).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the floppy (N88-DISK BASIC starts M98): the title, its menu row with the input box | OK: the menu row's filler in half-width with the box [ ] kept at its column, the cursor in it |
| 2 (instructions), Enter through the pages | OK: each page's rows in filler half-width at the game's columns, one a row inside the screen; the press-a-key row with its box |
| 1 (start): the opening scene, then two typed commands | OK: the house drawn, the opening messages' filler broken between words at 79 cells under it, the prompt after; each command answered with the not-understood message's filler. A test build with an over-long message showed it a page of 2 lines at a time, waiting for a key |

Not reached in this test: commands in English words (the stress build's words are filler), the rooms past the front of the house, save and restore, the ending.
