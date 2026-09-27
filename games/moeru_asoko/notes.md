# ♥ Moeru Asoko no Paipai Yuugi (Illusion)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Moeru Asoko no Paipai Yuugi/Moeru Asoko no Paipai Yuugi [HD]/Moeru Asoko no Paipai Yuugi.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Illusion's C-compiled engine (`PAIPAI/GAME.EXE`, packed with Microsoft EXEPACK; the patch unpacks it with `pc98tl/exepack.py` and writes it back unpacked). Its text is NUL-terminated Shift-JIS strings in the program itself, replaced in place; strings with line breaks are DOS messages and stay plain ASCII.

## English display (`pc98tl/illusion_font24.py`)

* The engine draws text two bytes per 24-dot cell: its own 24-dot font for the
  characters it knows, the kanji ROM for the rest.  English is written as
  letter pairs whose first byte (A0-DF) no Shift-JIS lead, font code or
  control code uses, so the engine sends them down its kanji-ROM path.
* Two hooks there (the Shift-JIS to JIS step and the 16x16 fetch) put the
  kanji ROM's two 8x16 ANK letters side by side in the glyph buffer, which the
  engine scales like any kanji: two half-width letters per cell.  Untranslated
  Japanese draws as before.
* The hooks live in a small DOS block of their own (under 1 KB) that an entry
  stub allocates at the top of memory before the game starts; the drawer
  calls them through far pointers kept in data-segment bytes that stay zero
  at run time.  All patch sites are found by byte signature.

## Script

106 strings: 5 dos, 101 exe.

Translation and the content classification (♥) are done by the translation model; 0 of 106 strings have English so far.

## Limits

* Each string keeps its original byte length: one letter per byte, two per Japanese character (e.g. a 3-kanji hand name holds 6 letters).
* Strings with a `%`-specifier are printf formats: keep the specifier, and keep the English on each side of it even in length (see the string's `note`).

## Not handled

* Text drawn into the artwork (logos, captions, title menus drawn as pictures).
* Installer and driver messages.
* Tile faces, the call buttons (チー/ポン/カン/リーチ/ロン/ツモ) and the menus are pictures.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title and stage select | OK (pictures) |
| Opponent introduction | OK (picture) |
| Mahjong table: seat winds, scores, round label | OK: half-width filler letter pairs, two per cell; untranslated 局 draws as before |
| Calls, hand names and score screens during play | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

The patch uses the collection's hard-disk install; the floppy set needs disk swaps the boot steps can't do.
