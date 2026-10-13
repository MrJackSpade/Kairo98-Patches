# Cal (Birdy Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Cal/Cal [FD]/Cal (Disk A).hdm` and its disk B (sha256 of disk A in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Birdy Soft's own disk system, ADOS (`pc98tl/ados.py`): files by number, no names.  The kernel (file 2) draws its characters through the kanji ROM; the game's program (file 253, loaded at segment 1000h) runs the scripts, files 10h and up, a bytecode with its text in Shift-JIS lines, written to the text layer.  `pc98tl/cal.py` documents the format, `pc98tl/cal_tl.py` the English.  A build with no English leaves both disks as they are.

* English is written one byte a letter, in byte values the script's text never uses.  The program is given a helper (where its script buffer started; the buffer moved up) that reads such a byte as one character and writes it as one half-width cell of the text layer; the kernel's character drawing is made to call the same helper, which draws two letters in one 16-dot cell (menus, choices, the name prompt, the program's strings, from the BIOS's 8x16 font).
* The scripts are written to disk B, where there is room, and the program reads them there.  A script longer than the moved buffer (23 sectors) is split where nothing is open, its rest a script of its own the first part goes to.
* A message longer than the window's 4 rows is ended and continued after a click.

## Script

2994 strings: 391 choice options, 2529 messages, 17 speaker names, 56 program strings, 1 the system's disk prompt.

Translation and the content classification (♥) are done by the translation model; 0 of 2994 strings have English so far.

## Limits

* Messages (`m` ids): any length.  Broken between words at the window's 70 half-width letters (54 after a speaker's name, which indents the text), `\n` a new line, paged after 4 rows.  `{c0}`-`{c7}` are colours and `{A}`-`{Z}` names the game puts in (the player's, a speaker's): keep them.
* Choice options (`c` ids): one line, up to 78 letters.
* Speaker names (`n` ids): up to 16 letters.
* Program strings (`p` ids) and the disk prompt (`k`): written in place, `max_cells` letters (two to a full-width cell).  In the prompt `{1}` and `{2}` are the disk's and the drive's letters: up to 10 letters before `{1}`, 18 between, 18 after.
* English is ASCII letters, digits, space and `.,!?'"-:;()&/%*+`; anything else is written as `?`.
* Disk B's free room holds the scripts' English: a build that does not fit is refused.
* The disks have no file names (ADOS), so the image carries no MTL_NOTE.TXT; the machine-translation notice is this file and the patch's name.

## Not handled

* Text drawn into the pictures.
* The name-entry grid's characters (they are what the player picks a name from).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from both floppies (disk A, disk B): the title menu | OK: its three items in filler, two half-width letters a cell (the kernel's drawing through the helper) |
| Start: the name entry screen, END clicked | OK: the prompt in filler; the grid as in the game |
| The first scene: clicks through its messages, a choice picked twice | OK: the messages in filler in the text window, half-width, broken between words; the choice menu's four options in filler; each pick's reply in filler, wrapped onto a second line |

Not reached in this test: saving and loading, the music test, the credits, the chapters past the first scene, the disk prompt (both disks are in their drives).
