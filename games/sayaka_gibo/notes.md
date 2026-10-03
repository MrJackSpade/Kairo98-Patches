# Sayaka - Gibo (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Sayaka - Gibo/Sayaka - Gibo [HD]/Sayaka - Gibo.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-02 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`GIBO/`), on a hard-disk image: 62 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it; this build has the later engines' extended opcodes).  Every script tokenizes and rebuilds byte for byte.  The procedure table holds 20 slots of 76 bytes (read off the engine's memory).

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
* Procedures are read for what they print: a name tag ends its line, a fixed text (an ellipsis) or a name shown from a variable (up to 8 columns, the name entry's limit) moves along it, a line break moves down, and a frame or text reset starts a fresh page.  A message continues the page of the text before it, wrapped from where that left off, with room left for what is printed after it.
* Procedures (`B9 n`) are copied into fixed slots of a table (one per number, run on into free slots after it); a build that would overrun one is refused.
* String variables' values (`@n='...'` arguments) and the strings in the engine's programs are rewritten in place.

## Script

7435 strings (7025 messages, 388 menu items, 6 name tags (procedure text), 1 string variable values, 15 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 7435 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Strings in `*.MEC` files: the engine loads these into one shared buffer, each at its own offset, so a `.MEC` file can only grow up to the next file's offset (or, for the top one, as far as the original game's loads reach; past that the buffer meets the engine's stack), often only a few dozen bytes past its Japanese.  The patcher refuses a build where one outgrows its room and lists that file's strings.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own (76 bytes a slot), so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters).  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Sound board and term questions with their menus | OK: questions kept to their Japanese line width and count, paged first (the window close waits for a key), last page left with the menu on the frame's next line; menu items fixed width |
| Caution message placed in the box (A7) | OK: filler wrapped from where it is placed |
| Term entry window | OK: labels as filler at their places; Finish picked with the arrow keys; the default value's field shows filler under the stored term |
| Opening scene | OK: filler wrapped between words to the 2-line box, pages with a wait between |
| Save/load, later acts, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
