# Injuu Gakuen - La Blue Girl (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Injuu Gakuen - La Blue Girl/Injuu Gakuen - La Blue Girl [HD]/Injuu Gakuen - La Blue Girl.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-03 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`INJU/`), on a hard-disk image: 101 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it; this build has the later engines' extended opcodes).  Every script tokenizes and rebuilds byte for byte.  The procedure table holds 20 slots of 76 bytes (read off the engine's memory).

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
* Procedures (`B9 n`) are copied into fixed slots of a table (one per number, run on into free slots after it); a build that would overrun one is refused.
* The strings in the engine's programs are rewritten in place.

## Script

6127 strings (39 name tags (procedure text), 5534 messages, 553 menu items, 1 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 6127 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own (76 bytes a slot), so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Startup menu (start, tutorial, extras, clear saves) | OK: item filler at fixed width in the menu window |
| Title and opening prompts | OK: one-line prompts at their Japanese width (cut and reported) |
| First classroom scene: command menu and its target submenu | OK: menus pop up under the cursor with the filler items; speaker's name on its line, message wrapped between words below it |
| System submenu (save, load, slots) | OK: filler at its place; SYSTEM.MES stays within its 1051 bytes (1047) |
| Operation tutorial (startup menu, second item) | OK: a long message paged: three lines, a click, the rest on the next page under the speaker's name; the two-item menu after it. The mouse diagram's labels are drawn in the picture |
| Leaving the classroom (the scene's commands in the order it wants), saving and loading, later scenes, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
