# Doop (MBS Truse)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Doop/Doop [HD]/Doop.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

MBS Truse's MAPL system (`MAPL.EXE`, LZEXE): the `*.MPX` scenes are bytecode with their text in a block of their own (XORed).  The patcher lays a scene's text out again and moves the code's string references; the code itself is unchanged.  `pc98tl/mapl.py` documents the format, `pc98tl/mapl_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws only Shift-JIS from the kanji ROM.  The patched MAPL.EXE (written unpacked) draws English as letter pairs, two ANK letters in one 16-dot cell (as pc98tl/illusion_font24.py does); a cell is two half-width letters.  The program's own strings (notices, errors, the CG rate) are replaced in place.
* The opening (`DOOP_OP.EXE`) draws its subtitles on the text layer; the patched program lays them out after its image (`pc98tl/mapl_op.py`) and draws pairs as two ANK characters.
* The game is played with the mouse.

## Script

7819 strings: 453 menu commands, 1 a DOS notice, 50 program strings (notices, errors), 7292 messages, 23 opening subtitles.

Translation and the content classification (♥) are done by the translation model; 0 of 7819 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` 72, letters a line holds): any length.  The window is 36 cells (72 letters) by four lines; the patcher breaks the English between words ("%N"), a line after "【name】" indented by the name's width as the program does, and the program waits for a click when the window is full.  Keep the `%` commands ("%K" a key wait and a new window, "%N" a new line, "%GF,file;" a picture ...) where they are.  A scene's text may take 65520 bytes; a longer build is refused and names its strings.
* Menu commands (`c` ids): one line, `max_cells` letters; past it reported.
* Program strings (`l` ids): in place, `max_cells` their room in letters (a letter a byte); keep `%s` and `%%n`; past it cut and reported.  The DOS notice (`d` id): plain ASCII, in place.
* English is ASCII (pairs); another character is written full-width (a cell) when Shift-JIS has it, else as `?`.
* Opening subtitles (`o` ids): two lines of 74 letters at most, broken between words (more cut and reported); `{#c}` a colour, keep it.  Together they may take about 2 KB.

## Not handled

* Text drawn into the pictures (titles, the chapter cards).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk: the opening (DOOP_OP.EXE) playing, shots every 12 s | OK: the subtitles in filler half-width on the text layer (letter pairs), broken between words onto two lines; the opening plays to its end |
| The title, a click; the prologue's messages (MAPL.EXE), a click after each | OK: the messages in filler half-width (pairs), broken between words, the program's key waits and pages kept |
| Further clicks to the scene's first menu | OK: a menu command in filler (its highlighted box) |
