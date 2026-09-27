# ♥ Tenshi-tachi no Gogo VI - My Fair Teacher (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Gogo VI - My Fair Teacher/Tenshi-tachi no Gogo VI - My Fair Teacher [HD]/Tenshi-tachi no Gogo VI - My Fair Teacher.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's later scene engine: 101 scene files (`*.SCM`), command tables then messages ended by `00 00`, found by count (`pc98tl/jast_scm.py`).

## English display (`pc98tl/jast_scm.py`)

* The engine draws every character from the kanji ROM.  Its glyph fetch is
  rewritten: a code whose first byte is below 80 is two ASCII letters, drawn
  as the kanji ROM's two 8x16 ANK glyphs side by side in one cell (a far
  routine in a small DOS block from the entry stub); Japanese draws as before.
* English is one stream of lines padded to the window's width, words
  stopping two columns short of the edge; the engine pages a full box itself
  (waits for a click).

## Script

1118 strings (scene text).

♥ by the script-text scan (23 of 1174 strings match the sexual-vocabulary list (6 distinct terms)). The maintainer translates it; 0 strings have English so far.

## Limits

* Speaker lines are written `Name: text` (the name up to 14 columns, or a `%nnn` placeholder); `\n` starts a new paragraph.
* A scene file, with its English appended, must fit the engine's 16 KB scene buffer; the patcher leaves a scene that would not fit in Japanese and reports it.

## Not handled

* Text drawn into the artwork (logos, menus drawn as pictures).
* Strings hard-coded in the engine program (menus, item names).
* Installer and driver messages.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title / command menu | OK (engine menus stay Japanese) |
| Message window | OK: half-width filler inside the frame, wrapped between words (60 columns) |
| Long message: the engine pages a full box itself | OK (9-line test message) |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
