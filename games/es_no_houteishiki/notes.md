# Es no Houteishiki (Abogado Powers)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Es no Houteishiki/Es no Houteishiki [HD]/Es no Houteishiki.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`ES\ES98.EXE` (Borland C, large model) with its scenes in `SCENE.SCN` (XORed with AAh, indexed by `SCNDAT.TBL`).  A scene block is a header (menu records, a table of places in the script) and a script of `!` commands (and `#i( )`, `#l`, `#n` blocks) and Shift-JIS text; labels outside quotes are the menus' objects and verbs, the text between quotes their replies.  `pc98tl/kuro.py` documents the format, `pc98tl/kuro_tl.py` the English.  A build with no English leaves the files as they are.

* English at any length in the scenes: each block is written again with every place in its table moved with the text it points at, the scene files and `SCNDAT.TBL` rewritten.  ES98.EXE draws ASCII half-width itself and pages its message window.
* The program's own strings (menus, messages) in place: ES98.EXE copies them and reaches them through tables, so they keep their places.
* Objects' names (the first piece of a menu label) are matched by string with the region names stored in the pictures and are never shown: they are kept in Japanese.

## Script

3585 strings: 66 choice options, 3475 scene messages, 44 program strings.

Translation and the content classification (♥) are done by the translation model; 0 of 3585 strings have English so far.

## Limits

* Scene messages (`m` ids): any length.  The patcher breaks the English between words at 66 letters (the window takes 67) and the game pages after 4 rows; `{r}` is a click and a new page, `\n` a new line.  `{C1}`.. are effects and are kept (a missing one is put at the end); `{R1}`.. are ruby readings (the half-width kana in the note), kept before the word they belong to or left out.
* Menu verbs (`u` ids): up to 20 letters (the game copies each into a 21-byte slot); longer is cut and reported.
* Choice options (`c` ids): one line each; a comma is written full-width (an ASCII comma would start another option).
* Captions (`n` ids): broken between words at `max_cells` letters a line, `{n}` a new line.
* Program strings (`e` ids): in place, `max_cells` letters (longer is cut and reported by string id); `{w}` and `{s}` as given.
* A scene block holds at most 64480 bytes (its places are 16-bit): a build over it is refused.
* English is ASCII.  `( ) [ ] !` are written full-width (the script reads them as commands), `"` as `'`, `_` and `~` as `-`, `|` and backslash as `/`; any other character as `?`.

## Not handled

* Text drawn into the pictures (the title buttons are English already).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (ES.BAT, ES98.EXE): the palette choice (Analog), the title menu (Initial Start) | OK: both menus are the pictures' English, as in the original |
| The opening and the first scene's messages (SCENE.SCN, about 5 clicks) | OK: every message in filler, half-width, broken between words at 66 letters; three or four lines a page, the page mark after each, a click going on |

Not reached in this test: the menus of objects and verbs, the choices, the in-game option menus (ES98.EXE's own strings), the music mode, saving and loading.
