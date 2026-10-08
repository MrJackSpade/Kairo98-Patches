# Dennou Tenshi - Digital Ange (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Dennou Tenshi - Digital Ange/Dennou Tenshi - Digital Ange [HD]/Dennou Tenshi - Digital Ange.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-03 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`DENAN/`), on a hard-disk image: 106 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it; this build has the later engines' extended opcodes).  Every script tokenizes and rebuilds byte for byte.  No procedure holds text, so no procedure grows.

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
* Procedures are read for what they print: a name tag ends its line, a fixed text (an ellipsis) or a name shown from a variable (its Japanese width) moves along it, a line break moves down, and a frame or text reset starts a fresh page.  A message continues the page of the text before it, wrapped from where that left off, with room left for what is printed after it.
* String variables' values (`@n='...'` arguments) and the strings in the engine's programs are rewritten in place.

## Script

1891 strings (1754 messages, 58 menu items, 1 string variable values, 77 text file lines, 1 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 1891 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Strings in `*.MEC` files: the engine loads these into one shared buffer, each at its own offset, so a `.MEC` file can only grow up to the next file's offset (or, for the top one, as far as the original game's loads reach; past that the buffer meets the engine's stack), often only a few dozen bytes past its Japanese.  The patcher refuses a build where one outgrows its room and lists that file's strings.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters).  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).
* Text file lines (`t` ids: `DEN_TCM/ENDING_1.TXT`, `DEN_TCM/ENDING_2.TXT`, `DEN_TCM/ENDING_3.TXT`, `DEN_TCM/ENDING_4.TXT`, `DEN_TCM/ENDING_5.TXT`, `DEN_TCM/ENDING_6.TXT`, `DEN_TCM/ENDING_7.TXT`, shown as they are, e.g. the opening roll): each line up to its Japanese byte length (twice `max_cells` in letters), as the file is loaded into a fixed place in memory; longer ones are cut and reported.
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title screen (Ange's greeting, the START and name-entry buttons) | OK: filler in the box, pages waiting for a click; the buttons are drawn in the picture |
| Name entry (the second button) | Reached: its kana grid is drawn in the picture; not driven further |
| Opening after START (the street, the girl on the rooftop, the meeting, the title) | OK: filler wrapped between words to the 2-line box, pages waiting for a click, pictures change with the story |
| Ending rolls (DEN_TCM/ENDING_1-7.TXT) | not yet seen |
| Entering a name, menus in the scenes, saving and loading, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
