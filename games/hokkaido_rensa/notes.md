# LOGiN Disk & Book Series - Hokkaido Rensa Satsujin - Okhotsk ni Kiyu 98 (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `LOGiN Disk & Book Series - Hokkaido Rensa Satsujin - Okhotsk ni Kiyu 98/LOGiN Disk & Book Series - Hokkaido Rensa Satsujin - Okhotsk ni Kiyu 98 [FD]/LOGiN Disk & Book Series - Hokkaido Rensa Satsujin - Okhotsk ni Kiyu 98 (Disk 1).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`OHO/`), on 2 floppies: 84 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  The procedure table was not measured, so a procedure may not grow: text in a procedure (`n` ids) keeps its Japanese byte length.

The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image (every disk's files in `OHO/`, with the scripts' drive letters taken off their file names, started as the floppy's boot does); the base image is the collection's `Naomi - Bishoujo-tachi no Yakata/Naomi - Bishoujo-tachi no Yakata [HD]/Naomi - Bishoujo-tachi no Yakata.hdi` with its own game removed.

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
* The strings in the engine's programs are rewritten in place.

## Script

2637 strings (232 menu items, 2318 messages, 7 name tags (procedure text), 80 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 2637 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* A script runs from the engine's script buffer, which holds 17096 bytes (read off its memory): a file that would outgrow it with the English is refused and named, so keep the longest scripts' English about as long as the Japanese.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own, so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* Program strings (`e` ids: `KNJNAME.CMD`, `CMD/BLKJACK.TCM`): the module's text is Shift-JIS only, so they are written in full-width letters, up to `max_cells` letters each, in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title (the copyright lines) | OK: each line's filler on its own row, above the next line's frame |
| Monitor question and message speed question | OK: filler question and items at their places |
| Name window (KNJNAME.CMD) | OK: its labels as full-width filler at their places, the kana grid as it is; the click script cannot steer it to its done button, so for the rest of the test a test image left out its run in OHO000.MES (no-ops of the same length), after which the original goes on as well |
| The phone call and the harbour scene with its command menu | OK: filler in the bottom box, the command menu's filler items at their places |
| The investigation, the blackjack game, saving and loading, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
