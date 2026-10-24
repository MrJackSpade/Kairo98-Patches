# Yumemizaka (U-Me Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Yumemizaka/Yumemizaka [HD]/Yumemizaka.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`YUMEMI.EXE`: the messages are in the `*.TXB` files, blocks of strings packed with LZSS ("FLZ0"); the scripts name a message by its block and number.  The patcher packs a changed block again and writes the program's own strings in place.  `pc98tl/flz.py` documents the format, `pc98tl/flz_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws ASCII half-width by itself and breaks a line at 58 half-width cells (mid-word); the patcher breaks the English between words with the program's new line.
* The program loads a block whole into one 64 KB segment.  When the English takes a block past it, every TXB file is written unpacked in a wide form (each message from a paragraph's start, its place counted in paragraphs) and the program is patched to read it: a loader of its own, put after its load image with the stack moved past it, reads the block into as many paragraphs as it takes, and the lookup takes the place in paragraphs.

## Script

4031 strings: 149 program strings, 3882 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 4031 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` 58, the window's width in half-width cells): five lines at most (the window's); the patcher breaks the English between words and cuts a message past five lines (reported).  `\n` forces a new line.  A block (a scene's messages) may take any length.
* Program strings (`l` ids, its menus and notices; `\n` a new line): in place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and reported.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures.
* The prologue that scrolls before the title (it is in none of the game's text files).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk: the prologue, the title, its first item (Enter through) | OK: the game starts; the prologue and the title are the program's pictures |
| The first chapter's card and the first scene's messages, Enter after each | OK: the chapter card (a program string, in place) in filler half-width; the messages in filler half-width, broken between words at 58 cells |
