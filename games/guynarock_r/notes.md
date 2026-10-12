# Guynarock R (Sogna, SGS21)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Guynarock R/Guynarock R [HD]/Guynarock R.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Sogna's `SGS21.COM` (protected mode): the scripts (`*.WIN`) are files in `SGS.DAT` (a directory of 32-byte entries, most files LZ-compressed); a script is ops, each a byte and its operands (the formats read off the program's own routines), and the ops that go somewhere hold a place in the script.  The patcher lays a changed script out anew with those places moved, compresses it again and puts it at `SGS.DAT`'s end (the archive is mostly pictures and sounds).  `pc98tl/sgs21.py` documents the formats, `pc98tl/sgs21_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws ASCII half-width by itself (messages, menus, its dialogs).
* A message's window breaks its line at the right edge and does not scroll; the patcher breaks the English between words (following the column from one message to the next, as the program does) and, when the window's rows are full, ends the message there and goes on after a key wait and a clear.
* The game is started from its hard-disk boot floppy's menu, with the CD in the drive (`game.json` `boot_fd`, `cd`); the program refuses to start from the hard disk's prompt.

## Script

590 strings: 2 program console lines, 56 menu items, 5 program strings, 520 messages, 7 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 590 strings have English so far.

## Limits

* Messages (`m` ids): any length.  `max_cells` is a line's room in half-width cells (the window's width less the indent where a line after the first starts).  `{N03}`-style tokens are a speaker's name (an `n` string) drawn at that place: keep them.  `{CLR}` clears the window, `{W}` is a mark the program skips; `\n` forces a new line.  A script may take 65535 bytes; a longer build is refused and names its strings.
* Speaker names (`n` ids): at most 63 bytes (cut past it and reported); `max_cells` the Japanese's width, past it reported (a message's text goes on right after the name).
* Menu items (`i` ids): at most 81 bytes (cut and reported); `max_cells` the menu's widest Japanese item, past it reported (the box grows with its longest item).
* Program strings (`l` ids, its dialogs) and console lines (`c` ids, printed before the game): in place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and reported.  The dialogs' YES / NO line keeps its two words where the Japanese has them (the mouse's places are fixed).
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.  `\` and `~` are written `/` and `-`.

## Not handled

* Text drawn into the pictures (the title menu).
* The boot floppy's install menu (`INSMENU`), which is not part of the game's disk.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard-disk boot floppy (the CD in the drive): its menu's first item, then the title | OK: the game starts from the patched hard disk; the title menu is a picture |
| The opening's narration and the first scene, a click after each | OK: the narration's messages in filler half-width, broken between words and going on from one message to the next on a line (a space between); a full window waits for a click and goes on in a cleared one; a speaker's name (its slot) before a message |
