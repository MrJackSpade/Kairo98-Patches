# Moonlight Chan Rin Shan (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Moonlight Chan Rin Shan/Moonlight Chan Rin Shan [HD]/Moonlight Chan Rin Shan.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

D.O.'s **CHAN** engine (`CHAN.EXE`), a mahjong game with a quiz: the quiz in `QDAT` (a directory of its members; each a table of 100 questions, then the questions with every byte inverted: four offsets, the right choice, the question and its three choices), the girls' profiles and the program's strings in `CHAN.EXE` itself.  `pc98tl/chan.py` documents the formats and the program patch, `pc98tl/chan_tl.py` the English.  `QDAT` and the profiles rebuild byte for byte.

The patch works on the game's hard-disk release (the game in `MOON/`).

* `CHAN.EXE` gets a helper put in at the end of its code segment (the segments after it move up).  A byte under 80h is a half-width letter: drawn 8 dots wide from the BIOS 8x16 font, bold as the program's characters, in the caller's colour.  In the text window (the questions, the profiles) the line's room is taken one for it, a word that would not fit what is left of the line starts a new line (the window's own, paging at its last row), and a space at a line's start is not drawn; the string routine (the choices, the menus) draws it the same way.
* `QDAT` is rebuilt with the English (each member padded to a paragraph, the directory anew); past the program's five reads (143360 bytes) the last read is made 8000h bytes and the stack and the memory the program asks for move up with it, 163840 bytes in all.
* The profiles are rebuilt as one block in the room the Japanese took, their table's offsets anew; the program's other strings are written in their own bytes.

## Script

4497 strings: 3251 quiz choices, 38 program strings, 1208 messages (quiz questions and profiles).

Translation and the content classification (♥) are done by the translation model; 0 of 4497 strings have English so far.

## Limits

* Messages (`m` ids): a quiz question in the quiz window (`max_cells` 50 letters a line, 3 lines, then a key wait and the window scrolled); a profile in its window (38 letters a line); `\n` starts a new line.  The program wraps between words.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* Quiz choices (`c` ids): one line each at its place, `max_cells` letters to the screen's edge; a new line is written as a space.
* `QDAT` with its English may take 163840 bytes (now 139760 with the Japanese): each English letter is one byte, a Japanese character two; a member (100 questions) may take 32 KB.  A build past either is refused.
* The profiles share the bytes the Japanese took (1382); a build past it is refused and names them.
* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures, the mahjong tiles).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The title menu (patched) | OK: its items half-width filler (the string routine), the pointer's item highlighted |
| A test copy whose title loop draws the first girl's profile at once (the text window) | OK: the profile's filler half-width, 38 letters a line, wrapped between words |
| The mahjong game, the quiz, the album, endings | not yet seen: the title menu takes no click in the emulator (the unpatched game neither); the clicks reach the program's button word, but no item starts |

The quiz questions and the profiles are drawn by the same text window routine the test copy used; the choices and the menus by the string routine the title menu shows.
