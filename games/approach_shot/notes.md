# 101 Kaime no Approach Shot (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `101 Kaime no Approach Shot/101 Kaime no Approach Shot [FD]/101 Kaime no Approach Shot (Disk A).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (at the disk's root), on 2 floppies: 52 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  The procedure table was not measured, so a procedure may not grow: text in a procedure (`n` ids) keeps its Japanese byte length.

The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image (every disk's files in `/`, with the scripts' drive letters taken off their file names, started as the floppy's boot does); the base image is the collection's `Naomi - Bishoujo-tachi no Yakata/Naomi - Bishoujo-tachi no Yakata [HD]/Naomi - Bishoujo-tachi no Yakata.hdi` with its own game removed.

## English display (`pc98tl/adv98v_tl.py`)

* The engine draws ASCII strings (`21 ... 00`) half-width itself, so English
  is written as ASCII strings in place of the Japanese text runs; the
  scripts are rebuilt with them (no offset table refers into a script).
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
* The strings in the engine's programs are rewritten in place.

## Script

1927 strings (18 name tags (procedure text), 1801 messages, 67 menu items, 41 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 1927 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* A script runs from the engine's script buffer, which holds 16584 bytes (read off its memory): a file that would outgrow it with the English is refused and named, so keep the longest scripts' English about as long as the Japanese.
* This engine draws menus from Shift-JIS only (an ASCII string in a menu crashes it), so menu items are written in full-width letters: `max_cells` letters each, cut and padded.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own, so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* Program strings (`e` ids: `BIN/HIT.EXE`, `BIN/GNAME.COM`): the module's text is Shift-JIS only, so they are written in full-width letters, up to `max_cells` letters each, in place; longer ones are cut and reported.
* Names in data files (`e` ids from `GOLF/SPEAK.DAT`, `NAME.DEF`): written in place, each up to its field's room (`max_cells` full-width letters, as the files hold these names in Shift-JIS only: the name with the spaces around it and any `＠` padding after it), a shorter one padded as the field was (`＠`, or the NUL or FF byte ending it); longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The club receptionist's greeting | OK: filler in the box beside the picture, pages waiting for a key |
| Name entry (BIN/GNAME.COM: the hero's name, then the golf name in letters) | OK: its prompts as full-width filler at their places (the prompt after the kana grid included); names typed with the keyboard are taken |
| The club's questions and menus (explanation, mode, course, out/in, hole) | OK: question filler above full-width filler items, picked with the keyboard |
| The golf round (BIN/HIT.EXE) | OK: the round starts on the first hole |
| Shots, the caddie's lines, the girls' scenes, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
