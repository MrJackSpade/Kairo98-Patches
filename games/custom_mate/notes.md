# Custom Mate (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Custom Mate/Custom Mate [HD]/Custom Mate.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`CMSTART/`), on a hard-disk image: 181 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it; this build has the later engines' extended opcodes).  Every script tokenizes and rebuilds byte for byte.  The procedure table was not measured, so a procedure may not grow: text in a procedure (`n` ids) keeps its Japanese byte length.

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

6437 strings (5527 messages, 891 menu items, 16 name tags (procedure text), 1 string variable values, 2 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 6437 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own, so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters).  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.
* Names in data files (`e` ids from `NAME.DEF`): written in place, each up to its field's room (`max_cells` full-width letters, as the files hold these names in Shift-JIS only: the name with the spaces around it and any `＠` padding after it), a shorter one padded as the field was (`＠`, or the NUL or FF byte ending it); longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Game-mode menu (name entry, start, new game, text colour) | OK: filler items at their places |
| Name entry (the first item) | Its kana window takes no emulated click or key in the original either; the run picks game start instead |
| The opening and its yes/no question | OK: filler in the box, the two answers under it; Up and click choose |
| Customizing the girl (the demon, her questions and the stat panel) | OK: questions with their menus, the panel's label and value per line cut to their Japanese widths; the dialog box over the bottom box as in the original |
| The default hero name (NAME.DEF) in the story | not yet seen |
| Entering a name, the simulation, saving and loading, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
