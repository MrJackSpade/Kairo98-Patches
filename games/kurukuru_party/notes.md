# Kurukuru Party - Princess Quest (Cocktail Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Kurukuru Party - Princess Quest/Kurukuru Party - Princess Quest [HD]/Kurukuru Party - Princess Quest.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-07 (`research/clearance.json`).

## Engine

Ides' **gip** 2.08 ("Gun'sHip"): `PQ.OV1` (the gip system) runs `PQ.OVL` (the script interpreter and the game's own commands) with the frame file `PQ.OV2`, all in `PQ/` on the game's hard-disk release.  The script is bytecode in `EVT/*.EVT` (121 files with text); `pc98tl/gip.py` documents it.  Every command has a fixed length or a known form; the disassembler follows the code from each script's start (and from the entries the game's commands start) and reaches every Japanese string.

* Messages, menu items and string variable values are reached only through the commands' pointers, so the English is laid out in the bytes the Japanese leaves free and after the script's end, and the pointers are moved to it; the code does not move.
* The game's text driver draws ASCII half-width, so English is written as ASCII; the program is not changed.
* Lines are wrapped between words to the window the script opened, a letter short of its width (a letter in the last column wraps the line itself), and a new page (key wait, clear) starts before a line would scroll the window.

## Script

4025 strings: 72 menu items, 3932 messages, 21 string variable values.

Translation and the content classification (♥) are done by the translation model; 0 of 4025 strings have English so far.

## Limits

* Messages (`m` ids): any length; `\n` starts a new line.  `max_cells` is the line's room in its window (English letters); longer text wraps between words and pages.
* `{Xn}` in a message is string variable n, which the script sets to a name, a speaker's name and opening bracket, an indent or a page break (the string's `note` says which): keep it in the English; the variable's own value is a `v` id.
* Menu items (`i` ids): `max_cells` letters, the menu window's width; longer ones are cut and reported.
* String variable values (`v` ids): up to 64 bytes (64 letters).
* A script may not outgrow its buffer: the main one holds 20000 bytes, the second one (for the scripts the others load and call) 7003.  A script's English may take the bytes of all its Japanese strings and the room left in its buffer; a build whose English does not fit is refused and names the script and its strings.  The scripts in the second buffer have the least room: in some, the English should take about as many bytes as the Japanese.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The gip system's own messages in `PQ.OV1` (option, memory and disk errors) and the floppy release's disk prompts in `PQ.INI`; the hard-disk release does not ask for disks.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title menu, the start and the mode question (START.EVT) | OK: filler wrapped in the two-line box and paged with a key wait; menu items at their places, cut to the menu's width |
| Character select (PREMAIN1.EVT) | OK: filler in the message window beside the portraits; the YES/NO menu |
| The explanation (EXP.EVT, run from a test image whose start script chains to it) | OK: filler wrapped between words in the 40-letter, four-line window, a new page before a line would scroll it |
| The scripts in the second buffer (the characters' openings, events, endings), the board game | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
