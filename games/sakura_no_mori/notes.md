# Sakura no Mori (Active MAIN.EXE)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Sakura no Mori/Sakura no Mori [HD]/Sakura no Mori.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-11-06 (`research/clearance.json`).

## Engine

Active's `MAIN.EXE` (Borland C): the game's files are in its folder `SAKURA`; the scripts (`*.HGO`) are a table of entries (labels, menus' items, switches' cases, each with its places in the code) and the code, ops and texts.  The patcher walks every op (their operands read off the program's own routines) and lays a changed script out anew, every place (the entries', the switches' and the conditions') moved; each changed file is written back.  `pc98tl/active_halo.py` documents the formats, `pc98tl/active_halo_tl.py` the English.  Unchanged files rebuild byte for byte.

This build's ops differ from Angel Halo's in sub-op 01h (operands SWW), sub-op 02h (operands SWW), sub-op 24h (no operand) (read off its scripts, every one of which walks and rebuilds byte for byte).

The scripts are packed (`CPX One-Pass SD`, `pc98tl/cpx.py`): runs of bytes copied from up to 255 back, marked by an escape byte.  The program unpacks a file only when it has that header and uses any other as it is, so a changed script is written back unpacked.

* The program draws ASCII half-width by itself, so English takes a byte a letter.
* A message's lines are each a text of their own (a text starts a new line); the patcher breaks the English between words into lines of the narrower window's width (56 cells) and the program pages the window past its lines.
* The opening (`OPENING.DAT`, lines of text) is broken between words at its widest Japanese line and its blocks' line counts set; the main menu's descriptions (`*.GMO`) are written anew with their places.

## Script

4760 strings: 88 choice items, 97 program strings, 6 main menu descriptions, 4545 messages, 24 opening blocks.

Translation and the content classification (♥) are done by the translation model; 0 of 4760 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the line's width, 56): any length; the patcher breaks the lines between words and the program pages.  `\n` in the English forces a new line.  A message is the texts up to another op; a key wait it ends with (`{P}`, `{W}`) is put back when the English leaves it out.  The program holds a script of at most 49152 bytes: a longer build is refused and names the script's strings.
* Choice items (`i` ids): `max_cells` the script's widest Japanese item; past it reported.
* The opening (`o` ids): any number of lines, each at most `max_cells`, centred by the program.
* Main menu descriptions (`d` ids): one line, `max_cells` the menu's widest Japanese one; past it reported.
* Prompts (`p` ids): `max_cells` the Japanese's; past it reported.
* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and reported.  `%s`-style marks are kept.
* `{W}`-style tokens are the controls inside a message (`{P}` a key wait, `{W}` a key wait and a cleared window, `{V0102}` a control and its two bytes); keep the ones that matter.  `\`, `{` and `}` are written `/`, `(` and `)`.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the main menu's items, the opening's titles).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the filler build (hard-disk release): the opening (OPENING.DAT) | OK: each block of its lines in filler, half-width, centred under the pictures, a long one over two lines |
| The main menu (a click past the opening; the pointer moved onto 最初から始める) | OK: the program's line and the item's description in filler, half-width, in the box under the menu |
| A new game: the first scene's messages (clicks) | OK: each message in filler, half-width, broken between words within the box, the page mark at a full box |

Not reached in this test: the choices, the later chapters, save/load and the endings, so they are not seen on screen.
