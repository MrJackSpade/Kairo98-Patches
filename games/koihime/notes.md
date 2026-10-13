# Koihime - Mystic Princess (Silky's)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Koihime - Mystic Princess/Koihime - Mystic Princess [FD]/Koihime - Mystic Princess (Disk A).hdm` and the other disks beside it (sha256 of the first in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`IGS.EXE`, Silky's "Image Gaming System" (1995, by spinout; IGS-DOS on five floppies): the `*.DIA` scripts are a stack machine's code with their strings in a data part.  The patcher packs the English into the room the Japanese strings leave (moving the pushes of their addresses), and adds routines after the code; a script past its 32 KB segment is split into further files (`NAME_2.DIA`): its main routine's parts, or a looping routine's bodies (entered through a byte of the saved state, 700h), each file with the strings it uses.  IGS-DOS reads a file as one run of clusters, so every file written is one run.  `pc98tl/igs.py` documents the format, `pc98tl/igs_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws half-width letters itself: in its vertical windows (the message box at the right, the menus) turned on their sides, read downwards.  The message box is given six columns 18 dots apart instead of four 27 apart (the same box).
* The scripts' width routine counts a letter as one cell (it counted 0), so a menu is sized to its English items.
* The game is played with the keyboard or the mouse; in a vertical menu Left moves to the next item.

## Script

13054 strings: 357 menu items, 4 other strings the scripts draw, 12693 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 13054 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the letters a line holds; the note gives the lines): any length.  The message box holds 41 letters a column and six columns.  A scene's strings are drawn one after another until the script clears the window; the patcher breaks the English between words, and when the window is full starts a new page (a click, the window cleared), a message that no longer fits from a new page.  A message whose Japanese ends in a new line keeps it (the next string starts a new line).  `\n` forces a new line.
* Tokens: keep them.  `{N}` / `{M}` the hero's names; `{DF0}`... a number the program fills in; `{S0}` / `{S1}` the program's text style.  A reading over kanji shows as kanji《reading》 in the Japanese; English has none.
* Menu items (`i` ids): one column, 40 letters at most; past it reported.
* Other strings (`l` ids: a page's title, the name entry's captions): `max_cells` the Japanese's width; past it reported.
* English is ASCII; "$" and "%" (the program's codes) are written full-width; another character full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the title, the logo).
* The name-entry screen's grid of kana (a table the scripts index): a name entered there is kana.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from floppies A and B (IGS-DOS, IGS OP.DIA): the monitor menu, the title menu | OK: the items in filler half-width, turned on their sides in the vertical menus, the menus sized to them |
| The name prompt and the name-entry screen (START.DIA) | OK: the prompt's filler in the vertical box; the entry's captions in filler (past their room, as reported) |
| The prologue (OPEN.DIA), Enter after each message | OK: the speaker's label, the messages' filler in the box's six columns, broken between words, a new page after a click when the box is full |
| A test start of the first scene (START loading S11.DIA), S11.DIA split by force into three files by its routine's bodies; the command menus chosen with Left and Enter | OK: the commands' replies kept only in S11_2.DIA shown (m01302 on), the part's file entered at the body, the scene's opening not shown again |
