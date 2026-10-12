# Kyouhaku (Ail ADV.EXE)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Kyouhaku/Kyouhaku [HD]/Kyouhaku.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Ail's `ADV.EXE` (packed with EXEPACK): the scenarios are in `SALL.SNL`, each LZSS-compressed; a scenario is its tables, labels, code and text, the code reading each text by its offset.  The patcher walks the code op by op (the sub-ops' arguments counted off the program's own routines) and lays the text section out anew with the English, every offset moved; the code stays as it is.  `pc98tl/ail.py` documents the formats, `pc98tl/ail_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws a single byte half-width from the kanji ROM by itself, so English takes a byte a letter; it lays a text out two bytes at a time, so each text is padded to an even length.
* The program breaks a message's lines by itself (27 pairs in a slot indented under the name, 29 in one from the window's edge) and pages the window; the patcher fills each line with spaces to that width so the breaks fall between words.
* The program's own strings (menus, prompts, messages) are replaced in place in the program.

## Script

7451 strings: 352 choice items, 65 program strings, 6880 messages, 62 speakers' names, 92 scene titles.

Translation and the content classification (♥) are done by the translation model; 0 of 7451 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the line's width, 54 or 58 cells): any length; the patcher breaks the lines between words and the program pages.  `\n` in the English forces a new line.  A scenario with its English may take 18300 bytes unpacked (the program's buffer); a longer build is refused and names the scenario's strings.  The fullest scenarios are within a few bytes of that already, so their English must take no more bytes than the Japanese (two bytes a character, one a letter).
* Speakers' names (`n` ids): `max_cells` the Japanese's.
* Choice items (`i` ids): one line in the choice's box, `max_cells` the choice's widest Japanese item; past it reported.
* Scene titles (`t` ids): shown with a choice and kept with a save, `max_cells` the Japanese's; past it reported.
* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and reported.  `%s`-style marks are kept.
* `>` is the program's colour mark and `%` its insert mark: in the English they are written `)` and `pct`.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk, the title menu; Enter on its first item | OK: the title menu's seven items in filler half-width (the program's own strings, replaced in place); the game starts |
| The opening: speakers' names and their messages, a long message, the command menu | OK: the names and messages in filler half-width (the program drawing single bytes from the ROM's half-width row); a long English message broken between words at 54 cells under the name and paged by the program (four lines a page); with its slot switched to sub-op 01h (a test build) at 58 cells from the window's edge; the command menu's items in filler |
