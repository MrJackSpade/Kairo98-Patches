# ♥ Rankou Nyotaitsuri - Mokkoriman no Nani de Nushitsuri (Illusion)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Rankou Nyotaitsuri - Mokkoriman no Nani de Nushitsuri/Rankou Nyotaitsuri - Mokkoriman no Nani de Nushitsuri [HD]/Rankou Nyotaitsuri - Mokkoriman no Nani de Nushitsuri.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Illusion's tmexec engine, `RANKOU/GAME.EXE`. Messages are `#nnnnn` ... `$` records in `MI.DOC`; the engine's own Japanese strings (also `$`-terminated) are replaced in place.

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

301 strings: 24 exe, 277 msg.

Translation and the content classification (♥) are done by the translation model; 45 of 301 strings have English so far.

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
| Title and character menu (clickable lines) | OK: half-width filler inside the frame |
| Character call-out message | OK: half-width filler inside the frame |
| Scene past the opening (fishing-spot select with message) | OK: half-width filler inside the frame |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

The character menu (record m00001) is clicked by line: keep one item per line.
