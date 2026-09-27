# ♥ Tenshi-tachi no Gogo III Bangaihen (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Gogo III Bangaihen/Tenshi-tachi no Gogo III Bangaihen [FD]/Tenshi-tachi no Gogo III Bangaihen (Disk A).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's self-booting engine: the floppies have no file system.  The boot sector loads the engine (hand-written assembly) from a fixed sector; directory tables in it give each file's disk, sector and length.  54 scenes hold command tables, then messages read two bytes at a time and ended by a zero word, found by count; the menu verbs and nouns are 16-byte entries in one more file (`pc98tl/jast_boot.py` documents the layout).

The disk tool that built the floppies cut files at a sector boundary and left old sector contents after each file's end; the extractor stops each scene at the first leftover fragment, and keeps a scene's cut-off last message as it is.

## English display (`pc98tl/jast_boot.py`)

* The engine prints on the PC-98 text layer.  Its message and menu draws
  hand each Shift-JIS code to one character routine; both calls now go to a
  helper that draws a code whose first byte is below 80 as two ASCII letters
  in two half-width cells (the engine's own half-width put).  Japanese draws
  as before.
* English lines are wrapped to 72 columns between words and joined by the
  engine's line mark `↓` (builds without it: padded with spaces to the edge,
  where the engine wraps).  The three-line box scrolls a line at a time, so
  the line scrolls in the message draw go through a pager: every third new
  line of a message waits for a key or a left click first.  The helpers sit
  in the unused (zero) tail of the music table, which stays zero in a
  running game.
* A word file with a message table is rebuilt and loaded just below the
  engine, which gives the scene buffer the room the file leaves.

## Script

1988 strings (1712 scene text, 276 menu words).

♥ by the safety valve: explicit sexual command words (clitoris, fellatio, SEX, first at w00117) and sex scenes found while checking the script; for the translation model: a character is stated to be 17 in a sexual context at m01674 (scene52:3) (2026-09-27). The maintainer translates it; 0 strings have English so far.

## Limits

* Messages: `{C2}` (name colour), `{C1}` (highlight) and `{C0}` (normal colour) switch the text colour and are not drawn; `{A<n>}` are animation controls; keep them. `\n` starts a new line.  Full-width characters such as 「」 can stay in the English.
* Menu words: 14 letters (7 cells shown); longer ones are cut and reported.
* A rebuilt scene must fit the engine's scene buffer (it loads below the word file); the patcher refuses a scene that would not.  Grown scenes move to free sectors of their disk (no table refers to them, one filler byte throughout) and their directory entry is updated.
* The disks have no file system, so the machine-translation notice is `MTL_NOTE.TXT` next to the patched images instead of a file on the disk.

## Not handled

* Text drawn into the artwork (the title logo).
* The engine's other screen strings (save/load, disk prompts) are English already, drawn full-width, and are left as they are.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title and opening (floppy set: boot disk and disk 2) | OK |
| Verb and noun menus | OK: filler words half-width inside the menu boxes |
| Message window (this build has no line mark: lines padded to the edge) | OK: half-width filler inside the frame, wrapped between words |
| Long message: waits at a full box, next lines after a key | OK (a test build with a six-line message at the start) |
| Partly translated build: untranslated Japanese still correct | OK (menus in Japanese next to an English message) |
| Scene past the opening (breakfast) | OK |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
