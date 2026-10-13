# Hana no Kioku Dai-2-shou (Foster)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Hana no Kioku Dai-2-shou/Hana no Kioku Dai-2-shou [HD]/Hana no Kioku Dai-2-shou.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Foster's CINEMA engine (`HK2/HK2.COM` loads the archive's driver, FAD.BIN, which serves the members of `HK2/A.FA1` and B.FA1; CINEMA.BIN runs the scripts, MB3N.BIN draws the text).  The archive is a directory of names and sizes at its end; most members are compressed (an LZ of 16-bit flag words), a member written back is stored unpacked, which the driver reads as it is.  A script is run op by op from its start in a 32 KB buffer whose last 2 KB hold ESC.BIN (the escape menu); the ops' lengths are CINEMA.BIN's, and the ones that hold an address in the script (gotos, calls, switches, the ifs, a message's or a menu's end, the menus' items) are rewritten when the text before them grows.  `pc98tl/cinema.py` documents the formats, `pc98tl/cinema_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws bytes below 80h itself as half-width letters (the ROM's ANK font), so the English needs no program patch.  The patcher breaks the lines between words and pages the window: it follows the cursor from message to message (a message after a speaker's name goes on along the name's row), puts the program's new line (\n) at the window's edge, and when the window's 3 rows are full ends the page (\f) and waits for a key (op 3Fh) before the rest.
* AUTOEXEC.BIN (the title and its menus) runs machine code from its own bytes, so it keeps its layout: a text that fits is written in its place, a longer one after the script's end (a message reached by a goto put in its place, an item by its address).

## Script

2901 strings: 2 program messages, 28 menu items, 2850 messages, 21 speakers' names.

Translation and the content classification (♥) are done by the translation model; 0 of 2901 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` 64: the window's width): any length; the patcher breaks the lines between words and pages the window (3 rows).  A message after a speaker's name goes on along the name's row (its note says so); one whose Japanese starts with a full-width space gets a space before the English when it has none.  `\n` in the English forces a new line.  A script with its English must end before ESC.BIN's place (7800h, 30 KB); a build past it is refused and names the script.
* Speakers' names (`n` ids): one line, `max_cells` the Japanese's; a longer name leaves less of its row to the message after it.
* Menu items (`i` ids): one line in the menu's box, `max_cells` the menu's widest Japanese item; past it reported.
* Program messages (`e` ids): TSM.COM's, printed by DOS when memory or a file is missing, in their own bytes, `max_cells` the room; past it cut and reported.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`; a backslash (the commands' mark) as `/`.

## Not handled

* Text drawn into the pictures (the title menu's items, the logo).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (HK2.COM, the archive's driver, CINEMA.BIN), the title menu | OK: the menu's items in filler, half-width; Enter picks the first |
| The first scenario's opening | OK: the speakers' names (in the same message as the text) in filler, cut to their room, the messages' filler after them on their row, broken between words, a new page after a key |
