# Doki Doki Shutter Chance (Elf, on Cocktail Soft / Fairytale's engine)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Doki Doki Shutter Chance/Doki Doki Shutter Chance [FD]/Doki Doki Shutter Chance.hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

ides' Adv98V script engine (at the disk's root), on 4 floppies: 4 scripts with text (each game's `START.MES`: the main game's, and in its folders `JOSHI/`, `NURSE/`, `BUS/`) in its bytecode (`pc98tl/adv98v.py` documents it).  Every script tokenizes and rebuilds byte for byte.  No procedure holds text, so no procedure grows.

This is ADVH, the engine before Adv98V (`ADVH.EXE`, in most games run by `ADVSHELL.COM`): the same bytecode, but no ASCII string command, and every character drawn as a 16x16 glyph.  The patch adds half-width letters to the program (`pc98tl/advh.py`): each English letter is written as `85 xx` (xx its ASCII code), which the program draws from the BIOS's 8x16 font one column wide and steps the cursor one column on; a packed program is unpacked, patched and packed again with its own EXEPACK unpacker.  The disk-change command (wait for disk X in the floppy drive) goes straight on.  Messages page with the key wait `81 90`, which clears the box: a message longer than the box goes on after a key on a fresh page.

The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image (the main disk's files in `DOKI/`, with the scripts' drive letters taken off their file names, started as the floppy's boot does); the base image is the collection's `Naomi - Bishoujo-tachi no Yakata/Naomi - Bishoujo-tachi no Yakata [HD]/Naomi - Bishoujo-tachi no Yakata.hdi` with its own game removed.  The data collections are games of their own, each with its engine and start script, so each disk goes into its own folder: `DOKI/JOSHI/` (Doki Doki Shutter Chance (Data Shuu #1 - Joshikou) {ADVH START.MES}.hdm), `DOKI/NURSE/` (Doki Doki Shutter Chance (Data Shuu #2 - Nurse) {ADVH START.MES}.hdm), `DOKI/BUS/` (Doki Doki Shutter Chance (Data Shuu #3 - Bus Guide) {ADVH START.MES}.hdm).  The hard disk starts the main game; a collection is started from DOS with `cd \DOKI\FOLDER` and `ADVH START.MES`.  Their scripts' refs are `FOLDER/START.MES:n`, and a string the games share lists every game's refs.

## English display (`pc98tl/adv98v_tl.py`)

* English letters are written as `85 xx` in place of the Japanese text runs
  (see the engine note above); the scripts are rebuilt with them (no offset
  table refers into a script).
* The engine wraps at the text frame's right edge even inside a word, and
  does not scroll (a fourth line of a 3-line frame draws over the first).
  So messages are broken between words to the frame's width (`A6` gives it
  in half-width columns) and cut into pages of its line count; between
  pages goes a wait and the file's message-end procedure call, as between
  the original messages.
* Menu items and text in one-line frames keep their Japanese width.
* Pieces of text with only colour, speed, pause or fade commands between
  them are one string; the English replaces all of it, without those
  effects.
* Procedures are read for what they print: a name tag ends its line, a fixed text (an ellipsis) or a name shown from a variable (its Japanese width) moves along it, a line break moves down, and a frame or text reset starts a fresh page.  A message continues the page of the text before it, wrapped from where that left off, with room left for what is printed after it.
* The strings in the engine's programs are rewritten in place.

## Script

53 strings (42 messages, 11 program strings).

Translation and the content classification (♥) are done by the translation model; 0 of 53 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  Full-width characters can stay in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are written back as they are.
* This old build ends each message with a key wait (`81 90`) that clears the box, so pages are split with it (in a one-line box, a line at a time).
* A script runs from the engine's script buffer, which holds 10240 bytes (read off its memory): a file that would outgrow it with the English is refused and named, so keep the longest scripts' English about as long as the Japanese.
* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are cut and reported.
* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Hard-disk layout boots (main game in DOKI, ADVH started from AUTOEXEC.BAT) | OK |
| Opening lines before the title picture | OK: half-width filler, centred lines kept on the screen |
| Title picture, then the story pages in the middle box | OK: filler wrapped in the box, lines 11 dots apart as the engine's own, a click (right button) going on |
| The client's scene (portrait with the text column at its right) | OK: filler wrapped in the column; a long message pages with a key wait, the column cleared for the next page |
| A data collection (DOKI/JOSHI started in a test image) | OK: its opening, story pages and client scene as in the main game |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

This is Elf's 1989 build of ADVH, older than the Fairytale/Cocktail Soft ones: its `ADVH.EXE` is neither EXEPACK-packed nor wrapped, and is written back unpacked; it has no disk-change command, so the half-width helper is put after the end of its image (the end of the text loop's code segment) and the header's size grows with it; it draws its glyphs squeezed to ten rows (lines 11 dots apart), and the helper squeezes the letters the same way (`pc98tl/advh.py`).

The main disk is Elf's own boot disk: FAT with no BPB in its boot sector, read with the standard 2HD layout (`pc98tl/disk.py`); its `ELF1.SYS`/`ELF2.SYS` system is not installed (the hard disk's DOS runs the game).

Scripts are loaded at DS:D800h and run up to the code segment at 1200h, a 10240-byte buffer (`script_room`).

The startup script's procedure 1 clears the box and shows a scene picture; it is not taken as the message end (a procedure that loads a file never is), and pages are split with the key wait `81 90`.
