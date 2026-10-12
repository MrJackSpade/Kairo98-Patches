# Angel Halo (Active MAIN98.EXE)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Angel Halo/Angel Halo (FD version) [HD]/Angel Halo (FD version).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Active's `MAIN98.EXE` (Borland C): the game's files are in the archive `FDHALO.PAK` (its files found by a hash of their names); the scripts (`*.HGO`) are a table of entries (labels, menus' items, switches' cases, each with its places in the code) and the code, ops and texts.  The patcher walks every op (their operands read off the program's own routines) and lays a changed script out anew, every place (the entries', the switches' and the conditions') moved; the archive is written anew.  `pc98tl/active_halo.py` documents the formats, `pc98tl/active_halo_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws ASCII half-width by itself, so English takes a byte a letter.
* A message's lines are each a text of their own (a text starts a new line); the patcher breaks the English between words into lines of the narrower window's width (56 cells) and the program pages the window past its lines.
* The opening (`OPENING.DAT`, lines of text) is broken between words at its widest Japanese line and its blocks' line counts set; the main menu's descriptions (`*.GMO`) are written anew with their places.

## Script

5901 strings: 150 choice items, 99 program strings, 6 main menu descriptions, 5600 messages, 45 opening blocks, 1 prompts.

Translation and the content classification (♥) are done by the translation model; 0 of 5901 strings have English so far.

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
| Boot from the hard disk: the opening (OPENING.DAT's blocks over the pictures), the title | OK: the opening's blocks in filler half-width, centred and broken between words (the program draws ASCII by itself); the title's prompt line (a program string) in filler |
| The main menu: the mouse to its second item (最初から始める), clicked; the first scenes' messages | OK: the menu's description line in filler; the messages in filler half-width, broken between words into the window's lines, a key wait between them; no choice came up in these scenes (the choices' items untested) |
