# Viper V8 RS (Sogna)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Viper V8 RS/Viper V8 RS [HD]/Viper V8 RS.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Sogna's SGS (`V8RS/SGS.COM`): each script (`*.SIL`, up to 16 KB) is read into the program's segment and run op by op.  The ops' lengths are read off the program's own routines (each build has its own table), so the scripts are walked exactly; the gotos, conditional jumps and calls hold script offsets and move with the text, so a script may grow.  `pc98tl/sgs.py` documents the format, `pc98tl/sgs_tl.py` the English.  Unchanged files rebuild byte for byte.

* The patch hooks the program's message and menu loops: a 7Fh mark (no JIS pair starts with it) turns half-width letters on and off, each letter one text-VRAM cell in the message's colour, the line breaking at the window's edge as for the program's own characters.  The hook's code sits at the end of the script's 16 KB room, so every script is written with it there.
* The patcher breaks the lines between words at the window's edge (op 03 sets the window, op 4E the indent after a speaker's name; the program keeps them from script to script), counting the names a message inserts.

## Script

678 strings: 7 program console lines, 62 menu items, 579 messages, 19 speakers' names, 11 system messages.

Translation and the content classification (♥) are done by the translation model; 0 of 678 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the window's usual width): any length; the patcher breaks the lines between words and the window scrolls.  `\n` in the English forces a new line.  A script with its English may take 16 KB less the hook's bytes; a longer build is refused and names the script and its strings.  The fullest scripts are close to that already, so their English must stay about as long in bytes as the Japanese (two bytes a character, one a letter).
* Menu items (`i` ids): one line, `max_cells` the menu's widest Japanese item; past it reported.
* Speakers' names (`n` ids): `max_cells` the Japanese's; the program keeps 48 bytes (a letter one, a full-width character two, two more for the half-width marks), past them cut and reported.
* System messages (`s` ids, the disk prompts): 79 bytes; past them cut and reported.
* Program console lines (`c` ids): printed before the game starts; in place, `max_cells` the Japanese's bytes; past them cut and reported.
* `{C1}`-style tokens are the commands inside a string (key waits, colours, inserted names, pictures) and must be kept; `{X7625}`-style tokens are the game's own characters (JIS row 76h).
* English is ASCII (half-width); another character is written full-width when JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the titles, the picture menu's captions).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (AUTOEXEC: FMX, SGS), the title and the picture menu | OK |
| The picture menu's top story (Up, Enter): the opening scenes | OK: the speaker's name in filler in its colour, the messages in filler half-width, each starting on a cleared window, broken between words at the window's edge and indented under the name (op 72's messages) |
