# Love Escalator (Umitsuki Seisakusho)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Love Escalator/Love Escalator [HD]/Love Escalator.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`EQAP32.EXE`, O. Tomioka's EQAP32 engine (a DOS/4GW program, Watcom C): the `*.EQA` scripts are bytecode in the `LOVE.EAR` archive, the text in them in the text layer's code (JIS less 2020h).  The patcher writes a changed script again (its jumps, calls and tables moved) and the archive anew.  A script past its 64 KB buffer is cut into further scripts (`NAME2.EQA`): a scene in parts going on with the script command (each with a copy of its shared routines), a hub of scenes (the endings) with its scenes in a further script reached through variable 10.  `pc98tl/le.py`, `pc98tl/ear.py` and `pc98tl/eqa.py` document the formats, `pc98tl/eqa_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws only full-width characters on the text layer.  The patched program also draws letter pairs, two ANK letters in one character's two cells (its cell writer extended in the code object's spare room); a cell is one half-width letter.
* The game is played with the keyboard or the mouse; the right button opens the program's menu.

## Script

14930 strings: 59 menu items, 14757 messages, 45 speakers' labels and the hero's name, 10 disk-error notices of the program's, 59 other strings put into slots.

Translation and the content classification (♥) are done by the translation model; 0 of 14930 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` the window's width in letters): any length.  The window is usually 60 cells by four lines (the help pages 74 by twelve); the patcher breaks the English between words, and when the window is full ends the message there and goes on in a further one after the script's click.  `\n` forces a new line.
* Tokens: keep them.  `{X9n}`-`{XCn}` insert a slot's string (`{X90}` the hero's family name, `{X92}` his given name, `{X94}` his label, `{X96}` on the speakers' labels; at a message's start the speaker); `{X82}` / `{X83}` draw slowly / at once (around a label); `{X84}` clears the window; `{X80}` waits for a click.
* Menu items (`i` ids): one line, `max_cells` letters (the menu's item width); past it reported.
* Speakers' labels and names (`n` ids) and other slot strings (`s` ids): `max_cells` their room in bytes (a letter a byte, a full-width character two); past it cut (the ending tokens kept) and reported.  The hero's name and label are what the player enters on the name-entry screen.
* The program's notices (`e` ids): in place, `max_cells` bytes; past it cut and reported.
* English is ASCII (pairs); another character is written full-width when JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures: the title menu's and the program's menus' labels, the title's logo, the notice before the prologue.
* The name-entry screen: its grid of kana and letters is the program's table the player picks the hero's name from; a name entered there is kana.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (LOVE.BAT: EQAP32 STARTUP), the title menu, Down and Enter on NEW GAME | OK: the menu (its labels drawn in the picture); the name-entry screen, its 決定 clicked and the confirmation passed with Enter |
| The prologue (PR.EQA), Enter after each message | OK: the messages in filler half-width (letter pairs), broken between words at the window's edge |
| The first scene (ST041A.EQA) | OK: the speakers' labels (their slot strings in filler, cut to their room; the hero's label as entered, kana) before the messages' filler |
| The program's menu (a right click in the scene) | OK: its items in filler (pairs), the first highlighted |
| ADDITIONAL MANUAL from the title menu: its menu, then a help page (the 74×12 window) | OK: the items in filler (past their room, as reported, running beyond the box); the page's filler broken between words in the window |
| A forced cut (PR.EQA's first part about 900 bytes, the rest in PR2.EQA), the prologue clicked through | OK: m02464, the first part's last message, then m02465, the first of PR2.EQA, the scene kept |
| The endings' hub split (ERE.EQA, its last scenes in ERE2.EQA): a test start calling ERE with var 00 at the table entry of a scene in ERE2 | OK: ERE2's first scene's messages (m01677 on), its speaker's label, page after page |
| A page break: the pseudo build's one paged message (m12333) in place of PR.EQA's first, in the game's flow | OK: four lines, a click, the rest on a new page, a click, the next message |
