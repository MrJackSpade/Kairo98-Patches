# ♥ Kankin (Illusion)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Kankin/Kankin [HD]/Kankin.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Illusion's tmexec engine, `KAN/GAME.EXE`. Messages are `#nnnnn` ... `$` records in `MES0.DOC`, `MES1.DOC`, `MES2.DOC`, `MES3.DOC`, `MES4.DOC`, `MES5.DOC`; the engine's own Japanese strings (also `$`-terminated) are replaced in place.

## English display (`pc98tl/illusion_font.py`)

* The message library draws a record one Shift-JIS character at a time from
  the kanji ROM. Its draw loop is rewritten in place (both far calls stay at
  their offsets, so the relocation table still matches): a byte below 80 is
  drawn as the kanji ROM's 8x16 ANK glyph, one column wide, so English is
  half-width and untranslated Japanese still draws as before.
* English is word-wrapped to the message window's width (taken from the
  engine's calls to the message routine); a line the engine wraps by itself
  swallows the line break right after it.
* Messages longer than the box page: the box area is saved on graphics page 1
  (unused by these games), the game waits for a click, the box is restored and
  the text continues at the top. Only messages longer than the box do this.
* The pager lives in a small DOS block of its own (under 1 KB) that an entry
  stub allocates at the top of memory before the game starts; the stub's
  load area is zeroed again afterwards. The game keeps all its other memory.
* The message lookup's end mark changes from `!` to the ^Z every message file
  ends with, so English may use `!`. All patch sites are found by byte
  signature.

## Script

450 strings: 30 exe, 420 msg.

Translation and the content classification (♥) are done by the translation model; 0 of 450 strings have English so far.

## Limits

* Message lines wrap at the message window's width; `\n` forces a break, and a line that already fits is kept as written (spacing included).
* Clickable menus and buttons are hit-tested at the Japanese layout: those records carry a `note` in `strings.json` with the lines and columns to keep.
* Engine strings: their original byte length.

## Not handled

* Text drawn into the artwork (logos, captions, title menus drawn as pictures).
* Installer and driver messages.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Opening narration (full-screen text) | OK: half-width filler inside the frame |
| Title and message window over the title art | OK: half-width filler inside the frame |
| Scene past the opening (car) | OK, messages page on click |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
