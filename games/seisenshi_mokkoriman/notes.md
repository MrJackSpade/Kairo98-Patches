# ♥ Seisenshi Mokkoriman (Illusion)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Seisenshi Mokkoriman/Seisenshi Mokkoriman [HD]/Seisenshi Mokkoriman.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Illusion's older engine (``MOKKORI/GAME.EXE``). Messages are records in `MES0.D`, `MES1.D`, `MES2.D`, `MES3.D`, `MES4.D`, `MES5.D`, `MES6.D`: `10 <index> <group>` then Shift-JIS text; group 90 is the character profiles (one record per frame line), A0 a song's lyrics, F4 the disk prompts, the rest scene messages.

## English display (`pc98tl/illusion_mes.py`)

* The engine draws a byte below 80 from its own 8x16 font (`FONT.DAT`, a full
  ASCII set), so English is half-width with no font work; records may change
  length.
* Its text windows scroll when their rows run out. The patch makes them page
  instead: the window waits for the space key or a left click, clears and
  goes on at the top. The pager sits in the dead scroll code itself, around
  the relocated calls there, so nothing moves and no memory is taken.
* Each message file loads into a 10000-byte buffer (up to the next buffer),
  so the patcher refuses a file that outgrows it.

## Script

311 strings: 9 lyric, 243 msg, 53 profile, 6 prompt.

♥ by the script-text scan (33 of 311 strings match the sexual-vocabulary list (4 distinct terms)). The maintainer translates it; 0 strings have English so far.

## Limits

* Each string has `max_cols` (its window's width: profile lines 22, disk prompts 32, scene messages 70); longer lines are word-wrapped, `\n` forces a break.
* Profile records are one frame line each.
* A message file may grow to 10000 bytes.

## Not handled

* Text drawn into the artwork (logos, captions, title menus drawn as pictures).
* Installer and driver messages.
* The title song's lyrics and credits, the scenario menu and the scene title cards are pictures.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title and theme song, scenario menu (space selects) | OK (menu and song credits are pictures) |
| Character profile frame (profile records) | OK: half-width filler inside the frame, one record per frame line |
| CG mode (all scenarios marked cleared in SAVE.DAT, test image only): scene captions in the lower message box | OK: filler half-width, wrapped at 32 columns |
| Paging: a 6-line caption in that box | OK: 3 lines, waits for space, box cleared, lines 4-6 |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

Scene messages in play come after the action stages, which the boot steps don't clear; they use the same text window and pager as the CG-mode captions.
