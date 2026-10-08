# Virtuacall (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Virtuacall/Virtuacall [HD]/Virtuacall.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-03 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`Q2/`), on a hard-disk image: 195 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it; this build has the later engines' extended opcodes).  Every script tokenizes and rebuilds byte for byte.  The procedure table holds 20 slots of 76 bytes (read off the engine's memory).

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
* Procedures are read for what they print: a name tag ends its line, a fixed text (an ellipsis) or a name shown from a variable (up to 8 columns, the name entry's limit) moves along it, a line break moves down, and a frame or text reset starts a fresh page.  A message continues the page of the text before it, wrapped from where that left off, with room left for what is printed after it.
* Procedures (`B9 n`) are copied into fixed slots of a table (one per number, run on into free slots after it); a build that would overrun one is refused.
* String variables' values (`@n='...'` arguments) and the strings in the engine's programs are rewritten in place.

## Script

25366 strings (25307 messages, 42 menu items, 2 string variable values, 15 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 25366 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Strings in `*.MEC` files: the engine loads these into one shared buffer, each at its own offset, so a `.MEC` file can only grow up to the next file's offset (or, for the top one, as far as the original game's loads reach; past that the buffer meets the engine's stack), often only a few dozen bytes past its Japanese.  The patcher refuses a build where one outgrows its room and lists that file's strings.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters).  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title, opening question and its menu | OK: question filler in the box; items fixed width |
| Name entry window | OK: the window's labels as filler at their places (the kana table stays Japanese). Its buttons take no emulated click or key in the original or the patched build (hover works), so for the rest of the test a test image skipped the two name-entry calls, keeping the default name |
| Phone screen and first town scene (test image) | OK: speaker name and message on one line, filler wrapped between words to the 3-line box, pages waiting for a click |
| Choosing a name in the window, save/load, later scenes, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
