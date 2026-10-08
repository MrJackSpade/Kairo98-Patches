# Glass no Destiny (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Glass no Destiny/Glass no Destiny [HD]/Glass no Destiny.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`GLASS/`), on a hard-disk image: 111 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it; this build has the later engines' extended opcodes).  Every script tokenizes and rebuilds byte for byte.  No procedure holds text, so no procedure grows.

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
* The strings in the engine's programs are rewritten in place.

## Script

3339 strings (3283 messages, 11 menu items, 42 text file lines, 3 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 3339 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* A script runs from the engine's script buffer, which holds 18612 bytes (read off its memory): a file that would outgrow it with the English is refused and named, so keep the longest scripts' English about as long as the Japanese.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Text file lines (`t` ids: `SR_PARTS/STAFF_1.DAT`, `SR_PARTS/STAFF_2.DAT`, `SR_PARTS/STAFF_3.DAT`, `SR_PARTS/STAFF_4.DAT`, `SR_PARTS/STAFF_5.DAT`, `SR_PARTS/STAFF_6.DAT`, shown as they are, e.g. the opening roll): each line up to its Japanese byte length (twice `max_cells` in letters), as the file is loaded into a fixed place in memory; longer ones are cut and reported.
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Opening (the house in the birch wood, the room, the move, the cat) | OK: filler wrapped over the bottom of each picture, pages waiting for a click; pictures change with the story |
| Staff rolls (SR_PARTS/STAFF_1-6.DAT) | not yet seen |
| Menus, saving and loading, later scenes, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
