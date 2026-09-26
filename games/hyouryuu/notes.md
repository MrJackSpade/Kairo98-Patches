# ♥ Hyouryuu (Illusion)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Hyouryuu/Hyouryuu [HD]/Hyouryuu.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Illusion's tmexec engine, `HYOURYUU/GAME.EXE`. Messages are `#nnnnn` ... `$` records in `K1.DOC`, `K10.DOC`, `K2.DOC`, `K3.DOC`, `K4.DOC`, `K5.DOC`, `K5X.DOC`, `K5Y.DOC`, `K5Z.DOC`, `K5Z2.DOC`, `K6.DOC`, `K6A.DOC`, `K6B.DOC`, `K6C.DOC`, `K7.DOC`, `K7A.DOC`, `K7B.DOC`, `K8.DOC`, `K8A.DOC`, `K8F.DOC`, `K8W.DOC`, `K9.DOC`, `K9A.DOC`, `K9F.DOC`, `K9V.DOC`; the engine's own Japanese strings (also `$`-terminated) are replaced in place.

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

2594 strings: 24 exe, 2570 msg.

♥ by the script-text scan (10 of 2570 strings match the sexual-vocabulary list (4 distinct terms)). The maintainer translates it; 0 strings have English so far.

## Limits

* Message lines wrap at the message window's width; `\n` forces a break, and a line that already fits is kept as written (spacing included).
* Clickable menus and buttons are hit-tested at the Japanese layout: those records carry a `note` in `strings.json` with the lines and columns to keep.
* Engine strings: their original byte length.

## Not handled

* Text drawn into the artwork (logos, captions, title menus drawn as pictures).
* Installer and driver messages.
* The date/place caption after the title ("2096年 東京都狛江市") is a picture.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Opening and title | OK |
| Main message window | OK: half-width filler inside the frame, 4-line box full |
| Scene past the opening (tent) | OK |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
