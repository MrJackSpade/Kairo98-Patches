# Chuushaki - Hirasawa Nurse School (Aypio)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Chuushaki - Hirasawa Nurse School/Chuushaki - Hirasawa Nurse School [HD]/Chuushaki - Hirasawa Nurse School.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-11-06 (`research/clearance.json`).

## Engine

Aypio's UK2 engine (`CHUSYA\UK2.EXE`, run by `CHUSYA.BAT` under its sound driver NAX.COM) on the hard disk.  The scripts are the `.MES` files in its folder (installed from the floppies' LZH archives): compiled commands of two letters (and a few of one byte) whose arguments are typed values, expressions and conditions, with addresses (gotos, calls, the ifs' and loops' ends) as words.  `pc98tl/aypio.py` documents the formats, `pc98tl/aypio_tl.py` the English.  A build with no English leaves the disk as it is.

* The scripts are walked command by command (UK2.EXE's own reading of each command's arguments) and written again with their texts at any length, every address moved with what it points at; each changed script is written again.  This build's commands are Sex 2's and one more (`A7`, a value, read off its scripts): its grammar is picked by the program's own table of its commands' names.
* Text is the program's own code: two-byte Shift-JIS and single bytes standing for the characters of its table.  Its command `\k` makes it draw bytes as themselves, ASCII half-width: the English is written in `\k` (a name or a word put in, and a page's `%s`, go back to `\K`), so the program needs no patch.
* The program breaks a line at the window's edge by itself and its message window shows four rows (a speaker's and three); the patcher breaks the English between words at 64 letters and puts a longer message's rest in more messages, each shown by the call after the message.
* Pages and formatted texts go through a C format (`%d`, `%s`.. are values' places, shown as they are).
* A script runs on top of the ones that called it, in a room of 35,000 bytes: when the deepest chain with its English is longer, the room (UK2.EXE's allocation and its check) is grown to fit, a kilobyte at a time, and `UK2.CFG`'s `MIN_MEM` (the memory asked for without EMS) by as much.
* UK2.EXE's messages, the sound driver's (NAX.COM) DOS messages and the lines `INSTALL.BAT` (the floppies' copy to a hard disk) shows in place.
* `MTL_NOTE.TXT` is put in the game's folder (`CHUSYA`).

## Script

3450 strings: 14 installer lines, 145 menu choices, 3230 messages, 2 names, 5 pages, 30 program messages, 24 other texts.

Translation and the content classification (♥) are done by the translation model; 0 of 3450 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 64 letters, 3 lines a window under a speaker (4 without one), the rest in more windows; `\n` a new line.  `{N1}`.. a name and `{S1}`.. a word the message puts in: keep each where it belongs (they count 8 letters).  `{C7}` a colour and `{W100}` a wait are kept.
* Names (`n` ids) and words put in (`w` ids): up to 16 letters (their slots hold 20 bytes); longer is cut and reported by string id.
* Pages (`p` ids): broken between words at 64 (48 in window 1) letters; `\n` a new line; `%d`, `%s`.. are where a value goes (a number, a name): keep each, in order (a different set is reported by string id).
* Menu choices (`c` ids): one line, `max_cells` letters (the box keeps the Japanese width).
* Other texts (`t` ids): one line.
* Installer lines (`b` ids): one line, up to `max_cells` letters; longer is reported.
* Program messages (`e` ids): in place, `max_cells` letters; longer is cut and reported.
* A script runs on top of the ones that called it: the deepest chain (with its English) may grow the room to 65,520 bytes, one script stays within 60,000; a build past either is refused and names the scripts.
* English is ASCII; other characters are written as `?` (curly quotes, dashes, `…` and the brackets are made ASCII); a backslash (the commands' mark) as `/`.

## Not handled

* Text drawn into the pictures (the title).
* The name entry's characters (the kana the player picks a name from) and the default names' pieces: the name stays as the player enters it.
* NAX.COM's help screens (shown only when it is run with its options by hand).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the filler build (the installed hard-disk game): the opening demo | OK: its pictures as they are (their text is drawn into them) |
| Enter past the opening: the first scene's messages (clicks) | OK: each message in filler, half-width, broken between words within the window, a long one over two lines |

Not reached in this test: the menus and choices, the quiz, the endings and the CG mode, so they are not seen on screen.
