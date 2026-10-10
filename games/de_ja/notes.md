# De-Ja (Elf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `De-Ja/De-Ja [HD]/De-Ja.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's early AI engine (`AI.EXE`, EXEPACK'd), before AI5: the scripts (`*.MES` in `DEJA/`) are run a byte at a time, statements 99h-BFh with numbers, variables and blocks in braces, Shift-JIS text drawn where it stands, each script's own dictionary (codes C0h-EFh, defined by statement A4h, run in place).  Nothing in a script is an address.  `pc98tl/elfai.py` documents the format and the program patch, `pc98tl/elfai_tl.py` the English.  Unchanged scripts stay byte for byte as they are.

The patch works on the game's hard-disk release.

* A script may not grow much: it is loaded at DS:2000h under the animations' buffers (DS:8000h and up).  So the messages' English is kept in `NAME.ENG` next to each script, and the script draws it line by line through a statement the program did not use (BBh and the line's offset).  `AI.EXE` is unpacked and given a helper at the end of its code: the statement draws the line a byte to a half-width letter, as the program draws a string; loading a script loads its `.ENG` into a 64 KB segment past the program's memory, which it grows by as much.
* Lines are wrapped between words to the text window (followed through the script: `A7` sets it, 3 lines of 80 letters for the messages), starting where the text before leaves the cursor (after a speaker's tag), and a new page (a key, then the window cleared) begun when it is full.
* Menu items and speakers' tags are written as strings in the script; names (the defaults KPUT.COM, the name entry, starts from, and its prompts) full-width.

## Script

19129 strings: 437 menu items, 18624 messages, 5 names and prompts, 63 speaker tags.

Translation and the content classification (♥) are done by the translation model; 0 of 19129 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` 79): any length; wrapped and paged by the patcher.  `\n` starts a new line.  `{N24}`/`{N25}` stand for the hero's family/given name (keep them; each is counted as 12 letters).
* Menu items (`i` ids, `max_cells` 14): one line, past the box's edge beyond it (reported).
* Speakers' tags (`t` ids): one line; the message goes on after it on the same line.
* Names (`n` ids): written full-width; a name 6 letters at most (KPUT.COM's), a prompt its `max_cells`; past it cut and reported.
* English is ASCII (half-width); another character is written as `?` (`"` in a menu item or tag as `'`).  A script with its English may take 24 KB (less where it names a lower buffer), its `.ENG` 64 KB; a build past either is refused and names the script.

## Not handled

* Text drawn into the pictures and the name entry's character grid (KPUT.COM's own).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (DEJA.BAT: AI START.MES) | OK: the first menu's items in filler, half-width, in their boxes |
| New game: the name entry (KPUT.COM) | OK: its prompts in full-width filler, the default names six full-width letters; ESC takes them |
| The opening (OPEN.MES) | OK: speakers' tags in their colours, the filler after them wrapped between words to the window's 79 letters, 3 lines to a page, the next page after a key; the hero's name drawn where the script puts it |
| The first scene (the hero's room) | OK: the command menu's items in filler in their boxes |
