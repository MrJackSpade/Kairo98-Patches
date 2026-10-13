# Fermion (Silky's)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Fermion/Fermion [HD]/Fermion.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Silky's (Elf's) **General Message system-1** (`SIL.EXE`): 93 `*.MES` scripts with text, in the archives `DISKA`, `DISKB`, `DISKC`, `DISKD` (one per floppy), stored as they are; `pc98tl/silky.py` documents the archive, the compression and the bytecode, and `pc98tl/silky_tl.py` the English.  Every script tokenizes from its bytecode's start to its end, every address in it lands on a statement, and each rebuilds byte for byte.

The patch works on the game's hard-disk release (the game in `FERM/`).

* The scripts hold addresses (jumps, loops, cases, calls), so a rebuilt script has them moved with its statements.
* English is a text statement in the engine's mode 2: single-byte letters, drawn half-width (8x16) by the engine itself, which the game uses for its half-width katakana sound effects; the program's drawing is not changed.
* Lines are wrapped between words to the text window the script set (46h; the message box is columns 3-63, 61 letters, set by the system library and measured on screen), with the engine's new line (04); the engine starts a new page by itself when a line would pass the window's bottom.
* A changed script is stored as it is, like the game's own and its archive laid out anew.

## Script

12096 strings: 12089 messages, 7 string variable values.

Translation and the content classification (♥) are done by the translation model; 0 of 12096 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A message that ends with a new line in the Japanese (a speaker's tag) should end with one too.  Letters only: the engine draws ASCII and half-width katakana in this mode, so anything else (full-width characters, accented letters) is written as `?`.
* `{N}` is where the script prints a string variable (4Bh: the hero's name, from the name entry): keep it in the English, in order; the patcher keeps 12 columns for it.
* A script is loaded at SS:0000 and the system library (`SYSTEM.MLL`) after it, at SS:7918h (read off `SL.EXE`): a script with its English may take that many bytes.  Each English letter is one byte, a Japanese character one or two, so the longest scripts must keep their English about as long in bytes as the Japanese; a build whose script outgrows its room is refused and names the script and its strings.
* String variable values (`v` ids: names and menu labels the script keeps in a variable): `max_cells` letters (a string variable's 32-byte slot), an even number of them (a space is added); longer ones are cut and reported.
* Program strings (`e` ids: ``): `max_cells` x 2 letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release; the opening lines and the title | OK: boots; half-width filler |
| The prologue (the bottom message box) | OK: filler wrapped between words to the box's 61 columns, pages waiting for a key |
| Later scenes, menus, the endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

Fermion's SIL.EXE is the same General Message system-1 (Rev.95:06:30) as Be-Yond's SL.EXE; its archives DISKA-DISKD hold the members uncompressed. The message box is set inside the system library, so its columns (3-63) were measured on screen: game.json message_window.
