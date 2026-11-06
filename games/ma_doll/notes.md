# Ma Doll (FairyDust)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Ma Doll/Ma Doll [HD]/Ma Doll.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-11-06 (`research/clearance.json`).

## Engine

FairyDust's `MADOU\MDMAIN.EXE` (MS C, EXEPACK'd) on the hard disk.  The scripts (`STY_nn.SCR`) are 6-byte records (an op and two operands) and a text area of NUL-ended strings, XOR 7Fh, that the records name by place: the messages (ops ending 02), the choices (the second block's records) and the pictures' names (ops ending 09).  A text's bytes are Shift-JIS, half-width kana bytes for hiragana and ASCII bytes for full-width letters and some kanji (the program's table of one-byte characters), 02 and a byte a name the program keeps.  `pc98tl/madoll.py` documents the formats and the patch, `pc98tl/madoll_tl.py` the English.  A build with no English leaves the disk as it is.

* The table's entries for the ASCII bytes are made the letters themselves (an entry of a letter and 0 is drawn in one half-width cell, as the program already does for a few marks), so English is ASCII, a byte a letter; Japanese that stays is written with those characters spelled out in Shift-JIS.
* The messages outgrow the text area (the program loads it into 34512 bytes below its data), so each script's messages go into a file of their own, `STY_nn.MSG`, each from a paragraph's start, and a message's operand becomes its paragraph.  The script loader's call of its text reader is made a call of a helper that also reads the .MSG file into memory it asks DOS for once (the largest .MSG's size); the two message readers (the window's and the log's) take the message's segment from that memory and its paragraph.  The text area keeps only the choices and the pictures' names; the helpers sit at the end of its room.  The program is written back unpacked.
* The window breaks a line at 58 cells and scrolls up a line when its 4 lines are full; the patcher breaks the English between words at 58 letters.

## Script

7953 strings: 82 choices, 7803 messages, 53 names put in, 15 program strings.

Translation and the content classification (♥) are done by the translation model; 0 of 7953 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 58 letters, the window scrolling.  `
` a new line.  Keep `{N0}` (the hero's name), `{N1}`.. (the names and tags the program puts in, `n` ids) and `{01}`.
* The largest script's messages must fit the free memory the game leaves (about 84 KB); the patcher reports the largest `.MSG` file's size.
* Choices (`c` ids): one line, `max_cells` letters (the Japanese's width); longer ones are cut and reported.
* Names (`n` ids) and program strings (`e` ids): in place, `max_cells` letters (the Japanese's bytes); longer ones are cut and reported.  A name is drawn two bytes at a time, so an odd length is padded with a space.
* English is ASCII; `\` is written `/` (the program's escape), other characters as `?` (curly quotes, dashes and `…` are made ASCII).

## Not handled

* Text drawn into the pictures (the title, the frame's lettering).
* The name entry's tables of kana (picked by their place).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the filler build (the installed hard-disk game): the system menu and the name entry (the pointer moved onto them) | OK: the menu's items and the default name in filler, half-width, cut to their room as reported; the name entry's kana tables as they are |
| The opening (STY_OP) and the first scene's messages (clicks), read from the .MSG files | OK: each message in filler, half-width, broken between words, a long one over two lines; the names the program puts in in filler; the page mark |

Not reached in this test: the choices, the log, the CG and music modes and the endings, so they are not seen on screen.
