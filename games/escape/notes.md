# Escape! (May-Be Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Escape!/Escape! [HD]/Escape!.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

May-Be Soft's FAS engine (`ESCAPE\FAS.EXE`, Borland C++ 1993, run by `ES.BAT`) under MS-DOS on the hard disk.  The scenes' scripts are FSX files in `ES_FSXP.DAT`, the H scenes' HSX files in `ES_HSXP.DAT` (packs: a directory, then the files): events, each a plain bytecode head that names message streams in its code (stored XOR D6h) by their place.  `pc98tl/fas.py` documents the formats, `pc98tl/fas_tl.py` the English.  A build with no English leaves the disk as it is.

* The messages are written again at any length: the events' code is rebuilt, the heads' code places, the events' lengths and places moved.
* English half-width: the message routine's character fetch calls a helper that takes a byte 20h-7Eh as a character of one byte (drawn by the program's text routine, half-width on the text screen), and its column step one that steps one column for it (a segment put in before the data segment).
* The patcher breaks the English between words at 47 columns (the program breaks a line itself at 48), the lines after the first at the speaker's indent, and waits for a key and starts a new window after five lines; an English name is padded to the indent.
* FAS.EXE's own text (the title and in-game menus, the item names, the save and load messages, the opening's lines) in place.
* `MTL_NOTE.TXT` is put in the game's folder (`ESCAPE`).

## Script

1675 strings: 1575 messages, 37 speaker names, 63 program texts.

Translation and the content classification (♥) are done by the translation model; 0 of 1675 strings have English so far.

## Limits

* Messages (`m`): any length, broken between words and paged by the patcher; `\n` a new line; keep each `{K}` (a key wait).  A script with its English must stay within 32,768 bytes: a build over it is refused with the script's name.
* Speaker names (`n`): up to `max_cells` letters (the indent of the lines under them, usually 10), brackets included; longer is reported by string id.
* Program texts (`e`): in place, `max_cells` letters; longer is cut and reported by string id.  Keep `_w`, `_s` and `%d`; some are pieces the program puts together (a menu's name and the rest of its prompt).
* English uses ASCII; other characters are written as `?` (curly quotes, dashes, `…` and the name brackets `【】` are made ASCII).

## Not handled

* Text drawn into the pictures (the title).
* The `.DOC` files in the game's folder (the developers' notes and the questionnaire), read outside the game.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (ES.BAT, FAS.EXE): the opening's lines (FAS.EXE's own text) | OK: the lines in filler, half-width, in place (cut at the Japanese room) |
| The title menu | OK: every choice in filler, half-width, in place |
| Game start: the first scene's speeches (MAP1A's messages, about 10 keys) | OK: each speaker's name and message in filler, half-width; broken between words at 47 columns, the later lines under the speaker's indent; the window's key mark after each message |
| A test build with a nine-line English message and an English name: the first message | OK: five lines, a key, the window cleared, the other four at the indent; the name padded to the indent, the next message beside it |

Not reached in this test: the in-game menu (the right button opened nothing at that point), the H scenes (ES_HSXP.DAT, the same message code), saving and loading, the endings.
