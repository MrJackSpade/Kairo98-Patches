# Branmarker (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Branmarker/Branmarker [FD]/Branmarker (Disk A).hdm` (sha256 in `strings.json`), with the other disks beside it (`Branmarker (Disk B).hdm`, `Branmarker (Disk C).hdm`, `Branmarker (Disk D).hdm`, `Branmarker (Disk E).hdm`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

D.O.'s own program on self-booting floppies: DO loads DOS.SYS (the program, run at 0100:0100) and DATA.SYS (1000:0000); the program loads its overlays at 0100:B98C (the maps' MAPnn, the opening's OPENG from disk B, the ending's BROE from disk E) and MAP02M (the town's talk) at 7B00:0000.  Disk B boots the omake disk's program, a DOS.SYS of its own (its events and a copy of the ending).  `pc98tl/brm.py` documents the formats and the patch, `pc98tl/brm_tl.py` the English.  A build writes every disk (the other disks beside the output, named after it).

* English is drawn in pairs of letters, each pair one character of the game's: the glyph fetch reads a pair's two 8x16 letters from the CG ROM into the two halves of the 16x16 glyph (the Shift-JIS conversion moved inside it; the room from the prompt's blink, an unrolled loop written again as a loop).  The opening's and the ending's own character loops take a pair with its first byte's high bit set.
* The message copy is written again with two more codes: 0E lo hi goes on in DATA.SYS's segment (a bank after DATA.SYS's variables, 1000:CE70-E7FF), 0F lo hi in the text's own segment.  A message's English goes in place; what does not fit goes on in the program's own room (0100:E000-EFFF, DOS.SYS made longer), the bank (the program's and MAP02M's), or after a map overlay's end (up to E000h).  The message buffer is moved from 1000:2940 (214 bytes) to 1000:E800 (1 KB).
* The disk prompt's letter, which the program writes into the prompt, is written where the English puts {D}.
* Menus, names, items and the load prompt (drawn by the plain string drawer), and the opening's and the ending's lines and the staff roll (streams of their own), are written in place.
* `MTL_NOTE.TXT` is put on disk A.

## Script

1508 strings: 33 staff roll lines, 963 messages, 9 ending speakers, 223 plain strings, 1 disk prompts, 279 opening and ending lines.

Translation and the content classification (♥) are done by the translation model; 0 of 1508 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 40 letters (the window's width), four lines a window, more after a key; `\n` a new line.  Keep `{N1}`.. (a name or an item the game puts in; 12 letters are allowed for it when breaking lines) and `{V1}`.. (a number).  The rooms for what does not fit in place are hard limits (a build past them is refused): about 10 KB for the program and MAP02M together, and after each map overlay up to E000h of its segment.
* Plain strings (`p` ids), disk prompts (`d` ids), opening and ending lines (`s`), staff roll lines (`c`) and ending speakers (`n`): in place, up to `max_cells` letters (longer is cut and reported by string id).  A disk prompt needs its `{D}`.  A string takes an even number of letters (one more space otherwise).
* English is ASCII; other characters are written as `?` (curly quotes, dashes and `…` are made ASCII).

## Not handled

* Text drawn into the pictures (the title, the opening's verse, the omake disk's menu).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot disk A with disk B in drive 2: the opening (OPENG's lines) | OK: each line in filler, half-width, at its place on the opening's pictures |
| The load prompt and its data menu, the prompt for disk C (put in, Return), the first map | OK: the prompt and the three data slots in filler; the map's status panel name in filler; a girl's talk on the map: her name on its own line (cut to its room) and the message in filler broken between words at 40 letters |
| ESC: the command menu and its message | OK: the menu's items in filler cut to their rooms, the message under the face in filler |
| A test build with the menu's message 380 letters long | OK: broken between words, four lines a window, the rest in the next windows after a key (its part past its place read from the program's own room) |
| A test build whose opening runs the ending instead (disk E asked for and put in) | OK: the prompt shows disk E's letter where {D} is; the ending's speakers and lines in filler, half-width, at their places |
| Boot disk B (the omake disk): its menu, the BGM gallery and the sound test | OK: the gallery's and the sound test's labels in filler with their numbers after them (the menu is a picture) |

Not reached in this test: the omake disk's recollection mode (it needs the game's saved progress), so its events are not seen on screen; the ending is seen only through a test build that runs it from the opening.
