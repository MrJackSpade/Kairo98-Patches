# Gaogao! 3rd - Wild Force (four nine System-98)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Gaogao! 3rd - Wild Force/Gaogao! 3rd - Wild Force [HD]/Gaogao! 3rd - Wild Force.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

four nine's System-98 (`SYS98FM.EXE`, packed with EXEPACK): the scripts (`*.lsp` (those that begin with 100h zero bytes; the others are pictures), the bytes after 100h XORed with 1) are members of the `DISK_?.LIB` archives, listed in the `DISK_?.CAT` catalogs, both LZSS-compressed; a script on its own next to the archives is the one the program reads.  A script is 16-bit ops with their messages and data between them; the patcher walks the code from its start and every jump (the ops' lengths and pointers read off the program's own routines) and finds every pointer to a message, a name, a file or data.  `pc98tl/sys98.py` documents the formats, `pc98tl/sys98_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program is written unpacked and patched: an ASCII byte, which it drew as a blank, is drawn from the kanji ROM's half-width row, one cell, so English takes a byte a letter.  The hook's code sits where the program's three exits were; they share one tail now, each still printing its line and exiting with its code.
* A changed script's old messages are cut out and the English goes at its end, every pointer moved; the archives with a changed script are written anew, compressed as the originals are.
* Messages (in the wide windows) are broken between words at the window's width and get a key wait and a cleared window past its lines; menus keep their lines.

## Script

8000 strings: 3 program console lines, 406 menu items and titles, 7519 messages, 72 speakers' names.

Translation and the content classification (♥) are done by the translation model; 0 of 8000 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the window's width): any length.  `\n` in the English forces a new line.  A script with its English may take 49 KB (C400h bytes) (the program reads that much); a longer build is refused and names the script and its strings.
* Menus (`i` ids): one item a line, at most `max_cells` (the window's width), no more lines than the Japanese; past it reported.
* Speakers' names (`n` ids): the program keeps 79 bytes; past them cut and reported.
* Program console lines (`c` ids): in place, `max_cells` the Japanese's bytes; past them cut and reported.
* `{C1}`-style tokens are the controls inside a text (colours, names and numbers inserted, key waits, new pages) and must be kept; `{XEBC3}`-style tokens are the game's own characters (the faces and marks it defines).
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the title, the title menu's items).
* Messages no op points at (left over in the scripts) are not extracted; they stay as they are.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (GAO3.BAT: SYS98FM.EXE config.lsp, then WF_OPEN.LSP): the sound menu, the title menu | OK: the items in filler half-width (the patched program drawing ASCII from the ROM's half-width row), one a line in their windows |
| New game, Enter on: the opening (OVERTURE), its speech bubble, the message window, the command menu | OK: the bubble's filler beside the face inside its frame; the messages broken between words at the 66-cell window; the menu's items one a line |

Not reached in this test: the battles past the opening, the save and load screens, the endings.
