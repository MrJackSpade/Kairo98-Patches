# Waku Waku Mahjong Panic! 2 - Kokushi Musou (FourNine)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Waku Waku Mahjong Panic! 2 - Kokushi Musou/Waku Waku Mahjong Panic! 2 - Kokushi Musou [HD]/Waku Waku Mahjong Panic! 2 - Kokushi Musou.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

FourNine's N.A.V.A.L system: `NAVAL.EXE` runs the scenario player `DIANA.EXE` and the mahjong programs `SONNET.EXE` and `TYPHON.EXE`.  The scripts (`*.DSD`) are operations a word each, parsed by the interpreter's own table; a string is drawn by an operation pointing at it.  The patcher lays a changed script's strings out again in the room the Japanese strings leave and after it (the code stays where it is).  The files are in the six `0Dnn.DAT` archives (a directory at the end, XOR 9999h; every file scrambled, a byte one more or less); the patcher writes the changed files into their archives again (a file split into parts gets its parts beside it).  A script holds 4650h bytes; `M2_SUB.DSD` is read after it (at 4650h, 3E80h bytes) and called by the scripts: its strings that do not fit it go to a pool kept at the top of every calling script's room.  A script past its room is split into copies of itself (`NAMEB.DSD`...), each entered at one operation (through a jump at its start; the operations under the jump copied into the free room) and keeping the strings its part of the code draws; the code going on to another part's entry goes to that file.  The mahjong opponents' files (`2JC*.DAT`, `FC4*.DAT`) are written anew with their table of lines (entries with the same line sharing it).  `pc98tl/diana.py` documents the format, `pc98tl/diana_tl.py` the English.  Unchanged files rebuild byte for byte.

* The three programs share one text routine; the patch makes it draw ASCII as half-width letters (NEC's half-width row), a byte and a cell each.  The programs are plain MZ programs, written as they were with the routine changed.
* The patched game folder has `MTL_NOTE.TXT`, the machine-translation notice.
* The menus are chosen with the mouse.

## Script

6185 strings: 17 DOS messages, 217 menus, 211 program and table strings, 4969 messages, 30 opponents' names, 741 mahjong opponents' lines.

Translation and the content classification (♥) are done by the translation model; 0 of 6185 strings have English so far.

## Limits

* Messages (`m` ids, a page each; `max_cells` the letters a line holds, the note gives the lines): any length.  The patcher breaks the English between words and starts a new page (a key, the window cleared) when the window is full; a message opening with a speaker's label (`【 ... 】` or `{L}`) has its later lines indented by the label's width.  In a scrolling window (the prologue) each message ends with a new line.  `\n` forces a new line.
* Menus (`i` ids): one item a line, `\n` between them as in the Japanese; a line past `max_cells` letters is cut and reported.
* Opponents' lines (`q` ids): broken between words at `max_cells` letters; an opponent's file past the programs' buffer (2JC*: 4096 bytes, FC4*: 2048 bytes) is refused.
* Names, program and table strings (`n`, `l` ids): in place, `max_cells` bytes (a letter a byte, a full-width character two), padded with spaces; past it cut and reported.  Blanks in the Japanese where the program draws an item's name over them stay blanks.
* DOS messages (`t` ids): in place, plain text; the program writes digits over the `00`s.
* Strings drawn one after another going on from a mark (`{M}` at the end: the game's typewriter texts, a character a string, as in the character cards): each goes on from the column and line the one before left; the English can be written in the first and the others left as `{M}` alone (nothing drawn).
* Tokens: keep them where the Japanese has them.  `{N}` the player's name, `{L}` the player's label, `{K}` a key, `{W}` a key and the window cleared, `{M}` a mark the next text goes on from; `{1Dnn}` `{1Enn}` colours, `{1Fnn}` the style, `{06nn}` a face, `{08nn}` a sound, `{10nn}` a pause; `{85xx}`/`{EBxx}` the font's half-width and own characters.
* English is ASCII; another character full-width when Shift-JIS has it, else `?`.

## Not handled

* Text drawn into the pictures (the archives' pictures: the title, the buttons, the panels).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (SIKI2.BAT: NAVAL.EXE, DIANA.EXE; the scripts in the rewritten archives): the sound menu, the title menu | OK: the items in filler half-width, the menus' rows in place |
| New game: the prologue (M0_00.DSD) in the message window, clicked through | OK: the filler broken between words at the window's edge, inside its frame, a new page when it is full |
| The character cards (M0_00.DSD: a string a character, each going on from the mark the one before left) | OK: the chained filler going on along the line, broken at the card's edge, a new page (a click) when the card is full; the name line cut at its room (reported) |
| Clicked on past the cards into the first room scene (M1_00.DSD) | OK: the speaker's name and the messages' filler inside the scene's message box, a new page when it is full |

Not reached in this test: a mahjong match (SONNET.EXE, TYPHON.EXE), the save and load screens, the endings.
