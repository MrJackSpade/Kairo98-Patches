# Watashi o Golf ni Tsuretette (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Watashi o Golf ni Tsuretette/Watashi o Golf ni Tsuretette [FD hd9]/Watashi o Golf ni Tsuretette (Disk A).d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (at the disk's root), on 3 floppies: 172 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  The procedure table was not measured, so a procedure may not grow: text in a procedure (`n` ids) keeps its Japanese byte length.

This is ADVH, the engine before Adv98V (`ADVH.EXE`, run by `ADVSHELL.COM`): the same bytecode, but no ASCII string command, and every character drawn as a 16x16 glyph.  The patch adds half-width letters to the program (`pc98tl/advh.py`): each English letter is written as `85 xx` (xx its ASCII code), which the program draws from the BIOS's 8x16 font one column wide and steps the cursor one column on; the program is unpacked, patched and packed again with its own EXEPACK unpacker.  Its disk-change command (wait for disk X in the floppy drive) goes straight on.  Messages page with the key wait `81 90`, which clears the box: a message longer than the box goes on after a key on a fresh page.

The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image (every disk's files in `/`, with the scripts' drive letters taken off their file names, started as the floppy's boot does); the base image is the collection's `Naomi - Bishoujo-tachi no Yakata/Naomi - Bishoujo-tachi no Yakata [HD]/Naomi - Bishoujo-tachi no Yakata.hdi` with its own game removed.  Watashi o Golf ni Tsuretette (Disk A).d88's copy of `MES/OPEN0.MES` is left out: another disk holds it differently, and the scripts load only that one.

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
* A message after a speaker's name tag (a procedure that ends its line) starts on the frame's second line.
* Procedures are read for what they print: a name tag ends its line, a fixed text (an ellipsis) or a name shown from a variable (its Japanese width) moves along it, a line break moves down, and a frame or text reset starts a fresh page.  A message continues the page of the text before it, wrapped from where that left off, with room left for what is printed after it.
* String variables' values (`@n='...'` arguments) and the strings in the engine's programs are rewritten in place.

## Script

8106 strings (7701 messages, 351 menu items, 4 name tags (procedure text), 8 string variable values, 42 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 8106 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* This old build ends each message with a key wait (`81 90`) that clears the box, so pages are split with it; in its one-line box a message pages a line at a time.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own, so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters).  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).
* Program strings (`e` ids: `GNAME.COM`): the module's text is Shift-JIS only, so they are written in full-width letters, up to `max_cells` letters each, in place; longer ones are cut and reported.
* The hero's default name (an `e` id from `GOLF/SPEAK.DAT`, `NAME.DEF`): up to `max_cells` full-width letters (the engine reads the name as message text); that is as long a name as the name entry takes from the player, or the Japanese name's length where the game has no name entry.  Longer names are cut and reported.  The file pairs the name with the placeholder `＊＊＊`, which the engine swaps for the name as it reads a message (the name entry writes the name the player types under the same placeholder): keep `＊＊＊` in the English of a message where the name goes.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Start menu | OK: filler items, the highlight on the first |
| Name entry (GNAME.COM: the hero's name, then the golf name in letters) | OK: its prompts as full-width filler at their places; names typed with the keyboard are taken and shown in its confirmation line |
| The club lobby (messages and the command menus) | OK: filler wrapped in the bottom box, pages waiting for a key; one-line menus picked with the arrow keys, the choices leading on to new messages |
| The golf round (GOLF/HIT.EXE, started from the practice script RENSYU.MES in a test image) | OK: the round starts on the first hole; shots are hit and scored |
| The caddie's lines (GOLF/SPEAK.DAT), the girls' scenes, Disk B and C scenes, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
