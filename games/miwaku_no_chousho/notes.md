# Miwaku no Chousho (Black Package)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Miwaku no Chousho/Miwaku no Chousho [HD]/Miwaku no Chousho.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

Black Package's own engine, `MC\MCEXE.EXE` (started by `MCBAT.BAT` with `INIT.SO3`), on the hard disk.  The scripts (`*.SO3`, LZSS-compressed) are ops each with its length; three ops (jumps and calls) name places in their script.  `pc98tl/mcs.py` documents the format and the patch, `pc98tl/mcs_tl.py` the English.  A build with no English leaves the disk as it is.

* A changed script is laid out anew, its jumps' and calls' places moved, and compressed again.
* The program draws a byte below 80h from its own half-width font, so English goes in as ASCII.  The marks it takes as codes in a text (! ? - % & $ ^ ` { } # | * _ \ ~) are written as their full-width forms.
* The window breaks a line at its edge and pages after 4 lines by itself; the patcher breaks the English between words at 72 letters.
* A script runs in a segment of its own.  When a script's English would make it longer than F800h bytes (a little more than the largest the game ships), runs of ops it repeats are put once at its end as subroutines and called (ops whose handlers neither move the script's place, nor write into the script, nor mark the structured ops' ends); messages are never moved.
* Choices, the script words (the names and words a message's `` `n `` puts in), speakers' names and the program's own messages are written in their room.
* `MTL_NOTE.TXT` is put in the game's folder (`MC`).

## Script

9882 strings: 490 choices, 42 script words, 484 system screen lines, 8803 messages, 40 speakers, 23 program messages.

Translation and the content classification (♥) are done by the translation model; 0 of 9882 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 72 letters, 4 lines a window, more windows after a key; `\n` a new line.  Keep `{`0}` (the hero's name: 12 letters are allowed for it when breaking lines), `{%n}`/`{&n}` (numbers) and the other `{..}` codes.
* A script's room is a hard limit (a build past it, after its repeated ops are folded, is refused): F800h bytes.
* System screen lines (`l` ids: the sound setup, the menus, the options): drawn at their places, up to `max_cells` letters a line (longer is reported by string id); keep their `{..}` codes.
* Speakers (`n`), choices (`c`), script words (`i`) and program messages (`e`): up to `max_cells` letters (longer is cut and reported by string id).
* English is ASCII; other characters are written as `?` (curly quotes, dashes and `…` are made ASCII), the code marks as their full-width forms.

## Not handled

* Text drawn into the pictures (`.PR4`: the title, the logos).
* The program's console messages with blanks it fills in itself (the EMS memory message, the floppy prompts) are left in Japanese; the hard-disk release does not show the floppy prompts.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot the hard disk (MCBAT.BAT, MCEXE.EXE INIT.SO3): the sound driver's setup screen | OK: every line in filler, half-width, at its place in its box |
| Return: the main menu, then a new game's name entry | OK: the menu's title and items in filler; the name prompt and its two choices in filler |
| The opening and the first messages of MC_START.SO3 (folded to fit its room) | OK: each message in filler, half-width, broken between words at 72 letters; the scene goes on through the moved jumps and calls |
| A test build with a five-line message | OK: the window shows four lines, then the fifth on a new window after a key |

Not reached in this test: choices inside the story, the save and load screens, and the folded big scripts (MC_EVE50 and the like) beyond their first messages.
