# Kuro no Danshou - The Literary Fragment (Abogado Powers)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Kuro no Danshou - The Literary Fragment/Kuro no Danshou - The Literary Fragment [HD]/Kuro no Danshou - The Literary Fragment.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`KURODAN\GAME.EXE` (Borland C, large model) with its scenes in `SCENE.SCN`, `ASCENE.SCN`, `CSCENE.SCN` (XORed with AAh, indexed by `SCNDAT.TBL`).  A scene block is a header (menu records, a table of places in the script) and a script of `!` commands and Shift-JIS text; labels outside quotes are the menus' objects and verbs, the text between quotes their replies.  `pc98tl/kuro.py` documents the format, `pc98tl/kuro_tl.py` the English.  A build with no English leaves the files as they are.

* English at any length in the scenes: each block is written again with every place in its table moved with the text it points at, the scene files and `SCNDAT.TBL` rewritten.  GAME.EXE draws ASCII half-width itself and pages its message window.
* The program's own strings (the opening, the screen-mode menu, disk prompts, error messages): its text renderer, puts, printf and sprintf jump to a helper in a segment of its own put before the data segment, which points a string with English at the English kept there.
* Objects' names (the first piece of a menu label) are matched by string with the region names stored in the pictures and are never shown: they are kept in Japanese.  The title scene's menu lies under the title picture's English buttons and is kept as it is.

## Script

4228 strings: 44 captions, 97 choice options, 12 menu verbs, 4031 scene messages, 44 program strings.

Translation and the content classification (♥) are done by the translation model; 0 of 4228 strings have English so far.

## Limits

* Scene messages (`m` ids): any length.  The patcher breaks the English between words at 66 letters (the window takes 67) and the game pages after 4 rows; `{r}` is a click and a new page, `\n` a new line.  `{C1}`.. are effects and are kept (a missing one is put at the end); `{R1}`.. are ruby readings (the half-width kana in the note), kept before the word they belong to or left out.
* Menu verbs (`u` ids): up to 20 letters (the game copies each into a 21-byte slot); longer is cut and reported.
* Choice options (`c` ids): one line each; a comma is written full-width (an ASCII comma would start another option).
* Captions (`n` ids): broken between words at `max_cells` letters a line, `{n}` a new line.
* Program strings (`e` ids): any length, broken between words at 64 letters; `{w}` and `{s}` as given.
* A scene block holds at most 64480 bytes (its places are 16-bit): a build over it is refused.
* English is ASCII.  `( ) [ ] !` are written full-width (the script reads them as commands), `"` as `'`, `_` and `~` as `-`, `|` and backslash as `/`; any other character as `?`.

## Not handled

* Text drawn into the pictures (the title buttons are English already).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (AUTOEXEC: KURO.BAT, GAME.EXE): the screen-mode menu, its first item clicked | OK: the menu's title and items in filler half-width (the program's strings through the helper); the title picture with its English buttons follows |
| Title: start, the opening | OK: the opening's lines in filler half-width, broken between words |
| The first scene: clicks through its messages, then a click on the picture's window | OK: the messages in filler in the message window, broken between words and paged by the game; the window's verb menu opens with its two verbs in filler |

Not reached in this test: picking a menu item (the test's mouse input does not pick one, in the original game too), choice menus, captions, the scenes past the first.
