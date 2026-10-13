# Waku Waku Mahjong Panic! - Shikigami Denshou (FourNine)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Waku Waku Mahjong Panic! - Shikigami Denshou/Waku Waku Mahjong Panic! - Shikigami Denshou [HD]/Waku Waku Mahjong Panic! - Shikigami Denshou.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

FourNine's N.A.V.A.L system: `NAVAL.EXE` runs the scenario player `DIANA.EXE` and the mahjong programs `SONNET.EXE` and `TYPHON.EXE`.  The scenario is `SNR/*.DSD` scripts (some packed, "eLZ0"): operations a word each, parsed by the interpreter's own table; a string is drawn by an operation pointing at it.  The patcher lays a changed script's strings out again in the room the Japanese strings leave and after it (the code stays where it is), and writes the script unpacked (the game's resident expander does not read every packed stream as the program would).  A script past DIANA's buffer (4268h bytes) is split into copies of itself (`NAMEB.DSD`...), each entered at one operation (through a jump at its start) and keeping the strings its part of the code draws; the code going on to another part's entry goes to that file.  The mahjong opponents' lines (`DAT/2JC*.DAT`, `DAT/FC4*.DAT`) are written anew with their table.  `pc98tl/diana.py` documents the format, `pc98tl/diana_tl.py` the English.  Unchanged files rebuild byte for byte.

* The three programs share one text routine; the patch makes it draw ASCII as half-width letters (NEC's half-width row), a byte and a cell each.  The programs are written unpacked (they were LZEXE), asking for no more memory than before.
* The menus are chosen with the mouse.

## Script

4247 strings: 21 DOS messages, 257 menus, 218 program and table strings, 3372 messages, 26 opponents' names, 353 mahjong opponents' lines.

Translation and the content classification (♥) are done by the translation model; 0 of 4247 strings have English so far.

## Limits

* Messages (`m` ids, a page each; `max_cells` the letters a line holds, the note gives the lines): any length.  The patcher breaks the English between words and starts a new page (a key, the window cleared) when the window is full; a message opening with a speaker's label (`【 ... 】` or `{L}`) has its later lines indented by the label's width.  In a scrolling window (the prologue) each message ends with a new line.  `\n` forces a new line.
* Menus (`i` ids): one item a line, `\n` between them as in the Japanese; a line past `max_cells` letters is cut and reported.
* Opponents' lines (`q` ids): broken between words at `max_cells` letters; an opponent's file past the programs' buffer (1250 bytes) is refused.
* Names, program and table strings (`n`, `l` ids): in place, `max_cells` bytes (a letter a byte, a full-width character two), padded with spaces; past it cut and reported.  Blanks in the Japanese where the program draws an item's name over them stay blanks.
* DOS messages (`t` ids): in place, plain text; the program writes digits over the `00`s.
* Tokens: keep them where the Japanese has them.  `{N}` the player's name, `{L}` the player's label, `{K}` a key, `{W}` a key and the window cleared, `{M}` a mark the next text goes on from; `{1Dnn}` `{1Enn}` colours, `{1Fnn}` the style, `{06nn}` a face, `{08nn}` a sound, `{10nn}` a pause; `{85xx}`/`{EBxx}` the font's half-width and own characters.
* English is ASCII; another character full-width when Shift-JIS has it, else `?`.

## Not handled

* Text drawn into the pictures (`GRP/*.EFD`: the title, the buttons, the panels).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (SIKI.BAT: NAVAL.EXE, DIANA.EXE): the sound menu, the title menu | OK: the items and the notes in filler half-width, the menus' rows in place |
| New game: the prologue (BEGINF.DSD, a scrolling window) | OK: filler half-width, each string from a new line; the scroll looks as the Japanese's does |
| The first scene (SS0.DSD, split into SS0.DSD and SS0B.DSD: its first part; MADV00.DSD), Enter after each page | OK: the speakers' labels, the messages' filler broken between words with later lines indented by the label, a new page when the window is full |
| The Panel Attack character select (MP4SEL.DSD), clicked through | OK: the profiles' filler in the box, a click going on to the next |

Not reached in this test: a mahjong match (SONNET.EXE, TYPHON.EXE: the mouse menus did not take the test's inputs reliably).  The two programs' text routine is patched the same way as DIANA's (the same routine, found by its bytes).
