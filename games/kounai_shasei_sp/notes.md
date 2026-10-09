# Kounai Shasei Special Disk (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Kounai Shasei/Kounai Shasei (Special Disk) [FD hd9]/Kounai Shasei (Special Disk).d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (at the disk's root), on its boot floppy, patched in place: 21 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  The procedure table was not measured, so a procedure may not grow: text in a procedure (`n` ids) keeps its Japanese byte length.

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

## Script

216 strings (148 messages, 6 name tags (procedure text), 62 menu items).

Translation and the content classification (♥) are done by the translation model; 0 of 216 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* This old build ends each message with a key wait (`81 90`) that clears the box, so pages are split with it (in a one-line box, a line at a time).
* A script runs from the engine's script buffer, which holds 17096 bytes (read off its memory): a file that would outgrow it with the English is refused and named, so keep the longest scripts' English about as long as the Japanese.
* This engine hangs on an ASCII string inside a procedure, so text kept in procedures (the speakers' name tags, `n` ids) is written in full-width letters, each two columns wide and two bytes long; a tag grows only into its procedure's free slots, so keep tags about as long as the Japanese.
* This engine draws menus from Shift-JIS only (an ASCII string in a menu crashes it), so menu items are written in full-width letters: `max_cells` letters each, cut and padded.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own, so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Opening exchange (the X team and the users) and the title | OK: filler lines in their colours at their places, waiting for a key |
| Main menu (four corners) with its explanation | OK: filler heading, items at their places with the highlight on the first, the explanation below |
| Quiz (question titles, the questions with their answer menus and hints, right and wrong answers) | OK: filler question above the items, the hint at its place; the answer screens' lines (procedures) in full-width filler |
| The penalty game after a wrong answer | OK: speaker tag and filler, then its menu, which returns to itself on a wrong pick as in the original |
| The music and graphics corners, the bonus corner, the end of the quiz | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
