# Bacta 1&2 + Voice (Himeya Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Bacta 1&2 + Voice/Bacta 1&2 + Voice [HD]/Bacta 1&2 + Voice.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-23 (`research/clearance.json`).

## Engine

Himeya Soft's B12 engine (`BACTA\B12.EXE`, run by `BACTA21.BAT`; type `CD BACTA` and `BACTA21` at the prompt), with Bacta and Bacta 2 in one set (a voice or a text mode, then the game).  The scripts are the members of `SNR`, an archive of names and places, each byte of a member rotated 5 bits: op codes (31 of them) with addresses (gosubs, jumps by a variable, the flags' and variables' conditional jumps) as words, and if/else blocks run "skipped" in between.  `pc98tl/b12.py` documents the formats, `pc98tl/b12_tl.py` the English.  A build with no English leaves the disk as it is.

* The scripts are read op by op and written again with their texts at any length, every address moved with what it points at; the archive is written again.
* The engine draws bytes below 80h half-width itself: the English needs no program patch.
* The window (Bacta's 3 lines of 68 letters, Bacta 2's 4 of 60, as each script sets it) breaks a line at its edge and goes on down past its bottom; its new-line code in a text does not move the window's position.  The patcher breaks the English between words and fills each line with spaces to the edge, and puts a wait for a key and a cleared window after each window's lines.
* `MTL_NOTE.TXT` is put in the game's folder (`BACTA`).

## Script

11236 strings: 344 menu choices, 10804 messages, 88 speakers' names.

Translation and the content classification (♥) are done by the translation model; 0 of 11236 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at `max_cells` letters (68 or 60), its window's lines a window, more windows shown in turn; `\n` a new line.  The speaker's name before it is a string of its own.
* Speakers' names (`n` ids): up to 16 letters, put before each of their messages with a space.
* Menu choices (`c` ids): up to `max_cells` letters (the menu's widest Japanese); longer is reported by string id.
* A script with its English must fit its segment (64 KB); a build past it is refused and names the script.
* English is ASCII; other characters are written as `?` (curly quotes, dashes, `…` and the brackets are made ASCII).

## Not handled

* Text drawn into the pictures (`GDT`: the opening's notice, the titles).
* The spoken lines (`PCM`, the voice mode).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Pseudo build boots (np21w, BACTA21.BAT) | OK: the mode and game menus' choices half-width in their boxes |
| Bacta's first scenes (pseudo) | OK: speakers' names and messages half-width in the 68-letter window |
| Bacta 2's title and opening (pseudo) | OK: the opening's messages broken between words in its 56-letter window |
| Partly translated build | OK: a long message broken between words over two windows, each waiting for a key; the rest in Japanese as before |
| Unmodified build | OK: a build with no English is the source image byte for byte |

Past the first scenes of each game the boot test did not play; every script goes through the same rebuild.
