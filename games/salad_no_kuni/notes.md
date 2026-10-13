# Salad no Kuni no Tomato-hime (Hudson Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Salad no Kuni no Tomato-hime/Salad no Kuni no Tomato-hime [FD h01] [Set 1]/Salad no Kuni no Tomato-hime [Set 1].d88` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-11 (`research/clearance.json`).

## Engine

An N88-DISK BASIC(86) disk: `START` (a BASIC program) BLOADs `SARADA.P0` (the game's core, x86 code) and the chapters `SARADA.P1`-`P4` (x86 code with their text in it: half-width katakana strings ended by a 0).  P0's string routine prints every string, whether written after a call, in a table, or named by an immediate.  `pc98tl/sarada.py` documents the format, `pc98tl/sarada_tl.py` the English.  A build with no English leaves the files as they are.

* English at any length: the string routine is made a far call to a helper loaded with a table (`SARADA.T0`-`T4`, at 2600h:0, memory neither BASIC nor the game uses; `START` loads each with its chapter).  A string with English is printed from the table instead, a word at a time, broken between words from the cursor's real column.
* The game shows the text layer's last 4 rows under its picture and scrolls the whole layer: the scroll waits for a key before a line not yet read would leave the window.
* The chapters' inventory, which printed its names a character at a time, prints them through the string routine.
* The parser's word list (in P0) already takes English words; it is not extracted.

## Script

584 strings: 559 messages, 25 inventory names.

Translation and the content classification (♥) are done by the translation model; 0 of 584 strings have English so far.

## Limits

* Messages (`m` ids): any length.  The helper breaks the English between words at the screen's 80 columns (the last left free) from wherever the cursor is; `\n` forces a new line.  A key is waited for after each windowful (3 lines).  A message the player answers on the same line (the prompts) should end as the Japanese does, with its space.
* Inventory names (`n` ids): one line each, the next name after a space.
* English is ASCII; another character (and `|`, which the game draws as another sign) is written as `?`.

## Not handled

* Text drawn into the pictures (the title logo).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the floppy (START auto-run): the title picture and its text window | OK: the credits and the next message in filler half-width, broken between words, a key waited for once the 4-row window is full (Space goes on) |
| Type START: the first scene | OK: the scene's description and the prompt in filler, paged at the window |
| Type I (inventory), then LOOK | OK: the inventory's line and each object's name in filler, then LOOK's answer; the picture intact |

Not reached in this test: chapters 2-4 (their tables load the same way as chapter 1's), saving and loading.
