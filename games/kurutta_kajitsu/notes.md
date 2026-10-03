# Kurutta Kajitsu (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Kurutta Kajitsu/Kurutta Kajitsu [FD]/Kurutta Kajitsu (Disk A).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-02 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`KAJITSU/`), on 3 floppies: 92 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  The procedure table holds 20 slots of 76 bytes (read off the engine's memory).

The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image (every disk's files in `KAJITSU/`, with the scripts' drive letters taken off their file names, started as the floppy's boot does); the base image is the collection's `Naomi - Bishoujo-tachi no Yakata/Naomi - Bishoujo-tachi no Yakata [HD]/Naomi - Bishoujo-tachi no Yakata.hdi` with its own game removed.

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
* Procedures are read for what they print: a name tag ends its line, a fixed text (an ellipsis) or a name shown from a variable (its Japanese width) moves along it, a line break moves down, and a frame or text reset starts a fresh page.  A message continues the page of the text before it, wrapped from where that left off, with room left for what is printed after it.
* Procedures (`B9 n`) are copied into fixed slots of a table (one per number, run on into free slots after it); a build that would overrun one is refused.
* String variables' values (`@n='...'` arguments) are rewritten in place.

## Script

3937 strings (3696 messages, 222 menu items, 10 name tags (procedure text), 9 string variable values).

Translation and the content classification (♥) are done by the translation model; 0 of 3937 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* This engine draws menus from Shift-JIS only (an ASCII string in a menu crashes it), so menu items are written in full-width letters: `max_cells` letters each, cut and padded.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own (76 bytes a slot), so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in letters).  Longer ones are refused.  `'` and `"` are written full-width (they would end the script's quoting).

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Floppy set laid out on a hard disk, title and load menu | OK: boots from the hard disk with every disk's files; the load menu's items as full-width filler |
| New game: opening messages | OK: filler wrapped to the message box (53 columns) in 4-line pages; the wait marker as 2-letter filler at its place |
| First command menus (look / talk / save, then places) | OK: full-width filler items; picking items goes on to the next messages (ASCII items crashed this engine) |
| Save/load, later chapters (disk B and C files), endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
