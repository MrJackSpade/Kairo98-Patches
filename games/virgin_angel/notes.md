# Virgin Angel (Crystal Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Virgin Angel/Virgin Angel [HD]/Crystal Soft (Virgin Angel).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Crystal Soft's own engine (`V_ANGEL\M.EXE`, EXEPACK, run by the start-up batch `HDGAME.BAT` as `m cmd00.scb`) under MS-DOS on the hard disk.  The scenario's text is `CMD00.TXB` (every byte complemented; texts ended by 1Ah, lines by 00h, a page by a line of 12h, a speaker's lines after 13h and the name), the most frequent characters a byte each by a table in M.EXE.  `pc98tl/vangel.py` documents it, `pc98tl/vangel_tl.py` the English.  A build with no English leaves the disk as it is.

* English two letters a character, as two-byte codes of the Shift-JIS leads no text uses; the program's four glyph routines call, in place of their BIOS glyph call, a helper in a segment put in before the data segment, which draws such a code from two 8x16 BIOS glyphs.  M.EXE is written unpacked.
* The patcher breaks the English between words (56 letters a line, a speaker's lines narrower by the name), pads each page's lines to one length (the program centres each line), and starts a new page after four lines; a speech going on to a new page shows the speaker's name again.
* M.EXE's own text (the opening's lines, the staff roll, the music mode) in place; its console messages (the mouse prompt, start-up errors) in place as ASCII.
* The start-up batch files' lines (the sound board's check and choice) written as English DOS text, their colours kept; `ANNOUNCE.TXT` (the title menu's announcement) written as ASCII.
* `MTL_NOTE.TXT` is put in the game's folder (`V_ANGEL`).

## Script

2024 strings: 21 announcement lines, 25 start-up batch lines, 373 speeches, 1523 narration paragraphs, 18 speaker names, 64 program texts.

Translation and the content classification (♥) are done by the translation model; 0 of 2024 strings have English so far.

## Limits

* Narration (`m`), speeches (`d`): any length, broken between words and paged by the patcher; `\n` a new line.  A text with its English must fit the program's text buffer (8191 bytes): a build over it is refused with the text's number.
* Speaker names (`n`): short; a speaker's lines are narrower by the name.
* Program texts (`e`): in place, `max_cells` letters; longer is cut and reported by string id.
* Batch lines (`b`): any length; keep each `{Cn}` (a colour).  `<`, `>` and `|` are written as `(`, `)` and `/` (DOS's redirections).
* Announcement lines (`a`): up to `max_cells` letters a line; longer is cut and reported.
* English uses letters, digits and `.,'!?-` (`"` written as `'`, `:` and `;` as `,`, brackets as `-`); anything else as `?`.

## Not handled

* Text drawn into the pictures (the title menu's choices, the title).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk: the start-up batch (HDGAME.BAT), its sound board check and choice; 2 picked | OK: every line in filler, ASCII DOS text, the colours kept |
| M.EXE's mouse prompt; Y | OK: the prompt in filler, ASCII |
| The title menu's first choice: the opening's lines (M.EXE) | OK: each line in filler, half-width two letters a character, centred as in the original |
| The first text: narration, then a speaker's lines (about 5 clicks) | OK: narration in filler, broken between words, its lines lined up; the speaker's name in filler before the first line and the rest under it; four lines a page |

Not reached in this test: the title menu's other choices (the music mode, the announcement: the menu took neither the keys nor the mouse moves the test sent), saving and loading, the endings and the staff roll.
