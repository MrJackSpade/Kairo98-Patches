# Pia Carrot e Youkoso!! (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Pia Carrot e Youkoso!!/Pia Carrot e Youkoso!! [HD]/Pia Carrot e Youkoso!!.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-02 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`PIA/`), on a hard-disk image: 352 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it; this build has the later engines' extended opcodes).  Every script tokenizes and rebuilds byte for byte.  The procedure table holds 20 slots of 76 bytes (read off the engine's memory).

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
* A message after a speaker's name tag (a procedure that ends its line) starts on the frame's second line.
* Procedures are read for what they print: a name tag ends its line, a fixed text (an ellipsis) or a name shown from a variable (up to 8 columns, the name entry's limit) moves along it, a line break moves down, and a frame or text reset starts a fresh page.  A message continues the page of the text before it, wrapped from where that left off, with room left for what is printed after it.
* The hero's name, printed mid-message by a procedure call with its inline flag set, leaves room for the longest name the name entry takes (8 columns), and the text after it carries on the same line.
* Procedures (`B9 n`) are copied into fixed slots of a table (one per number, run on into free slots after it); a build that would overrun one is refused.
* String variables' values (`@n='...'` arguments) and the strings in the engine's programs are rewritten in place.

## Script

8564 strings (8141 messages, 95 name tags (procedure text), 291 menu items, 22 string variable values, 15 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 8564 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* The hero's name is printed between two message runs: the run before it ends where the name starts (end it with a space if one should come before the name), the run after it starts right after the name.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Strings in `*.MEC` files: the engine loads these into one shared buffer, each at its own offset, so a `.MEC` file can only grow up to the next file's offset (or, for the top one, as far as the original game's loads reach; past that the buffer meets the engine's stack), often only a few dozen bytes past its Japanese.  The patcher refuses a build where one outgrows its room and lists that file's strings.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own (76 bytes a slot), so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters); the hero's default name parts (offered again by the name entry) up to 8 letters.  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name window's character tables stay Japanese: the engine picks characters from them by position (its English-letter table lets the player type an English name).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Name prompt and name entry window | OK: prompts as filler cut to their Japanese width (ending before the input field); the window's labels as filler at each label's place, cut to its bytes; the hero's default name (8-letter filler) in the field; Finish clicked through |
| Menus (uniform select, yes/no) | OK: menu items in their boxes at fixed width; the question in its one-line frame |
| Opening narration | OK: filler wrapped between words to the frame, 3-line pages with a wait between (the engine used to wrap mid-word and draw a fourth line over the first) |
| Hero's name inside a message | OK: name (filler) printed inline; the text after it carries on the same line without a mid-word break |
| Speaker name tags in the first scene | OK: tag filler (cut to its procedure's slots) on the first line, the message on the next two, later pages of 3 lines |
| Save/load, item lists, picture viewer | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
