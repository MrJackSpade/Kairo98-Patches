# Mugen Yasoukyoku (four nine System-98)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Mugen Yasoukyoku/Mugen Yasoukyoku [HD]/Mugen Yasoukyoku.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

four nine's System-98 (`SYS98.EXE`, packed with LZEXE): the scripts (`*.s`, the bytes after 100h XORed with 1) are members of the `DISK_?.LIB` archives, listed in the `DISK_?.CAT` catalogs, both LZSS-compressed; a script on its own next to the archives is the one the program reads.  A script is 16-bit ops with their messages and data between them; the patcher walks the code from its start and every jump (the ops' lengths and pointers read off the program's own routines) and finds every pointer to a message, a name, a file or data.  The shared routines' script (`Mug_Sub.s`, loaded 4000h above the others, which call it) keeps its layout.  `pc98tl/sys98.py` documents the formats, `pc98tl/sys98_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program is written unpacked and patched: an ASCII byte, which it drew as a blank, is drawn from the kanji ROM's half-width row, one cell, so English takes a byte a letter.  The hook's code sits where the program's three exits were; they share one tail now, each still printing its line and exiting with its code.
* A changed script's old messages are cut out and the English goes at its end, every pointer moved; the archives with a changed script are written anew, compressed as the originals are.
* Messages (in the wide windows) are broken between words at the window's width and get a key wait and a cleared window past its lines; menus keep their lines.

## Script

3783 strings: 5 program console lines, 170 menu items and titles, 3541 messages, 67 speakers' names.

Translation and the content classification (♥) are done by the translation model; 0 of 3783 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the window's width): any length.  `\n` in the English forces a new line.  A script with its English may take 16 KB (the program reads that much); a longer build is refused and names the script and its strings.  The fullest scripts are close to that already, so their English must stay about as long in bytes as the Japanese (two bytes a character, one a letter).
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
| Boot from the hard disk (AUTOEXEC: FONT, SYS98.EXE run.s), the title menu; Enter on the first item | OK: the title menu is the picture's (Japanese); the game starts |
| The opening: the narration, the command menu (Look and the others), what Look shows | OK: the messages in filler half-width (the patched program drawing ASCII from the ROM's half-width row), broken between words at the 66-cell window, a key wait and a cleared window past its four lines; the command menu's five items in filler, one a line, in the 14-cell window |

English releases exist on other platforms (Nocturnal Illusion, Windows and later); none on the PC-98.
