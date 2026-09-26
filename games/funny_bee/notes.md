# ♥ Uchuu Kaitou Funny Bee (Alice Soft, 1994)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Uchuu Kaitou Funny Bee [HD]/Uchuu Kaitou Funny Bee.hdi` (sha256 in `strings.json`).
Clearance: no English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Alice Soft **System 3**. The script is split across `BEE/ADISK.DAT` and `BEE/BDISK.DAT`
(80 pages). There's no `AG00.DAT`, since this game has no verb/object menu. Disassembling
and reassembling all pages reproduces both files byte for byte.

## English display (`pc98tl/alice3_font.py`)

* The kana table in `ADV.COM` is remapped so the bytes A0-DD become NEC half-width
  ASCII glyphs from the kanji ROM, at one script byte per letter. Characters
  outside `A-Z a-z . , ! ? ' - : ( )` and space are written as 2-byte half-width
  codes.
* The text drawer advances half a cell after a half-width character, and a full
  cell otherwise, so Japanese that hasn't been translated yet still lays out correctly.
* The scenario page pool goes from 32 KB to 128 KB, and the stack moves up to make
  room for the hook.

All patch sites are found by byte signature, not fixed addresses.

## Limits

* Message lines: the width of the widest Japanese line in each message, at least 21 cells (42 letters).
* Menus: each item's own Japanese width in cells (twice that in letters). The menu
  box grows to the right from a fixed position and runs off screen when an item is too long.
* Names: 32 bytes.

## Test status (np21w)

| Test | Result |
|---|---|
| Boot, intro, title menu with 2.5× filler | OK: half-width text renders; menus fit |
| Scrolling intro text | JP-length screens redraw over earlier lines. Check with real English |
| Menu highlight bar | stops slightly short of long items (cosmetic) |
| Gameplay, save/load | not yet seen |
