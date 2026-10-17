# Star Platinum (Custom)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Star Platinum/Star Platinum [HD]/Star Platinum.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Custom's own engine under MS-DOS on the hard disk: `STAR_PT\SP.COM` loads the resident drivers (`VAL24`, `CSTMOUSE`, `TRPSCHRN`, `CSTMET`, `CSTMIDI.BIN`) and runs the modules in turn (`CUSTLOGO`, `SPO`, `SPG`, `SPD`, `SPF`, `SPE`, `SPV.BIN`), each a PKLITE 1.50 program.  The text is in GDM archives (an LZSS offset table, then LZSS entries): `SCENARIO.GDM` (each entry bytecode and a pool of strings it names by number) and `MUSIC.GDM` (the card game's balloons, the staff rolls).  `pc98tl/starpt.py` documents the formats, `pc98tl/starpt_tl.py` the English, `pc98tl/pklite.py` the unpacking.  A build with no English leaves the disk as it is.

* The programs are unpacked by running PKLITE's own decompressor under emulation (twice, loaded apart, for the relocations) and written unpacked.
* English half-width: the modules that draw text (`SPV`, `SPG`, `SPD`, `SPE`, `SPF`) drew a byte below 100h as a blank; their glyph routine calls a helper (a segment put in before the data segment) that draws it from the BIOS 8x16 font.
* The script's strings are written again at any length (the bytecode names them by number); the patcher breaks the English between words at the window's width (a narrower layout's where the Japanese is narrower), under the speaker's name, and starts a new screen with the name again after four lines.  SPV's script buffer is made 65,520 bytes.
* The card game's balloons broken at 27 letters (the program breaks a line itself after 28), up to four lines; the staff rolls' lines centred where the Japanese was.
* The programs' own text (the system menu, the card rules, the drivers' and the start-up disk maker's DOS messages) in place.
* `MTL_NOTE.TXT` is put in the game's folder (`STAR_PT`).

## Script

2451 strings: 72 card game balloons, 309 menu lines, 44 staff roll lines, 844 speeches, 1101 narration paragraphs, 37 speaker names, 44 program texts.

Translation and the content classification (♥) are done by the translation model; 0 of 2451 strings have English so far.

## Limits

* Narration (`m`), speeches (`d`): any length, broken between words and paged by the patcher; `\n` a new line; keep each `{..}` code (`{p15_}` a pause, `{w10}` the typing speed, `{k}` a key wait).  `{Gxxxx}` is a character of the game's own font and is dropped.  A scene with its English must fit the script buffer (65,520 bytes): a build over it is refused with the entry's number.
* Speaker names (`n`): up to 7 letters (the column before the lines).
* Menu lines (`c`): one line, `max_cells` letters (the box keeps the Japanese width; longer is reported by string id).
* Balloons (`b`): broken at 27 letters, up to four lines; more is cut and reported.
* Staff roll lines (`r`): one line, centred.
* Program texts (`e`): in place, `max_cells` letters; longer is cut and reported by string id; keep each `%s`, `%d`, `%c`, `%ld` and `{ESC}`.
* English uses ASCII; other characters are written as `?` (curly quotes, dashes and `…` are made ASCII).

## Not handled

* Text drawn into the pictures (the opening's subtitles, the title).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (SP.COM: the drivers, the logo, the opening's pictures); Esc to the top menu | OK: the menu's title and choices in filler, half-width; the box keeps the Japanese width (a longer choice is cut by the program) |
| Story mode, start from the beginning: the prologue's speeches (about 5 keys) | OK: each speaker's name and lines in filler, half-width, broken between words under the name; four lines a screen, a speech going on to a new screen with the name again |
| The top menu's second choice (the card game): its introduction, the first balloon | OK: the introduction's lines in filler, paged in its box; the balloon in filler, broken at 27 letters, no blank lines |
| Right click in the card game: the system menu (SPG.BIN's own text) | OK: every choice in filler, half-width, the settings' values beside them |

Not reached in this test: the later scenes' narration (its narrower windows), the card rules' explanations (SPD.BIN), the staff rolls, saving and loading; the drivers' and the start-up disk maker's messages show only when memory is short or the MIDI search hung.
