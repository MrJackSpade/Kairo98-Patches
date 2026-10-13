# if 3 (Active MAIN.EXE)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `if 3/if 3 [HD]/if 3.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Active's `MAIN.EXE` (Borland C): each scenario's scripts are `*.ADV` files in its folder under `IF3`, blocks of ops and texts; the patcher walks every op (their operands read off the program's own routines) and lays a changed script out anew, every pointer (the blocks' chain, the jumps, the choices' targets) moved.  `pc98tl/active_if.py` documents the format, `pc98tl/active_if_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws a text two bytes at a time and counts its window's columns in cells; it is patched to draw a pair of ASCII letters as two half-width letters from the kanji ROM's half-width row, so English takes a byte a letter, two a cell.
* The program breaks a line at its window's edge and waits for a key and clears the window past its lines; the patcher fills each line with spaces to the window's width so the breaks fall between words, following the window the scripts set (op 6Fh) from script to script.
* The program's own strings (menus, prompts) are replaced in place, the scenarios' titles in their `TITLE.DAT`.
* When the English does not fit on the disk, the patcher grows the volume by whole cylinders, up to the clusters its FAT has room for, without moving anything (`DiskImage.grow_volume`); past that the build is refused.

## Script

9966 strings: 492 choice items, 69 program strings, 9402 messages, 3 scenario titles.

Translation and the content classification (♥) are done by the translation model; 0 of 9966 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the line's width in letters, 72 or 76): any length; the patcher breaks the lines between words and the program pages.  `\n` in the English forces a new line.  A message is the texts up to a key wait; the key wait it ends with is the patcher's.  The program reads at most 32768 bytes of a script: a longer build is refused and names the script's strings.
* Choice items (`i` ids): one line in the choice's box, `max_cells` the choice's widest Japanese item; past it reported.
* Scenario titles (`t` ids): `max_cells` the Japanese's; past it reported.
* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and reported.  `%s`-style marks and a menu item's leading `*0` are kept.
* `{p}`-style tokens are the controls inside a message (`{v0A}` a pause and its length, `{w}` a new window, `{e01}`, `{f}` and the others); keep the ones that matter.  `\`, `{` and `}` are written `/`, `(` and `)`.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures.
* The install batch files' lines (run from the floppies only).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk: the title, the scenario menu | OK: the menu's prompt lines and the scenarios' titles in filler half-width (the patched program drawing ASCII pairs from the ROM's half-width row) |
| Enter on the first scenario: scenario 8 (自殺志願)'s opening, its messages and choices | OK: the messages in filler half-width, broken between words at the window's edge (the window the scripts set followed), a key wait between them, the window cleared past its lines; the choices' items in filler |
