# Be-Yond (Silky's)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Be-Yond/Be-Yond [FD]/Be-Yond (Disk A).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Silky's (Elf's) **General Message system-1** (`SL.EXE`): 245 `*.MES` scripts with text, in the archives `DISKA`, `DISKB`, `DISKC`, `DISKD`, `DISKE`, `DISKF`, `DISKG` (one per floppy), each compressed; `pc98tl/silky.py` documents the archive, the compression and the bytecode, and `pc98tl/silky_tl.py` the English.  Every script tokenizes from its bytecode's start to its end, every address in it lands on a statement, and each rebuilds byte for byte.

The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image the way its own installer does (every disk's files in `BIYO/`, started with `game`; one disk's `DISKNO` kept); the base image is the collection's `Naomi - Bishoujo-tachi no Yakata/Naomi - Bishoujo-tachi no Yakata [HD]/Naomi - Bishoujo-tachi no Yakata.hdi` with its own game removed.

* The scripts hold addresses (jumps, loops, cases, calls), so a rebuilt script has them moved with its statements.
* English is a text statement in the engine's mode 2: single-byte letters, drawn half-width (8x16) by the engine itself, which the game uses for its half-width katakana sound effects; the program's drawing is not changed.
* Lines are wrapped between words to the text window the script set (46h; the message box is columns 17-62, 46 letters), with the engine's new line (04); the engine starts a new page by itself when a line would pass the window's bottom.
* A changed script is compressed again and its archive laid out anew.

## Script

23869 strings: 7 program strings, 23776 messages, 86 string variable values.

Translation and the content classification (♥) are done by the translation model; 0 of 23869 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's room (below); `\n` starts a new line. `max_cells` is a line's width in its window (letters); longer text wraps between words and pages.  A message that ends with a new line in the Japanese (a speaker's tag) should end with one too.  Letters only: the engine draws ASCII and half-width katakana in this mode, so anything else (full-width characters, accented letters) is written as `?`.
* `{N}` is where the script prints a string variable (4Bh: the hero's name, from the name entry): keep it in the English, in order; the patcher keeps 12 columns for it.
* A script is loaded at SS:0000 and the system library (`SYSTEM.MLL`) after it, at SS:7918h (read off `SL.EXE`): a script with its English may take that many bytes.  Each English letter is one byte, a Japanese character one or two, so the longest scripts must keep their English about as long in bytes as the Japanese; a build whose script outgrows its room is refused and names the script and its strings.
* String variable values (`v` ids: names and menu labels the script keeps in a variable): `max_cells` letters (a string variable's 32-byte slot), an even number of them (a space is added); longer ones are cut and reported.
* Program strings (`e` ids: `SL.EXE`, `MUSIC.COM`): `max_cells` x 2 letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Hard-disk layout boots (the seven disks' files in BIYO, started with GAME.BAT) | OK |
| The display menu and the title texts | OK: half-width filler, the menu's highlight on its items |
| The icon menu (NEW GAME, LOAD, MES, EXIT) | OK: its label (a string variable) as half-width filler, centred |
| The opening narration | OK: half-width filler wrapped between words in the bottom window, a key going on |
| The first dialogue scene (speaker tags, the bridge) | OK: each speaker's tag on its own line, the message wrapped between words below it, longer ones paged by the engine |
| The name entry, the program's error messages | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
