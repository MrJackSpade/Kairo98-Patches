# Arquelphos (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Arquelphos/Arquelphos [HD]/Arquelphos.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **ARQ98** engine (`ARQ98.EXE`): its 171 messages are in the program itself, a block in its data segment (a top table of groups, each group's table of messages, the messages: controls and runs of text, ADL's characters); `pc98tl/arq.py` documents the block and its patch, `pc98tl/adl5.py` the program patch (its run is ADL5's, with one window), `pc98tl/adl_tl.py` the English.  The block rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `DL02/`).

* The block is rebuilt, with the English, in a segment of its own put in after the program's image (the work segments after it move up), and the routine that shows the messages is rewritten in its own bytes to read it there: the messages may take 64 KB together.
* `ARQ98.EXE` gets ADL5's helper in 512 bytes put in at the end of its code segment.  In a run of text, 20h switches to half-width letters: ASCII drawn 8 dots wide from the BIOS 8x16 font into the graphics planes, with the engine's own character wait and paging (a new line whose row would run past the window's bottom pages first).  Before each English word the helper measures it against the window's right edge and starts a new line when it would not fit.
* The program's own strings (the disk prompt, the save and load messages) take ASCII in their own bytes.
* `PCMSET.EXE` (run before the game) draws its lines with ADL5's graphics drawer: it gets the same half-width letters (a 256-byte helper), and its lines are `e` strings too.

## Script

196 strings: 25 program strings, 171 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 196 strings have English so far.

## Limits

* Messages (`m` ids): any length within the block's room (below); `\n` starts a new line.  `max_cells` is a line's width in the window (letters); longer text wraps between words and pages.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* `{X1}`, `{X2}`...: the message's controls between its runs (a key wait, a new line, the window cleared, the portrait); the note says what each does.  Keep each once, in any order; a message without them all is refused.
* The messages are rebuilt into one 64 KB segment: with their English they may take 65536 bytes together.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build that outgrows it is refused.
* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); a character the program writes in at run time (a drive letter, a digit) is `{X1}`..., kept in the English, which is placed so that it stays where the program writes it.  Longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logos, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| PCMSET.EXE (patched), the voice speed setting | OK: its lines half-width filler; the OK button goes on to the game |
| ARQ98: the opening (the village girl, the goddess Rera), the title, the island map | OK: filler half-width (8x16, graphics planes), wrapped between words in the window, paged; the speaker's portrait box at its control; the map's menu (a picture) as it was |
| The stages and their battles, save/load, endings | not yet seen |

The messages' window is set up at run time: from B0h to 230h dots during the opening (48 letters, game.json "message_cells"), narrower where a portrait box is shown; the helper wraps at the window's edge as it is.

The patch adds the message segment (the block's size, in paragraphs) to the program's image; the memory the program asks DOS for past its image stays the same.
