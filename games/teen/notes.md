# Teen (Custom)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Teen/Teen [HD]/Teen.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-23 (`research/clearance.json`).

## Engine

Custom's own C++ engine (`TEEN\TEEN.COM` runs INIT.EXE, CUSTOM.EXE and MENU.EXE; MENU.EXE plays the opening, TEEN_S1.EXE and TEEN_S2.EXE the two scenarios), on the hard disk.  The scenes are compiled into the programs; the messages are the lines of `DATA_00.MSG` and `DATA_nn.1MS`/`.2MS` (each byte rotated and XORed), named by their line's number.  `pc98tl/trps.py` documents the formats and the patch, `pc98tl/trps_tl.py` the English.  A build with no English leaves the disk as it is.

* The message files are written again, each line any length.
* The programs (PKLITE) are written back unpacked.  Their message routine passes over a byte that is not a Shift-JIS lead: it is made to call a helper (a segment put in before the last) that draws the byte with the routine's own call, 8 dots wide, a column on.  The one-byte glyph routine counted its rows with a local it had not set; it is made to count 16.
* The window breaks a row at its edge and waits for a key after its 4 rows; the patcher breaks the English between words at 64 letters, filling each row with spaces to the edge.  After a window's wait the helper waits for the keys to be let go (and empties the key buffer), so the key does not also end the message's own wait.
* The programs' strings are written in place.  Those drawn two bytes a character (menus, choices, names) are written in pairs of letters: each pair a code of its own (Shift-JIS EDh-EFh) whose glyph the kanji routine's hook makes from the two letters' BIOS glyphs; a choice's label goes the same into the choices' conditions that name it.  The console's messages (and strings with ASCII in them already) are written as they are.
* `HELP.TXT` (the operation help) is written again, its escape codes kept.
* `MTL_NOTE.TXT` is put in the game's folder (`TEEN`).

## Script

6519 strings: 21 help lines, 6301 messages, 197 program strings.

Translation and the content classification (♥) are done by the translation model; 0 of 6519 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 64 letters, 4 rows a window, more windows after a key; `\n` a new row.  `{Gxxxx}` a character of the game's own (TEEN.GAI) is kept where it is (2 letters wide).
* Program strings (`e` ids): in place, up to `max_cells` letters (longer is cut and reported by string id); keep `%d`, `%s`.. and `\n`.  A string drawn in pairs of letters takes an even number of letters (one more space otherwise); a program's pairs may be at most 564 different ones (a build past it is refused).
* Help lines (`h` ids): one line of the text screen; keep each `{ESC}`.
* English is ASCII; other characters are written as `?` (curly quotes, dashes and `…` are made ASCII).

## Not handled

* Text drawn into the pictures (`.YCG`: the title, the logos).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Pseudo build boots (np21w, TEEN.COM) | OK: the main menu's items in filler, drawn as pairs of letters in their box |
| The opening (pseudo) | OK: messages in filler, half-width, broken between words at 64 letters; the speakers' names in their brackets in pairs of letters |
| A message longer than a window | OK: 4 rows, the window's wait, then the rest in a cleared window after a key |
| A choice (pseudo) | OK: the menu shows its three choices in filler, as the Japanese menu shows three |
| Partly translated build | OK: the main menu's items in English (Gallery, System, Controls, Quit); a long English message over two windows; the rest in Japanese as before |
| Unmodified build | OK: a build with no English is the source image byte for byte |

Past the first choice the boot test did not play; every message line and program string goes through the same patch. HELP.TXT and the installers' messages were not shown in the boot test.

The menus take the mouse (Enter opens and closes a choice menu).
