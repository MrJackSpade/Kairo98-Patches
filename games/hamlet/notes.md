# Hamlet (Panther Software)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Hamlet/Hamlet [HD]/Hamlet.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

Panther Software's own engine (`HAM.EXE`): the scenes (`*.P`, `*.CMN`, `START*.BIN`) are code overlays the engine reads into its overlay segment, their strings among their code, a message named by the `mov si` before the engine's message call; the program's own strings are in its data segment; the opening (`HOPEN.EXE`) has its text in its own data segment.  `pc98tl/panther.py` documents the formats and the program patches, `pc98tl/panther_tl.py` the English.  Unchanged files rebuild byte for byte.

The patch works on the game's hard-disk release (the game in `HAMLET/`).

* `HAM.EXE` gets a helper put in at the end of its code segment (the segments after it move up).  A byte from 20h to 7Fh is a half-width letter: drawn 8 dots wide from the BIOS 8x16 font, bold as the program's characters, two to a character's place; in the message window and the string routine (menus) alike.
* A scene's message longer than its own bytes is put at the scene's end and its `mov si` pointed at it; the overlay segment grows to the largest scene (up to 65535 bytes), the segments after it moving up.
* The program's messages and menu labels longer than their own bytes go in room put in after its data segment, their `mov si` / `mov bx` pointed at them.
* `HOPEN.EXE` gets the same half-width drawing in its character loops, its reveal and its string routine; its text is rebuilt in room put in after its data segment (story lines centred anew, the characters' names centred in their card).

## Script

2936 strings: 77 program strings, 2816 scene strings, 43 opening strings.

Translation and the content classification (♥) are done by the translation model; 0 of 2936 strings have English so far.

## Limits

* Scene messages (`m` ids, `max_cells` 45): any length.  The patcher wraps between words at 45 letters a line; the engine pages every 5 lines with a key wait.  `\n` starts a new line.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.
* Scene strings no `mov si` names (58, their `note` says so: the ending's credits and a few lines): each within its own bytes (`max_cells`); longer ones are cut and reported.
* A scene may take 65535 bytes with its English (the engine's read); a build past it is refused and names the scene.
* Program strings (`e` ids): messages (`max_cells` 45) as the scenes' are; menu labels one line each, `max_cells` the Japanese's room (past it reported, the box does not grow); the weapons' names and the disk prompts within their own bytes (longer ones are cut and reported).  The data segment has 39152 bytes of room for the moved ones; a build past it is refused.
* Opening strings (`o` ids): one line each, `max_cells` letters (80 for the story and glossary lines, the card's columns for the characters' names, the Japanese's room for the mode labels, past which is reported); longer lines are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, the pictures; the opening's map and mecha screens are English already).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (PANTHER.EXE's logo, then HAM.EXE) | OK: the logo, then the title menu |
| Title menu (HAM.EXE's string routine) | OK: the filler labels drawn half-width, bold, in the menu's colours; past the box where longer than the Japanese (reported as overruns) |
| New game: the first scene's messages (START.BIN, message window) | OK: filler wrapped between words at 45 letters, 5 lines a page, the key wait and the next page; the face beside it |
| Opening (HOPEN.EXE): glossary page | OK: each line typed out half-width at its place |
| Opening: the characters' cards | OK: each name centred in its card, moving with it, cut to the card's 38 columns |
| Opening: story pages (reveal and scroll) | OK: lines centred anew, cut at 80 letters (reported), revealed and scrolled as the Japanese |
| Opening: the mode labels (CRUISE / ASSAULT / COMBAT MODE) | not reached in the test |

Menu labels longer than the Japanese draw past their box, and what is drawn outside it stays on screen after the menu closes: keep them to their `max_cells`.
