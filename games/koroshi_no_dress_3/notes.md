# Koroshi no Dress 3 (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Koroshi no Dress 3/Koroshi no Dress 3 [HD]/Koroshi no Dress 3.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-03 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`KD3/`), on a hard-disk image: 287 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  The procedure table was not measured, so a procedure may not grow: text in a procedure (`n` ids) keeps its Japanese byte length.

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
* String variables' values (`@n='...'` arguments) and the strings in the engine's programs are rewritten in place.

## Script

15170 strings (14603 messages, 477 menu items, 2 name tags (procedure text), 1 string variable values, 86 text file lines, 1 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 15170 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* This engine draws menus from Shift-JIS only (an ASCII string in a menu crashes it), so menu items are written in full-width letters: `max_cells` letters each, cut and padded.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Strings in `*.MEC` files: the engine loads these into one shared buffer, each at its own offset, so a `.MEC` file can only grow up to the next file's offset (or, for the top one, as far as the original game's loads reach; past that the buffer meets the engine's stack), often only a few dozen bytes past its Japanese.  The patcher refuses a build where one outgrows its room and lists that file's strings.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own, so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters).  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).
* Text file lines (`t` ids: `CMD/ROLL.DAT`, shown as they are, e.g. the opening roll): the files hold Shift-JIS only (no half-width letters), so they are written in full-width letters, each line up to `max_cells` letters (its Japanese byte length), as the file is loaded into a fixed place in memory; longer ones are cut and reported.
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Startup menu | OK: full-width filler items at their places |
| The name question before its yes/no menu | OK: the question keeps to its Japanese width beside the menu and pages with the game's message end and its clear (the menu file has no message end of its own); the two items under it |
| Opening (the apartment door, the shadow at the door) | OK: filler wrapped between words to the box, pages waiting for a click |
| The detective's office (the first scene) | OK: messages page the same way as the story goes on |
| Ending roll (CMD/ROLL.DAT, shown by G_ED1B.MES) | OK on a test image that runs G_ED1B.MES's roll part right after the start script's setup: the roll's lines scroll up as full-width filler |
| The investigation's command menus, saving and loading, later scenes, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
