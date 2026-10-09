# Cocktail Soft Zoukangou (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Cocktail Soft Zoukangou/Cocktail Soft Zoukangou [FD]/Cocktail Soft Zoukangou (Disk A).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (at the disk's root), on 2 floppies: 62 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  No procedure holds text, so no procedure grows.

This is ADVH, the engine before Adv98V (`ADVH.EXE`, run by `ADVSHELL.COM`): the same bytecode, but no ASCII string command, and every character drawn as a 16x16 glyph.  The patch adds half-width letters to the program (`pc98tl/advh.py`): each English letter is written as `85 xx` (xx its ASCII code), which the program draws from the BIOS's 8x16 font one column wide and steps the cursor one column on; the program is unpacked, patched and packed again with its own EXEPACK unpacker.  Its disk-change command (wait for disk X in the floppy drive) goes straight on.  Messages page with the key wait `81 90`, which clears the box: a message longer than the box goes on after a key on a fresh page.

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
* The strings in the engine's programs are rewritten in place.

## Script

2230 strings (1972 messages, 248 menu items, 10 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 2230 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* This old build ends each message with a key wait (`81 90`) that clears the box, so pages are split with it; in its one-line box a message pages a line at a time.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.
* Names in data files (`e` ids from `NAME.DEF`): written in place, each up to its field's room (`max_cells` full-width letters, as the files hold these names in Shift-JIS only: the name with the spaces around it and any `＠` padding after it), a shorter one padded as the field was (`＠`, or the NUL or FF byte ending it); longer ones are cut and reported.
* `ADVSHELL.COM` is patched in place (a byte signature, the same length): ADVSHELL checks drive A's volume label for the game disk's (ｶｸﾃﾙｿﾞｳｶﾝ A); on the hard disk the check is made to report a match.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Start menu (the four sampling-program items) | OK: filler items at their places, the question below in its colour |
| The explanation story (the night city, the girl) | OK: filler wrapped in the bottom box, pages waiting for a key; pictures change with the story, and it returns to the menu |
| Mouse | With the base image's QMOUSE loaded beside the game's MOUSE.SYS the key waits take no key or click; the install leaves QMOUSE out |
| The other programs, the default names (NAME.DEF) | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
