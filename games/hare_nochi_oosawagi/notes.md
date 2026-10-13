# Hare Nochi Oosawagi! (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Hare Nochi Oosawagi!/Hare Nochi Oosawagi! [FD]/Hare Nochi Oosawagi! (Disk A).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (at the disk's root), on 2 floppies: 91 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  No procedure holds text, so no procedure grows.

This is ADVH, the engine before Adv98V (`ADVH.EXE`, in most games run by `ADVSHELL.COM`): the same bytecode, but no ASCII string command, and every character drawn as a 16x16 glyph.  The patch adds half-width letters to the program (`pc98tl/advh.py`): each English letter is written as `85 xx` (xx its ASCII code), which the program draws from the BIOS's 8x16 font one column wide and steps the cursor one column on; a packed program is unpacked, patched and packed again with its own EXEPACK unpacker.  This build has no disk-change command (each disk's files are read from their own drive), so the drawing routine goes at the end of the animation driver's second file buffer, past the largest animation file the game has (the patch checks the room).  Messages page with the key wait `81 90`, which clears the box: a message longer than the box goes on after a key on a fresh page.

The opening (`HARE.EXE`, run by `ADVSHELL.COM` before the engine) is a program of its own: its character cards and credits are fixed-width text records in the program (the `e` ids at `HARE.EXE:...`), each with a field of two-letter codes (colour, speed, scrolling) at its characters' places.  It draws a single byte as a half-width cell itself; the patch (`pc98tl/advh.py` patch_opening) steps the code field by the character's bytes rather than 2, so a code applies at its text's byte offset as the Japanese laid it out, and passes over a pair a letter at an odd offset reads across two codes.  Each record's text is written in place, cut to its room.

The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image (every disk's files in `/`, with the scripts' drive letters taken off their file names, started as the floppy's boot does); the base image is the collection's `Naomi - Bishoujo-tachi no Yakata/Naomi - Bishoujo-tachi no Yakata [HD]/Naomi - Bishoujo-tachi no Yakata.hdi` with its own game removed.

## English display (`pc98tl/adv98v_tl.py`)

* English letters are written as `85 xx` in place of the Japanese text runs
  (see the engine note above); the scripts are rebuilt with them (no offset
  table refers into a script).
* The engine wraps at the text frame's right edge even inside a word, and
  does not scroll (a fourth line of a 3-line frame draws over the first).
  So messages are broken between words to the frame's width (`A6` gives it
  in half-width columns) and cut into pages of its line count; between
  pages goes a wait and the file's message-end procedure call, as between
  the original messages.
* Menu items and text in one-line frames keep their Japanese width.
* Pieces of text with only colour, speed, pause or fade commands between
  them are one string; the English replaces all of it, without those
  effects.
* Procedures are read for what they print: a name tag ends its line, a fixed text (an ellipsis) or a name shown from a variable (its Japanese width) moves along it, a line break moves down, and a frame or text reset starts a fresh page.  A message continues the page of the text before it, wrapped from where that left off, with room left for what is printed after it.
* String variables' values (`@n='...'` arguments) and the strings in the engine's programs are rewritten in place.

## Script

6954 strings (6431 messages, 389 menu items, 11 string variable values, 123 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 6954 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* This old build ends each message with a key wait (`81 90`) that clears the box, so pages are split with it (in a one-line box, a line at a time).
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters).  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.
* `ADVSHELL.COM` is patched in place (a byte signature, the same length): ADVSHELL checks drive A's volume label for the game disk's (ﾊﾚﾉﾁｵｵｻﾜ.ｷﾞA); on the hard disk the check is made to report a match.
* `HARE.EXE` is patched in place (a byte signature, the same length): the opening (HARE.EXE) loads its pictures and its music from drive B (B:\PRS\..., B:\MUS\HO-END.M); on the hard disk every file is on drive A.
* `ADVSHELL.COM` is patched in place (a byte signature, the same length): ADVSHELL plays the opening music from drive B (B:\MUS\HO-OPN.M); on the hard disk every file is on drive A.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (ADVSHELL: the opening HARE.EXE, then ADVH.EXE): the credits, the title, the character cards | OK: the credits' and every card's records in filler half-width, each field in its colour, the cards going on one after another to the end of the opening |
| Space at the title loop, then Enter: the start menu, the first scenes, the command menus | OK: the messages in filler half-width wrapped at the box's width over its lines; the start and command menus' items in filler half-width in their columns, the cursor bar over the first |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

Not reached in this test: the scenes past the first rooms, save and load, the endings.
