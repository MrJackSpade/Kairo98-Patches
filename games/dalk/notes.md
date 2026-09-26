# Dalk (DALK, Alice Soft, 1992)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Alice Soft/Dalk/Dalk [HD].zip` → `Dalk (v1.08) (uncensored).hdi`
(sha256 recorded in `strings.json`; the patcher warns if you use a different dump).

## Engine

Alice Soft **System 2** (`ADV.COM`, "Scenario decode system for PC98/286 Ver 1.00").

| File | Contents | Handled by |
|---|---|---|
| `DALK/ADISK.DAT` | 41 scenario pages (bytecode + inline Shift-JIS) | `pc98tl/alice_sys2*.py` |
| `DALK/AG00.DAT` | verb / object captions for the command menu | `alice_sys2_tl.py` |
| `DALK/ADV.COM` | interpreter; 4 hard-coded strings; font hook | `advhack.py` |
| `*CG.DAT` | graphics: status panel labels (LV / EXP / H.P / アイテム) are drawn into the art | not handled (image editing) |

The opcode lengths come from the open-source reimplementation
[kichikuou/system3-sdl2](https://github.com/kichikuou/system3-sdl2) (`nact_sys2.cpp`).
Disassembling and reassembling all 41 pages reproduces ADISK.DAT byte for byte,
and every jump target resolves.

## Patches applied to ADV.COM (`advhack.py`)

1. **Packed half-width English.** The engine draws only 16px cells, and it
   expands the half-width kana in the script into full-width hiragana (table at
   CS:1A29). Two English letters go into one unused Shift-JIS code (lead 0x80
   or 0xEB–0xFF). A hook on the SJIS→JIS converter (CS:483E) and the glyph fetch
   (CS:485F) builds the 16×16 cell from the engine's own 8×16 ANK font
   (A100:0000). The result is one byte per letter and two letters per cell, and
   the engine's layout code is unchanged.
2. **Bigger scenario page pool.** Pages load into a compacting pool (segment
   [5560]) that was 48 KB. A page-calling page stays resident under the page it
   calls, and there's no overflow check. It's now 128 KB.
3. **Stack moved** from A8F6 to B8F6 (with the DOS memory block grown to match),
   so the hook code can live after the end of the file.

## Limits (enforced by patch.py)

* **Line width.** Each message may use the width of its widest Japanese line,
  but never less than 21 cells (42 letters). The engine never wraps on its own.
  The main message box is about 22 cells wide.
* **Lines per box: no limit.** The engine pages overflowing text itself
  (checked: 7 lines in the 4-line box show as 4, then a key press, then 3).
* **Page size.** 16-bit addresses mean each page must stay under 64 KB. At 2.5×
  stress length the largest page is 60 KB, and real English should be well under that.
* **Names** (`kind: name`) go into fixed slots with a per-category `max_cells`
  (characters, classes and commands 5; items 8; monsters 10). The patcher warns
  on overflow.
* **exe strings** are replaced in place, with at most `max_bytes` encoded bytes.
* Characters outside `A–Z a–z 0–9 space . , ! ? ' " - : ( )` are drawn
  full-width (one whole cell each). `;` becomes `,`, `[]` becomes `()`, and
  curly quotes become straight quotes.

## Test status (np21w, `tools/emu_shot.ps1`)

| Test | Result |
|---|---|
| Boot, intro, title menu with English message box + menu | OK, crisp half-width text |
| Every string at 2.5× length (`patch.py --pseudo`) | boots, New Game, first scenes OK |
| 7-line message in the 4-line box | engine pages it automatically |
| Partial translation (English and Japanese mixed) | OK |
| Command (verb/object) menu, battle, dungeon, save/load | **not yet seen**: needs a longer scripted playthrough |

## Translation status

* Done (by hand): all 249 `name` entries (party, classes, commands, items,
  monsters, staff), all verb/object captions, the engine strings, and the title menu.
  Adjust any of these freely. Romanization follows the katakana with no
  official source, so e.g. セイル = "Seil" is a guess.
* Everything else (`msg` and most `menu`) is untranslated and ready for MTL.
  See `tools/mtl.py`.
