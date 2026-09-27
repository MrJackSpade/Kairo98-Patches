# Angel Army (Illusion)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Angel Army/Angel Army [HD]/Angel Army.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Illusion's C-compiled engine (`ARMY/GAME.EXE`, packed with Microsoft EXEPACK; the patch unpacks it with `pc98tl/exepack.py` and writes it back unpacked). Its text is NUL-terminated Shift-JIS strings in the program itself, replaced in place; strings with line breaks are DOS messages and stay plain ASCII.

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

297 strings: 234 exe, 63 text.

No ♥ (0 of 297 strings match the sexual-vocabulary list (0 distinct terms)). Claude translates it; 297 of 297 strings done.

## Limits

* Each string keeps its original byte length: one letter per byte, two per Japanese character (e.g. a 3-kanji hand name holds 6 letters).
* Strings with a `%`-specifier are printf formats: keep the specifier, and keep the English on each side of it even in length (see the string's `note`).

## Not handled

* Text drawn into the artwork (logos, captions, title menus drawn as pictures).
* Installer and driver messages.
* The title logo, country cards and map/menu graphics are pictures.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title menu (engine strings) | OK: half-width letter pairs; English build reads correctly |
| Leader quote boxes (MESSAGE.TXT), turned horizontal | OK: filler and English inside the box, name label below |
| Scene past the opening (country card, next quote) | OK |
| Map play, unit menus, status and damage screens | not yet seen (their strings are translated and within their byte limits) |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

Needs DIP switch 2-8 OFF (game.json "dipsw"; the game refuses to start otherwise). The patch uses the collection's hard-disk install.

Engine strings keep their byte length, so some labels are abbreviated (country names JPN/CHN/GER, one-kanji terrain names as two letters, the heroine Kotono as Koto on name labels).
