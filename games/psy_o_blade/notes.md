# Psy-O-Blade (T&E Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Psy-O-Blade/Psy-O-Blade [FD]/Psy-O-Blade (Program disk).hdm` (sha256 in `strings.json`), with `Psy-O-Blade (Data disk).hdm` in drive 2.
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).  VNDB's English release is the Mega Drive version's (a fan translation), another platform's.

## Engine

Two 2HD disks of raw sectors (no file system).  The main program (on the program disk at `program_at`, loaded at 2000h:0) loads overlays (code with the text inline) to 2000h:AEC0h, and small resident blocks (the speaker names, the item names, the save screens) above them, through 12-byte entries (drive, track, sector, length, address).  Text is stored 60h less than the characters; bytes below 20h are commands (window, clear, wait, colour, choices...).  Every message goes through one routine.  `pc98tl/psyo.py` documents it, `pc98tl/psyo_tl.py` the English.  A build with no English leaves the disk as it is.

* English at any length: a table of the English is put on the program disk's empty tracks and read into 6000h:0 at start-up by a stub in the program's zeros.  The message routine looks its message up there by its bytes and reads the English from it instead, drawing it half-width.
* Lines are broken between words at the window's right edge.  When English fills its window, the game's own wait cursor shows and the window is cleared for the rest (the Japanese scrolls).
* The disks have no file system: `MTL_NOTE.TXT` is written next to the patched disk, and the data disk is copied there unchanged.

## Script

1109 strings: 1109 messages (dialogue, narration, menus and choices, the speaker and item names, the title and disk screens).

Translation and the content classification (♥) are done by the translation model; 0 of 1109 strings have English so far.

## Limits

* Messages (`m` ids): any length; lines broken between words at the window's edge, a full window waits for a key and is cleared.  `\n` is a new line.
* `{XX}` and `{XX:args}` are the game's commands and must be kept, in order: `{04:nn}` picks a window, `{09}` clears it, `{08}` waits for a key, `{0C:nn}` sets the colour, `{05:...}` and `{06:nn}` place the text, `{0F}` marks a choice's start and end (keep a choice's text between its two `{0F}`), `{0E:...}` calls one of the game's routines (a picture, a portrait), `{14:...}` prints another message there, `{11:...}` a number.  The patcher warns by string id when the commands differ from the Japanese's.
* The same Japanese is one string everywhere (the game finds its English by the Japanese).
* English is ASCII; anything else is written as `?`, `[` and `]` (the game's kana switches) as `(` and `)`.
* The English all together must fit the disk's empty tracks and 256K of memory: a build over it is refused.

## Not handled

* Text drawn into the pictures.
* A few strings are code bytes the extractor took for text; they have no effect if translated.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot both floppies; the opening demo (cockpit picture, two speakers) | OK: names and lines in filler, half-width, broken between words |
| Title screen (PSY-O-BLADE, load a save?) | OK: title, copyright and the yes/no choice in filler; clicking the second choice starts a new game |
| First scene: two portrait windows | OK: the speaker names (the bars above the portraits) and both windows' lines in filler; a full window shows the game's wait cursor and is cleared for the rest |
| About 45 clicks on: the next scenes (corridor, four speakers) | OK: every line and name in filler, no Japanese left on screen |

Not reached in this test: the command menus, saving and loading (to a user disk in drive 2), the ending.
