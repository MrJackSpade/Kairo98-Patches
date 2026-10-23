# Sex 2 (Aypio)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Sex 2/Sex 2 [HD]/Sex 2.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-23 (`research/clearance.json`).

## Engine

Aypio's UK2 engine (`SEX2\UK2.EXE`, run by `SEX2.BAT` after `SOUNDSEL.EXE`'s sound board menu, under the PMD/MMD sound drivers) on the hard disk.  The scripts are the `.MES` members of `DATALIB1-4.DLB` (a directory of names, places and sizes, then the members): compiled commands of two letters (and a few of one byte) whose arguments are typed values, expressions and conditions, with addresses (gotos, calls, the ifs' and loops' ends) as words.  `pc98tl/aypio.py` documents the formats, `pc98tl/aypio_tl.py` the English.  A build with no English leaves the disk as it is.

* The scripts are walked command by command (UK2.EXE's own reading of each command's arguments) and written again with their texts at any length, every address moved with what it points at; the archives are written again.  This build's commands differ from Sex's (some gone, some new, some reading other arguments): its grammar is picked by the program's own table of its commands' names.
* Text is the program's own code: two-byte Shift-JIS and single bytes standing for the characters of its table.  Its command `\k` makes it draw bytes as themselves, ASCII half-width: the English is written in `\k` (a name or a word put in, and a page's `%s`, go back to `\K`), so the program needs no patch.
* The program breaks a line at the window's edge by itself and its message window shows four rows (a speaker's and three); the patcher breaks the English between words at 48 letters and puts a longer message's rest in more messages, each shown by the call after the message.
* Pages and formatted texts go through a C format (`%d`, `%s`.. are values' places, shown as they are).
* A script runs on top of the ones that called it, in a room of 35,000 bytes: when the deepest chain with its English is longer, the room (UK2.EXE's allocation and its check) is grown to fit, a kilobyte at a time, and `UK2.CFG`'s `MIN_MEM` (the memory asked for without EMS) by as much.
* UK2.EXE's messages, `SOUNDSEL.EXE`'s menu and the lines `INSTALL.BAT` (the CD's copy to a hard disk) shows in place.
* `MTL_NOTE.TXT` is put in the game's folder (`SEX2`).

## Script

3920 strings: 10 installer lines, 43 menu choices, 4 formatted texts, 3732 messages, 2 names, 24 pages, 21 program messages, 84 other texts.

Translation and the content classification (♥) are done by the translation model; 0 of 3920 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 48 letters, 3 lines a window under a speaker (4 without one), the rest in more windows; `\n` a new line.  `{N1}`.. a name and `{S1}`.. a word the message puts in: keep each where it belongs (they count 8 letters).  `{C7}` a colour and `{W100}` a wait are kept.
* Names (`n` ids) and words put in (`w` ids): up to 16 letters (their slots hold 20 bytes); longer is cut and reported by string id.
* Pages (`p` ids): broken between words at 48 (64 in the wider windows) letters; `\n` a new line; `%d`, `%s`.. are where a value goes (a number, a name): keep each, in order (a different set is reported by string id).
* Menu choices (`c` ids): one line, `max_cells` letters (the box keeps the Japanese width).
* Other texts (`t` ids): one line.
* Formatted texts (`f` ids): broken between words at 48 letters; `\n` a new line; keep each `%d`, `%3d`.. in order.
* Installer lines (`b` ids): one line, up to `max_cells` letters; longer is reported.
* Program messages (`e` ids): in place, `max_cells` letters; longer is cut and reported.
* A script runs on top of the ones that called it: the deepest chain (with its English) may grow the room to 65,520 bytes, one script stays within 60,000; a build past either is refused and names the scripts.
* English is ASCII; other characters are written as `?` (curly quotes, dashes, `…` and the brackets are made ASCII); a backslash (the commands' mark) as `/`.

## Not handled

* Text drawn into the pictures (the title).
* The name entry's characters (the kana the player picks a name from) and the default names' pieces: the name stays as the player enters it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Pseudo build boots (np21w, SEX2.BAT) | OK: SOUNDSEL.EXE's menu in filler, then the title |
| The name page (U2 in window 1) and its menu (W8) | OK: the page in filler broken between words at 48 letters, both names put in by its %s shown right; the choices in filler (the box keeps the Japanese width) |
| The first scene (pseudo, clicked through) | OK: the day's page with its %d filled; messages in filler broken between words at 48 letters, 4 rows a window, a longer one's rest in a second window |
| Scripts' room | OK: the stress build's deepest chain (main.mes > sex20.mes > sex21.mes > sex_sys.mes, 40,305 bytes) grew the room to 40,960 bytes and the game ran; all 53 patched scripts read back |
| Partly translated build | OK: SOUNDSEL.EXE's menu in English, the name page in English with the names in it, its choices in English |
| Unmodified build | OK: a build with no English is the source image byte for byte |

Past the first scene the boot test did not play; every script goes through the same rebuild.

The menus take the mouse only (the boot steps move it in small steps; a large jump is not seen).
