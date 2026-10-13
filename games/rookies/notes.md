# Rookies (Umitsuki Seisakusho)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Rookies/Rookies [HD]/Rookies.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`ANI.EXE`, K. Hoshino's "AVG and ANIME SYSTEM" (Turbo C): the `*.SCP` scripts are LZ96-packed bytecode with the text in them (JIS words).  The patcher writes a changed script again (its jumps and calls moved) and packs it; a script past its 64 KB segment is cut into further files (`NAME2.SCP`), each part going on to the next with the script-loading command, cut only before a message no jump or routine reaches across.  `pc98tl/lz96.py` and `pc98tl/aas.py` document the formats, `pc98tl/aas_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws only full-width characters (the kanji ROM).  The patched program draws English as letter pairs, two kanji-ROM ANK letters in one 16-dot cell (as for pc98tl/illusion_font24.py); a cell is two half-width letters.
* The game is played with the mouse; the right button opens the program's menu.

## Script

11257 strings: 19 DOS notices, 88 choice items, 21 program strings (its menu, the save slots), 11103 messages, 26 characters' names.

Translation and the content classification (♥) are done by the translation model; 0 of 11257 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` 58, letters a line holds): any length.  The window is 29 cells (58 letters) by three lines; the patcher breaks the English between words and ends a shorter line itself, and the program waits for a click when the window is full.  `\n` forces a new line.  `{N}` is the player's name; `{Snn}` at a message's start is a speaker's name, drawn "【name】" on a line of its own; keep them.
* Choice items (`i` ids): one line in the choice's box, `max_cells` letters; past it reported.
* Characters' names (`n` ids, the program's table): in place, 54 letters at most; past it cut and reported.
* Program strings (`l` ids: its menu, the save slots): in place, `max_cells` their room in letters; past it cut and reported.
* DOS notices (`t` ids): printed through DOS, in place as plain ASCII, `max_cells` bytes; past it cut and reported.
* English is ASCII (pairs); another character is written full-width (a cell) when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the title's logo).
* The name-entry screen: its rows of kana are the grid the player picks the name from; a name entered there is kana.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (RK.BAT: ANI), the title, Enter; the title menu, Enter on its first item | OK: the menu's items in filler half-width (letter pairs) in their box; the first starts the game (the name-entry screen) |
| The name-entry screen, its 終了 clicked; the opening (OPENING.SCP), a click after each message | OK: the speaker's name on a line of its own, the messages' filler half-width after it, broken between words at the window's edge |
| The program's menu (a right click) | OK: its labels in filler (pairs), cut to their room |
| A forced cut (OPENING.SCP's first part about 400 bytes, the rest in OPENING2.SCP), the opening clicked through | OK: the last message of the first part, then the first of OPENING2.SCP, the scene, name and window kept |
