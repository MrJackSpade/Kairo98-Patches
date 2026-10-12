# Viper F-40 (Sogna, SGS21)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Viper F-40/Viper F-40 [HD]/Viper F-40.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Sogna's `SGS21.COM` (protected mode): the scripts (`*.WIN`) are files in `SGS.DAT` (a directory of 32-byte entries, most files LZ-compressed); a script is ops, each a byte and its operands (the formats read off the program's own routines), and the ops that go somewhere hold a place in the script.  The patcher lays a changed script out anew with those places moved, compresses it again and puts it at `SGS.DAT`'s end (the archive is mostly pictures and sounds).  `pc98tl/sgs21.py` documents the formats, `pc98tl/sgs21_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws ASCII half-width by itself (messages, menus, its dialogs).
* A message's window breaks its line at the right edge and does not scroll; the patcher breaks the English between words (following the column from one message to the next, as the program does) and, when the window's rows are full, ends the message there and goes on after a key wait and a clear.
* The game is started from its hard-disk boot floppy's menu, with the CD in the drive (`game.json` `boot_fd`, `cd`); the program refuses to start from the hard disk's prompt.

## Script

2099 strings: 2 program console lines, 26 menu items, 5 program strings, 2040 messages, 26 speaker names.

Translation and the content classification (♥) are done by the translation model; 0 of 2099 strings have English so far.

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
| Boot from the hard-disk boot floppy (the CD in the drive): its menu's first item, then the opening and the title | OK: the game starts from the patched hard disk; the title is a picture |
| The first scene's messages and its menu, a click after each | OK: a speaker's name (its slot) and the message in filler half-width on one line, a longer one broken between words; the menu's items in filler half-width |
