# M Hard (Aaru)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `M Hard/M Hard [HD]/M Hard.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Aaru's `MHARD.EXE`: the scripts (`*.AB`) are files in the FL1 archives (`*.FL1`, a directory of names and sizes at the end), compressed with LZSS in some games; a script is ops, each a word and its operands (the formats read off the program's own handlers).  The patcher lays a changed script out anew, its jumps moved, compresses it again when it was and writes the archive anew.  `pc98tl/aaru.py` documents the formats, `pc98tl/aaru_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws ASCII half-width by itself, but from 60h one letter low (its half-width codes step over Shift-JIS's missing 857Fh); the patcher writes those bytes one higher, so lowercase letters show as they should.
* The program breaks a message's line at its window's edge; the patcher breaks the English between words with the program's new line (`\N`) between the lines.
* The program's own strings (its menus) are replaced in place in the program (packed, but with its code and data as they are), their room filled with spaces.

## Script

2704 strings: 58 choice items, 20 program strings, 2626 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 2704 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the window's width, 60 half-width cells): any length; the patcher breaks the lines between words.  `\n` in the English forces a new line (the Japanese's speaker names stand on a line of their own).  A script may take 65535 bytes unpacked; a longer build is refused and names its strings.
* Choice items (`i` ids): one line, `max_cells` the script's widest Japanese item; past it reported.
* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and reported.  A leading `{C0}`-style token (a colour) is kept.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.  `\`, `%`, `|`, `` ` ``, `{`, `}` and `~` are written `/`, `pct`, `!`, `'`, `(`, `)` and `-`.

## Not handled

* Text drawn into the pictures (the titles).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk: the title and its menu; Enter on its first item | OK: the menu's items in filler half-width (the program's strings, in place); the game starts |
| The opening's messages, Enter after each | OK: the messages in filler half-width, lowercase letters right (written a byte higher), broken between words; no choice came up in these scenes (the choices' items untested) |
