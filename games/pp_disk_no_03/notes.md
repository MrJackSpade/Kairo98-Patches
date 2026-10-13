# PP Disk No. 03 (Mediax / P's PSYTEC)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `PP Disk No. 03/PP Disk No. 03 [FD]/PP Disk No. 03 (Disk A).hdm` (sha256 in `strings.json`), with `PP Disk No. 03 (Disk B).hdm` next to it.
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

A disk magazine: on each floppy the viewer `PPDISK.EXE` (the same program on both), its menus (`PPDISK.SCR`: the menus, Pia's speech balloons and a pool of strings the program relocates when it loads it) and its text (`PPDISK.TXT`: records of lines, shown in the menus' box or on the whole screen).  Disk B also carries Silky's *REIRA* demo (`SIL.EXE`, `SILK0.DAT`: the AI5 engine, patched by `pc98tl/ai5.py`) and its installer (`PPCOPY.EXE` with `PPCOPY.CMD`).  `pc98tl/ppdisk.py` documents the formats and the program patch, `pc98tl/ppdisk_tl.py` the English.  Unchanged files rebuild byte for byte.

The floppies have no room for the English (5 KB and 3 KB free), so the patch lays them out on a DOS hard disk, as the other floppy games here are: Disk A in `\PPDISK`, Disk B in `\PPDISK\B`.  AUTOEXEC.BAT starts Disk A's viewer and then Disk B's, each with `-d` (the program's own switch: ESC on the main menu quits, which on the floppies it never does).  The demo runs with `GAME` in `\PPDISK\B`.

* `PPDISK.TXT` is rebuilt with the English, wrapped between words, and the menus' offsets of its records rewritten.
* The menus' strings are written in their own bytes, or at the end of the pool (its size in the header grows).
* `PPDISK.EXE`: the viewers' tables of page starts (32 on the stack) are moved to the last 512 bytes of the 32 KB text buffer (256 pages), every read into the buffer stopping short of them.  ASCII is drawn half-width by the program's own text routine.  Its messages are written in their own bytes.

## Script

196 strings: 22 articles, 10 Pia's balloons, 20 REIRA demo messages, 10 REIRA demo menu items, 8 REIRA demo labels, 25 program messages, 1 installer text, 46 menu items, 38 full-screen pages, 16 menu titles.

Translation and the content classification (♥) are done by the translation model; 0 of 196 strings have English so far.

## Limits

* Articles (`a` ids, `max_cells` 46): lines wrapped between words to 46 letters, 8 lines to a page; full-screen pages (`p` ids, `max_cells` 80): 80 letters, 24 lines to a page.  `\n` between lines (a line's leading spaces are kept).  A record may take 32255 bytes (a byte a letter and one for each line's end) and 256 pages; a build past either is refused and names it.
* Menu titles (`t` ids, `max_cells` 36) and items (`m` ids, `max_cells` 46): one line; past it they run over the box (reported).
* Pia's balloons (`b` ids): wrapped to 16 letters, 6 lines at most; past them the build is refused.
* Program messages (`e` ids): in their own bytes, `max_cells` the room; past it cut and reported.  `{S1}`/`{N1}` stand for the name/number the program puts in.
* Installer text (`i` ids): lines wrapped to 78 letters; the screen shows 23, past them the first scroll off (reported).
* REIRA demo (`dm`, `di`, `dl` ids): as the AI5 games' messages, menu items and labels (`games/reira/notes.md`).
* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else as `?`.

## Not handled

* Text drawn into the pictures (the title screen, the map, the icons).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (Disk A's viewer, PPDISK -d) | OK: the title, then the main menu: its title, items and Pia's balloon in filler, half-width, in their boxes |
| Disk A: the map quiz (the first item) | OK: its message in filler in the bar under the map |
| Disk A: an article (a menu of type 3) | OK: the filler wrapped between words at the box's 46 letters, 8 lines to a page, the next page with Enter |
| Disk A: a list (CG pictures and full-screen pages) | OK: the pages' filler wrapped at 80 letters, 24 lines to a page, the next page with a click; the pictures load |
| ESC on the main menu, then Disk B's viewer | OK: Disk A's viewer quits, Disk B's title and menus follow in filler |
| Disk B: the REIRA demo's installer text (PPCOPY.CMD) | OK: shown in filler wrapped at 78 letters; at 2.5 times the Japanese it takes 31 lines and the first scroll off (reported by the patcher) |
| The REIRA demo (GAME in \PPDISK\B, run on its own) | OK: its setup screen, then its first message and menus in filler; later scenes not reached |

Disk B's own record 0 (a copy of the replay mode's help) is never shown: no menu on Disk B opens the replay mode.
