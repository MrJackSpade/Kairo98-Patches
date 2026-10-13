# Mai (Cocktail Soft / Fairytale)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Mai/Mai [HD]/Mai.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (`MAI/`), on a hard-disk image: 52 scripts with text (`MES/*.MES`, `*.MEC`) in its bytecode (`pc98tl/adv98v.py` documents it; this build has the later engines' extended opcodes).  Every script tokenizes and rebuilds byte for byte.  The procedure table was not measured, so a procedure may not grow: text in a procedure (`n` ids) keeps its Japanese byte length.

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

1965 strings (40 name tags (procedure text), 1837 messages, 41 menu items, 46 text file lines, 1 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 1965 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* A script runs from the engine's script buffer, which holds 12288 bytes (read off its memory): a file that would outgrow it with the English is refused and named, so keep the longest scripts' English about as long as the Japanese.
* This engine hangs on an ASCII string inside a procedure, so text kept in procedures (the speakers' name tags, `n` ids) is written in full-width letters, each two columns wide and two bytes long; a tag grows only into its procedure's free slots, so keep tags about as long as the Japanese.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free slots after its own, so the tags of one procedure share a few bytes beyond the Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build that overruns a slot and names that procedure's strings.
* Text file lines (`t` ids: `GAIBU/STAFF.TXT`, shown as they are, e.g. the opening roll): the files hold Shift-JIS only (no half-width letters), so they are written in full-width letters, each line up to `max_cells` letters (its Japanese byte length), as the file is loaded into a fixed place in memory; longer ones are cut and reported.
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.
* Names in data files (`e` ids from `NAME.DEF`): written in place, each up to its field's room (`max_cells` full-width letters, as the files hold these names in Shift-JIS only: the name with the spaces around it and any `＠` padding after it), a shorter one padded as the field was (`＠`, or the NUL or FF byte ending it); longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Opening (Mai's homework, her friend at the door, the garden, the room) | OK: the speaker tag and filler wrapped in the box under the picture, pages waiting for a click |
| Title | OK |
| The game proper, the staff roll (GAIBU/STAFF.TXT), saving and loading, endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

Needs DIP switch 2-8 OFF (game.json "dipsw"; AdvBIOS asks for it and stops otherwise).
