# ♥ Kitoujima Joshi Keimusho (Illusion)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Kitoujima Joshi Keimusho/Kitoujima Joshi Keimusho [HD]/Kitoujima Joshi Keimusho.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Illusion's tmexec engine, `PRI/GAME.EXE`. Messages are `#nnnnn` ... `$` records in `CHIKA_1`, `CHIKA_2`, `CHIKA_3`, `CHIKA_4`, `HAN.DOC`, `MASAKI_1`, `MASAKI_2`, `MASAKI_3`, `MASAKI_4`, `MIKI_1`, `MIKI_2`, `MIKI_3`, `MIKI_4`, `NOBUKO_1`, `NOBUKO_2`, `NOBUKO_3`, `NOBUKO_4`, `YOU_1`, `YOU_2`, `YOU_3`, `YOU_4`; the engine's own Japanese strings (also `$`-terminated) are replaced in place.

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

2602 strings: 64 exe, 2538 msg.

♥ by the safety valve: sexual assault during a prison intake search found while translating (first at m00007) (2026-09-26). Claude translated 6 strings before that point; the rest is the maintainer's to translate.

## Limits

* Message lines wrap at the message window's width; `\n` forces a break, and a line that already fits is kept as written (spacing included).
* Clickable menus and buttons are hit-tested at the Japanese layout: those records carry a `note` in `strings.json` with the lines and columns to keep.
* Engine strings: their original byte length.

## Not handled

* Text drawn into the artwork (logos, captions, title menus drawn as pictures).
* Installer and driver messages.
* The title menu and the opening narration are pictures (the narration pages and the name captions are drawn into the art).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title menu | OK (drawn as a picture, stays Japanese) |
| Character select: prompt and name row (engine strings) | OK: half-width filler inside the frame |
| Confirm box | OK: half-width filler inside the frame |
| Story message window after character select | OK: half-width filler inside the frame |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

Boot steps: the character select and the confirm box are clicked at the game's fixed click areas; those records carry layout notes.
