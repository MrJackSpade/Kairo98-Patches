# Hiiragizaka no Kyuukan (U-Me Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Hiiragizaka no Kyuukan/Hiiragizaka no Kyuukan (FD version) [HD]/Hiiragizaka no Kyuukan (FD version).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`HIRAGI.EXE`: the messages are in the `*.TXB` files, blocks of strings packed with LZSS ("FLZ0"); the scripts name a message by its block and number.  The patcher packs a changed block again and writes the program's own strings in place.  `pc98tl/flz.py` documents the format, `pc98tl/flz_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws ASCII half-width by itself and breaks a line at 56 half-width cells (mid-word); the patcher breaks the English between words with the program's new line.
* The program loads a block whole into one 64 KB segment.  When the English takes a block past it, every TXB file is written unpacked in a wide form (each message from a paragraph's start, its place counted in paragraphs) and the program is patched to read it: a loader of its own, put after its load image with the stack moved past it, reads the block into as many paragraphs as it takes, and the lookup takes the place in paragraphs.

## Script

7658 strings: 59 program strings, 7599 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 7658 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` 56, the window's width in half-width cells): four lines at most (the window's); the patcher breaks the English between words and cuts a message past four lines (reported).  `\n` forces a new line.  A block (a scene's messages) may take any length.
* Program strings (`l` ids, its menus and notices; `\n` a new line): in place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and reported.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (HIRAGI.EXE): the U-Me logo, the title and its menu | OK: the menu's items in filler, half-width, in their box |
| The name window (the default name), its END clicked | OK: the default name in filler; the kana grid as it is |
| A new game: the day's card and the first messages, read from the wide TXB blocks | OK: the day card in filler; each message in filler, broken between words within the window's 56 cells and 4 rows; the scenes' pictures as they are |

Not reached in this test: the diary, the endings and the achievement screen, so they are not seen on screen.
