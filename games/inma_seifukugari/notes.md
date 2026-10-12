# Inma Seifukugari (Ail ADV.EXE)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Inma Seifukugari/Inma Seifukugari [HD]/Inma Seifukugari.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Ail's `ADV.EXE` (packed with EXEPACK): the scenarios are in `SALL.SNL`, each LZSS-compressed; a scenario is its tables, labels, code and text, the code reading each text by its offset.  The patcher walks the code op by op (the sub-ops' arguments counted off the program's own routines) and lays the text section out anew with the English, every offset moved; the code stays as it is.  `pc98tl/ail.py` documents the formats, `pc98tl/ail_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws a single byte half-width from the kanji ROM by itself, so English takes a byte a letter; it lays a text out two bytes at a time, so each text is padded to an even length.
* The program breaks a message's lines by itself (52 cells in a slot indented under the name, 56 in one from the window's edge, read off the program) and pages the window; the patcher fills each line with spaces to that width so the breaks fall between words.
* The program's own strings (menus, prompts, messages) are replaced in place in the program.

## Script

5259 strings: 124 choice items, 59 program strings, 5005 messages, 22 speakers' names, 1 prompts, 48 scene titles.

Translation and the content classification (♥) are done by the translation model; 0 of 5259 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the line's width, 52 or 56 cells): any length; the patcher breaks the lines between words and the program pages.  `\n` in the English forces a new line.  A scenario with its English may take 18300 bytes unpacked (the program's buffer); a longer build is refused and names the scenario's strings.  The fullest scenarios are within a few hundred bytes of that already, so their English must take no more bytes than the Japanese (two bytes a character, one a letter).
* Speakers' names (`n` ids): `max_cells` the Japanese's.
* Choice items (`i` ids): one line in the choice's box, `max_cells` the choice's widest Japanese item; past it reported.
* Scene titles (`t` ids): shown with a choice and kept with a save, `max_cells` the Japanese's; past it reported.
* Prompts (`p` ids): a line shown on its own, `max_cells` the Japanese's; past it reported.
* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and reported.  `%s`-style marks are kept.
* `>` is the program's colour mark: in the English it is written `)`; a `%` that is no insert is written `pct`.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures.
* The opening's scrolling prologue (drawn in its pictures, ANIM*.ANM).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk, the title menu; Enter on its first item | OK: the title menu's items in filler half-width (the program's own strings, in place); the game starts |
| The opening (its scrolling prologue, clicked past), then the first scenes' messages | OK: the prologue is the pictures' (Japanese, as in the original); the speakers' names and messages in filler half-width, lines broken between words and the window paged (np21w shows this game's screens doubled, the original as well) |
