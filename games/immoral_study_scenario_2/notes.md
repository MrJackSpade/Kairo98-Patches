# Immoral Study Scenario 2 - Iijima Yuka (Scoop)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Immoral Study Scenario 2 - Iijima Yuka/Immoral Study Scenario 2 - Iijima Yuka [HD]/Immoral Study Scenario 2 - Iijima Yuka.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Scoop's Adventure Script Interpreter (`AI.COM`, with SCBIOS.COM and GSHELL.COM resident): each script (`*.BIN`, "Adventure v1.00") is a stack machine's code followed by its strings; the code pushes a string's offset in the table (op 0Dh) right before the op that shows it (44h a message or a speaker's tag, 4Ah a menu's item, 4Bh a menu's heading).  The English goes after the end of the file and only those pushes change, so the code, every jump and every other string stay where they were.  `pc98tl/scoop.py` documents the format, `pc98tl/scoop_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws ASCII half-width itself (SCBIOS.COM writes the text VRAM, a byte a cell) and pages the window itself, so the English needs no program patch; the patcher breaks the lines between words (0Dh) at the window's 54 cells, from where the message before left the line.
* Bytes A0h-DFh are characters from AI.COM's table (the hiragana the scripts use); `jp` shows them as they look.

## Script

1447 strings: 19 batch file lines, 150 menu items, 1263 messages, 8 speakers' tags, 7 menu headings.

Translation and the content classification (♥) are done by the translation model; 0 of 1447 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` 54: the window's width): any length; the patcher breaks the lines between words, the window waits for a key and starts over when full.  `\n` in the English forces a new line.  `[` and `]` around words show them in the highlight colour, as in the Japanese.  A script with its English may take 64 KB; a longer build is refused and names the script.
* Speakers' tags (`n` ids), menu items (`i` ids) and menu headings (`t` ids, shown highlighted): one line, `max_cells` the Japanese's; past it reported.
* Batch file lines (`b` ids): printed by `IMM02.BAT` when the game cannot start (memory or interrupts in use); one line.
* `{C1}`-style tokens are the colour commands inside a string and must be kept; `{X86A2}` is NEC's long line (the scripts draw out a vowel with it).
* English is ASCII (half-width); `<` and `>` (a tag's marks) are written `(` and `)`; another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the title logo, the window frames).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (IMM02.BAT: SCBIOS, GSHELL, AI IMMORAL2.BIN), the title menu | OK: the menu's items in filler, half-width, in their box; Enter picks the first |
| The opening: the narration and the first scene (the guard) | OK: the messages' filler half-width, broken between words at the window's edge, the window waiting for a key and starting over when full; the speakers' tags in filler in their colour (cut to their room); a choice menu's items in filler |
