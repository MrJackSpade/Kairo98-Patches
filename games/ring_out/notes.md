# Ring Out!! (ZyX)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Ring Out!!/Ring Out!! (FD version) [HD]/Ring Out!! (FD version).hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

ZyX's engine (`ZVA21F.EXE`): the scripts are the members of the archive `ZSD00` (a directory of names and offsets); each is run from the code offset at its start, its labels (the words before the code) the only places a jump or call goes, so a script may grow when its labels move with it.  A message is a run of commands (colour, a key and a new page, a new line, the speaker, inserted names and numbers) and text after FFh up to a NUL: bytes below 80h are characters from the program's table, the rest Shift-JIS.  The speakers' names are a coded member the scripts load (op 19h).  `pc98tl/zyx.py` documents the formats and the program patch, `pc98tl/zyx_tl.py` the English.  Unchanged files rebuild byte for byte.

* The scripts are walked with the program's own op lengths (its table, and its routines for the ops of variable length, recognised by their code) from their start and every label; the text runs are rewritten and the labels moved by the bytes before them.
* `ZVA21F.EXE` gets a helper, put in after its code segment (the segments after it moved up): 80h turns half-width letters on and off; a letter is drawn 8 dots wide from the ROM's ANK font through the program's own drawing (colour, outline, the delay between letters); at a space the line is broken when the next word would pass the window's edge, with the program's own new line and, past the window's bottom, its key wait and new page.  The speakers' names' loop gets the same letters.

## Script

2238 strings: 5 program messages, 93 menu items, 4 placed labels, 2125 message runs, 11 speakers' names.

Translation and the content classification (♥) are done by the translation model; 0 of 2238 strings have English so far.

## Limits

* Message runs (`m` ids, `max_cells` 56: a line's letters after the speaker's name): any length; the window breaks lines between words and pages when full.  The line breaks and pages of the Japanese are the script's own commands around a run, so `\n` is a space.  A run its note says is followed by an inserted name or number is drawn on directly before it.  A script with its English may take 64 KB; a build past it is refused and names the script.
* Choice menus' items (`i` ids): one line in the menu's box, `max_cells` its widest Japanese item; past it the line breaks inside the box.
* Labels (`l` ids): text the script places on the screen, one line without breaks: `max_cells` the Japanese's; past it the letters run on over what is beside them.
* Speakers' names (`n` ids): `max_cells` bytes (the room the program copies each into): a letter one, two more for the half-width letters' start and end, a full-width character two; past it cut and reported.
* Commands of the menus (`c` ids): as the speakers' names.
* Program messages (`e` ids): in their own bytes, `max_cells` the room; past it cut and reported.  The pieces of the two disk prompts that the program writes a drive's letter and a disk's number into keep their Japanese.
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the title logo, the menus' frames).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (the floppy version installed: RO.BAT, ZVA21F) | OK: the setup menu's items in filler, half-width, in their box; Down and Enter pick its last item |
| The opening (RO_01.ZSD) and the title | OK: the speakers' names in filler on their plates (cut to their ten bytes), the messages' filler after them broken between words, page after page with Enter; the title logo between |

KOM_F0.ZSD (a command table: SAVE, LOAD, the wrestling moves, the look and talk commands) is not extracted: no script loads it (op 19h names NAME_F0 only), so it is never shown.
