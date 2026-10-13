# Lesser Mern (Panther Software)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Lesser Mern/Lesser Mern [HD]/Lesser Mern.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-10 (`research/clearance.json`).

## Engine

Panther Software's own RPG engine (`LESS.EXE`): the maps' scripts (`MDTnnn`, their messages inline in their events, the speaker names in a table), the events' (`EV200, EV201, EV202, EV203, EV204, EV205`) and the ending's (`ED200, ED201`, run by `ENDG.EXE`) share one message routine (a copier building the message, then a window drawing it a character at a time); the program's own text (monsters, items, magic, battle and system messages, menus) is in its data segment; the opening (`OPEN.EXE`) has a script of its own that puts each character's glyph into a gaiji.  `pc98tl/lmern.py` documents the formats and the program patches, `pc98tl/lmern_tl.py` the English.  Unchanged files rebuild byte for byte.

The patch works on the game's hard-disk release (the game in `LM/`).

* `LESS.EXE` and `ENDG.EXE` get a helper put in at the end of their code segment, their data segment grown to 64 KB (the message buffer moved to its end, 2 KB) and a segment of English put in after it.  A byte from 20h to 7Fh is a half-width letter, drawn 8 dots wide from the BIOS 8x16 font, bold, in the caller's colour; the window breaks lines between words.  Every string keeps its own bytes (lists walked by counting their strings keep their layout): English past them goes on elsewhere through an escape (7Fh into the map's script, 7Ch into the English segment, back at 7Dh; 7Eh filler is skipped), followed by the copier, the window and the string routine alike.
* A map's script is rebuilt with its English, the speaker names put at its end and their table pointed at them.
* `OPEN.EXE` gets a helper drawing two letters into each gaiji; each message's text and its pages' layout (where the gaiji go, line by line) go into room put in after the program, the layout made anew for the English (wrapped between words to the page's width), the page's timing, sounds and faces kept in their order.
* `LM.COM` and `OP.COM` (the menu run first) get the half-width letters in their string routine.

## Script

2140 strings: 522 program strings, 1504 messages (maps, events, the ending), 95 speaker names, 19 opening messages.

Translation and the content classification (♥) are done by the translation model; 0 of 2140 strings have English so far.

## Limits

* Messages (`m` ids, `max_cells` 52, the map window's line): any length.  The window wraps between words and waits for a key when full; `\n` starts a new line.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.  A map's script with its English may take 17192 bytes; a build past it is refused and names it.
* Speaker names (`n` ids): one line, `max_cells` 24.
* Program strings (`e` ids): messages (`max_cells` 52) as the maps' are; names and labels any length, but `max_cells` is the room of the menu, box or line they sit in (past it they run over its edge, and what is drawn outside a menu stays on screen after it closes).  Past their own bytes they are written in ASCII only (`?` for another character).  A program's English segment may take 65520 bytes; a build past it is refused.  The two lines of the menu run first are cut to their own bytes (reported).
* Opening messages (`o` ids): wrapped by the patcher to `max_cells` letters a line (the page's width), ASCII only, at most 376 letters a message (two to a gaiji; past it cut and reported); `\n` starts a new line.

## Not handled

* Text drawn into the artwork (the title logo, the status window's labels, which are English already, the pictures).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk: the menu run first (LM.COM) | OK: its two lines drawn half-width (the filler cut to their bytes, reported) |
| Title menu (LESS.EXE's string routine) | OK: the filler labels half-width, in the menu's colours; past the box where longer than the Japanese |
| New game, the field menu and a system message (the message window) | OK: the menu's labels half-width; the message's filler past its own bytes, read from the English segment |
| A map's message (MDT002: a villager talking) | OK: the speaker's name (moved to the script's end) on the first line, the message's filler wrapped between words at the window's width, going on past its own bytes |
| Opening (OPEN.EXE) | OK: the filler drawn two letters to a gaiji, wrapped between words, line after line at the page's place, with the opening's pictures and timing |
| Events (EV200-EV205) and the ending (ED200, ED201 in ENDG.EXE) | not reached in the test (the same message routine and helper as the maps') |

Names and labels longer than the Japanese draw past their menu or box, and what is drawn outside a menu stays on screen after it closes: keep them to their `max_cells`.
