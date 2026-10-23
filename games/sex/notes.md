# Sex (Aypio)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Sex/Sex [HD]/Sex.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Aypio's UK2 engine (`SEX\UK2.EXE`, run by `SEX.BAT` under its sound driver NAX.COM) on the hard disk.  The scripts are the `.MES` members of `DATALIB1-4.DLB` (a directory of names, places and sizes, then the members): compiled commands of two letters (and a few of one byte) whose arguments are typed values, expressions and conditions, with addresses (gotos, calls, the ifs' and loops' ends) as words.  `pc98tl/aypio.py` documents the formats, `pc98tl/aypio_tl.py` the English.  A build with no English leaves the disk as it is.

* The scripts are walked command by command (UK2.EXE's own reading of each command's arguments) and written again with their texts at any length, every address moved with what it points at; the archives are written again.
* Text is the program's own code: two-byte Shift-JIS and single bytes standing for the characters of its table.  Its command `\k` makes it draw bytes as themselves, ASCII half-width: the English is written in `\k` (a name or a word put in goes back to `\K`), so the program needs no patch.
* The program breaks a line at the window's edge by itself and its message window shows four rows (a speaker's and three); the patcher breaks the English between words at 64 letters and puts a longer message's rest in more messages, each shown by the call after the message.
* UK2.EXE's messages, the sound driver's (NAX.COM) and the floppy launcher's (AYPIO.COM) DOS messages in place.
* `MTL_NOTE.TXT` is put in the game's folder (`SEX`).

## Script

3783 strings: 134 menu choices, 11 words put in, 3492 messages, 4 names, 111 pages, 24 program messages, 7 other texts.

Translation and the content classification (♥) are done by the translation model; 0 of 3783 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 64 letters, 3 lines a window under a speaker (4 without one), the rest in more windows; `\n` a new line.  `{N1}`.. a name and `{S1}`.. a word the message puts in: keep each where it belongs (they count 8 letters).  `{C7}` a colour and `{W100}` a wait are kept.
* Names (`n` ids) and words put in (`w` ids): up to 16 letters (their slots hold 20 bytes); longer is cut and reported by string id.
* Pages (`p` ids): broken between words at 64 letters; `\n` a new line.
* Menu choices (`c` ids): one line, `max_cells` letters (the box keeps the Japanese width).
* Program messages (`e` ids): in place, `max_cells` letters; longer is cut and reported.
* A script runs on top of the ones that called it: the deepest chain (start.mes, sex.mes, a scene, what it calls) must stay within 35,000 bytes, one script within 60,000; a build past either is refused and names the scripts.
* English is ASCII; other characters are written as `?` (curly quotes, dashes, `…` and the brackets are made ASCII); a backslash (the commands' mark) as `/`.

## Not handled

* Text drawn into the pictures (the title).
* The name entry's characters (the kana the player picks a name from) and the default names' pieces: the name stays as the player enters it.
* NAX.COM's help screens (shown only when it is run with its options by hand).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (SEX.BAT: NAX.COM, UK2.EXE): the opening's pages (U2, about 4 keys) | OK: each page in filler, half-width, broken between words at 64 letters, four rows a page |
| The title: its menu (W8) and the message under it | OK: every choice in filler, half-width (the box keeps the Japanese width, a longer choice runs on below it); the message in filler, broken between words |
| Every patched script read again (all 58 .MES files in the four archives) | OK: every command and address read back; each message too long for one window made a message and the call after it again |

Not reached in this test: the story's scenes (the title menu takes no choice from the emulator's keys or mouse here, in the original as well), so a message paged over windows in a scene, the names and words put in, the name entry and saving are not seen on screen.
