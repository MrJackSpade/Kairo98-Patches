# Dies Irae (FamilySoft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Dies Irae/Dies Irae (FD version) [HD]/Dies Irae (FD version).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

FamilySoft's own engine (`DIESIRAE\DIES01.EXE`, started by `DIES98.COM` after the opening `D_OP98.EXE`) under MS-DOS on the hard disk.  The scenario is text scripts (`*.CEN`, every byte stored one less): commands, codes and Shift-JIS text read a byte at a time, the menus a line a choice.  `pc98tl/dies.py` documents it, `pc98tl/dies_tl.py` the English.  A build with no English leaves the disk as it is.

* English two letters a character, as two-byte codes of printable ASCII bytes the scripts' reader takes as characters; the glyph routine is made to jump, before its CG ROM read, to a helper in a segment put in before the data segment, which draws such a code from two 8x16 BIOS glyphs.
* The patcher breaks the English between words at the window's 24 characters (48 letters) with the script's own new line; the program pages a full window (three lines) with its own wait.
* The script buffer is made larger (32 KB, from 17000 bytes): the program reads a scene's script and the shared `000.CEN` into it together.
* The programs' DOS messages (disk errors, memory, the goodbye) are written in place.
* `MTL_NOTE.TXT` is put in the game's folder (`DIESIRAE`).

## Script

7237 strings: 477 menu choices, 6753 messages, 7 program messages.

Translation and the content classification (♥) are done by the translation model; 0 of 7237 strings have English so far.

## Limits

* Messages (`m`): any length, broken between words at 48 letters and paged by the program; `\n` a new line.  Keep each `{Xn}` (a code of the script's: `{Fn}` a face, `{Cn}` a colour, `{Gn}` a picture, `{Wn}` a wait...) where it stands: a code the Japanese does not have is refused by string id.  A message runs on from the text before it when the script puts no break between them.
* Choices (`c`): one line in the menu's box, `max_cells` characters (20 letters); longer is cut and reported by string id.
* A scene's script, with its English and `000.CEN`'s, must fit the script buffer (32 KB): a build over it is refused with the script's name.
* Program messages (`e`): in place, `max_cells` letters; longer is cut and reported.
* English uses letters, digits and `.,'"!?-:;()`; anything else is written as `?`.

## Not handled

* Text drawn into the pictures (the title, the character select's names, the command buttons, the speakers' names under their faces).
* The setup tools (`SETUPFD.BAT`, which makes a boot floppy, and the `HDSTART.EXE` it runs), which the hard-disk image does not use.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk: the opening, Return, the character select; S (start) clicked | OK: the title and the character select as in the original (their text is in the pictures) |
| The first scene (the reception): the description and the talk with Marian, about 12 clicks | OK: every message in filler, half-width two letters a character, broken between words; a full window waits and goes on with the rest; the faces change between the lines |
| The menu of places at the scene's end | OK: its choices in filler in the menu's box (20 letters each); picking one moves to the next scene, whose messages are in filler |

Not reached in this test: the save, load and system menus (000.CEN), the battles, the other two heroes' stories, the endings.
