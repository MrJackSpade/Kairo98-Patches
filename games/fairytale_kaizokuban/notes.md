# Fairytale Kaizokuban (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Fairytale Kaizokuban/Fairytale Kaizokuban [FD hd9]/Fairytale Kaizokuban (Disk A).d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (at the disk's root), on 2 floppies: 56 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  No procedure holds text, so no procedure grows.

This is ADVH, the engine before Adv98V (`ADVH.EXE`, in most games run by `ADVSHELL.COM`): the same bytecode, but no ASCII string command, and every character drawn as a 16x16 glyph.  The patch adds half-width letters to the program (`pc98tl/advh.py`): each English letter is written as `85 xx` (xx its ASCII code), which the program draws from the BIOS's 8x16 font one column wide and steps the cursor one column on; a packed program is unpacked, patched and packed again with its own EXEPACK unpacker.  The disk-change command (wait for disk X in the floppy drive) goes straight on.  Messages page with the key wait `81 90`, which clears the box: a message longer than the box goes on after a key on a fresh page.

The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image (every disk's files in `/`, with the scripts' drive letters taken off their file names, started as the floppy's boot does); the base image is the collection's `Naomi - Bishoujo-tachi no Yakata/Naomi - Bishoujo-tachi no Yakata [HD]/Naomi - Bishoujo-tachi no Yakata.hdi` with its own game removed.

## English display (`pc98tl/adv98v_tl.py`)

* English letters are written as `85 xx` in place of the Japanese text runs
  (see the engine note above); the scripts are rebuilt with them (no offset
  table refers into a script).
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

2120 strings (1907 messages, 206 menu items, 7 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 2120 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* This old build ends each message with a key wait (`81 90`) that clears the box, so pages are split with it (in a one-line box, a line at a time).
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.
* The hero's default name (an `e` id from `NAME.DEF`): up to `max_cells` full-width letters (the engine reads the name as message text); that is as long a name as the name entry takes from the player, or the Japanese name's length where the game has no name entry.  Longer names are cut and reported.  The file pairs the name with the placeholder `＊＊＊`, which the engine swaps for the name as it reads a message (the name entry writes the name the player types under the same placeholder): keep `＊＊＊` in the English of a message where the name goes.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The title line ADVSHELL.COM prints while it loads the engine (`Ｆａｉｒｙｔａｌｅ　海賊版`, a brand name in full-width letters and three kanji): the program-string search takes only runs with kana.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Start menu and its submenu | OK: filler items, the highlight moved with the arrow keys; the second item opens a five-item menu |
| The opening story (the president) | OK: filler wrapped in the bottom box, pages waiting for a key |
| The stories behind the other menu items, Disk B's pictures, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
