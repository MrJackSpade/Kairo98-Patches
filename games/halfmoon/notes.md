# Halfmoon ni Kawaru made (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Halfmoon ni Kawaru made/Halfmoon ni Kawaru made [HD]/Halfmoon ni Kawaru made.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`RAMIYA/`), on a hard-disk image: 84 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it; this build has the later engines' extended opcodes).  Every script tokenizes and rebuilds byte for byte.  The procedure table holds 20 slots of 76 bytes (read off the engine's memory).

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

4937 strings (82 name tags (procedure text), 4823 messages, 10 menu items, 7 string variable values, 15 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 4937 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* This old build ends each message with a key wait (`81 90`) that clears the box, so pages are split with it; in its one-line box a message pages a line at a time.
* A script runs from the engine's script buffer, which holds 17744 bytes (read off its memory): a file that would outgrow it with the English is refused and named, so keep the longest scripts' English about as long as the Japanese.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Strings in `*.MEC` files: the engine loads these into one shared buffer, each at its own offset, so a `.MEC` file can only grow up to the next file's offset (or, for the top one, as far as the original game's loads reach; past that the buffer meets the engine's stack), often only a few dozen bytes past its Japanese.  The patcher refuses a build where one outgrows its room and lists that file's strings.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own (76 bytes a slot), so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters).  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name window's character tables stay Japanese: the engine picks characters from them by position (its English-letter table lets the player type an English name).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Story select (the four girls' panels, artwork) and its centre menu | OK: the centre menu's filler items; Suzuka's panel chosen with a click |
| Suzuka's prologue (full-screen text) and the escape scene | OK: filler wrapped between words, the speaker's tag above each message, pages waiting for a click; the game's key wait clears the box, so pages end with it (page_break 81 90) and no extra cleared box comes between them |
| The other three stories, the menu's other items, saving and loading, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
