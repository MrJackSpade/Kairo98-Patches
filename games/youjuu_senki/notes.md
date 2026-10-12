# Youjuu Senki - A.D. 2048 (D.O.)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Youjuu Senki - A.D. 2048/Youjuu Senki - A.D. 2048 [HD]/Youjuu Senki - A.D. 2048.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

D.O.'s `YJWAR.EXE`: the scenes' messages are `*.TXB` files and the animated scenes `*.SC` files in NCA archives (`SYSDATA.NCA`, `ANMSC.NCA`), their Shift-JIS with every bit inverted; the battle lines (`*.MSG`), the data pages (`DATA_*.TXT`) and the unit table (`UNIT.DAT`) are plain files.  `pc98tl/yjwar.py` documents the formats, `pc98tl/yjwar_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws ASCII half-width by itself and breaks a line at its window's edge (mid-word); the patcher breaks the English between words, filling each line's end with spaces.
* A message window holds four lines (a fifth is drawn over the screen); the patcher makes a longer text several messages, a click each.
* The program's strings and its unit table are replaced in place in the program.
* The game asks for DIP switch SW2-8 off (`game.json` `dipsw`).

## Script

1377 strings: 328 battle lines, 115 data pages' paragraphs, 174 program strings, 427 scene messages, 58 unit names, 59 profile lines, 216 animated scenes' messages.

Translation and the content classification (♥) are done by the translation model; 0 of 1377 strings have English so far.

## Limits

* Scene messages (`m` ids) and animated scenes' messages (`s` ids): any length, `max_cells` the window's width (70 half-width cells).  `\n` forces a new line.  The opening's pages are centred line by line.
* Profile lines (`p` ids): one line each at a fixed place, `max_cells` 36; past it reported.
* Battle lines (`b` ids): broken at the battle window's 28 cells; at most 78 bytes (the longest Japanese line), past it cut and reported.
* Data pages (`d` ids): a paragraph each, any length, broken at the page's 62 cells with the Japanese's indents.
* Unit names (`n` ids): at most 19 bytes (cut past it); `max_cells` 16, the panels' room, past it reported.
* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and reported.  Keep `%s`/`%d` marks.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (DIP SW2-8 off): the start menu; its second item | OK: the menu's program strings in filler half-width (in place); the game starts |
| The first scene's messages, a click each | OK: the messages in filler half-width, broken between words at the 70-cell window, a speaker's face beside them; a message past four lines goes on in a second (checked with a six-line test message) |
| The HQ menu, its information item, the data page about the beasts | OK: the menus' program strings in filler half-width; the data page's paragraphs in filler, broken at the page's width with their indents |
| The opening (start menu's first item), checked separately | OK: the opening's pages centred line by line in filler half-width |
| The animated scenes, the profiles and the battle lines | untested: not reached in these runs (the leave scenes need the soldiers' consent; no battle was played) |
