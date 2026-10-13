# Maison Ikkoku - Omoide no Photograph (MicroCabin)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Maison Ikkoku - Omoide no Photograph/Maison Ikkoku - Omoide no Photograph [FD]/Maison Ikkoku - Omoide no Photograph.hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

`PIYO.EXE` runs the compiled script `PIYO.LDY`; the messages are in `PIYO.LBC`, each byte coded by the one before it in its message (rotated by its low three bits).  The patcher writes `PIYO.LBC` anew and sets every message's place in `PIYO.LDY`'s table; the commands and the names, which the script names by number through two more tables of places, go at `PIYO.LDY`'s end when changed.  `pc98tl/piyo.py` documents the format, `pc98tl/piyo_tl.py` the English.  Unchanged files rebuild byte for byte.

* The program draws the text on the text layer, a one-byte character as a half-width cell: English goes out as ASCII, no drawing change.
* Each of `PIYO.LBC` and `PIYO.LDY` is read into one segment: 65535 bytes each; a build past it is refused.

## Script

915 strings: 10 program notices, 14 strings inside the script's code, 74 commands, 696 messages, 121 names of things and people.

Translation and the content classification (♥) are done by the translation model; 0 of 915 strings have English so far.

## Limits

* Messages (`m` ids): the window under the picture is 80 half-width cells wide and 10 rows high, scrolling as messages come.  The patcher breaks the English between words at 79 cells; `\n` forces a new line.  A message past 10 lines is reported (the window shows that many).
* Commands (`u` ids) and names (`n` ids): the menu shows 16 half-width cells of each (the program prints them `%-.16s`); longer is reported.  Names are also put into messages.
* Strings inside the script's code (`l` ids) and the program's notices (`e` ids): written in place, `max_cells` their bytes; longer is cut and reported.
* English is ASCII; another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the title).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the floppy (PIYO.EXE): the title, then its menu (start, continue) | OK: the menu's two items in filler half-width in the menu window, the first highlighted |
| Start: the first room, then commands from its menu, moving through the house | OK: each room's command menu in filler half-width, 16 cells an item; the messages' filler broken between words at 79 cells in the window under the picture, scrolling as they come; the rooms changing with the commands |

Not reached in this test: the other characters' scenes, saving and loading, the endings.
