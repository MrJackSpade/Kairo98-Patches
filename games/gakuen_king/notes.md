# ♥ Gakuen King (Alice Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Gakuen King/Gakuen King (FD version) [HD]/Gakuen King (FD version).hdi` (sha256 in `strings.json`).
Clearance: no English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Alice Soft **System 3 (Gakuen King command set)**, engine `GAKUEN.COM` in `ALI_GAKU/`.

Every script page disassembles and reassembles byte for byte (`tools/verify_roundtrip.py`).

## English display (`pc98tl/alice3_font.py`)

* The kana table in the engine is remapped so the script bytes A0-DD become NEC
  half-width ASCII glyphs from the kanji ROM, one byte per letter. Other
  characters are written as 2-byte half-width codes.
* The text drawer advances half a cell after a half-width character and a full
  cell otherwise, so untranslated Japanese still lays out correctly.
* Untranslated text hard-coded in a program has its half-width kana rewritten
  as full-width codes, so it still shows as Japanese.
* The hook goes just above the program's old stack top, and the stack moves up
  past it (the DOS memory block grows to match). Nothing else changes size, so
  the patch is memory-neutral. All patch sites are found by byte signature.
* A text run hard-coded in a program that outgrows its place is written, in
  full, after the hook, and the code that loads it is pointed there.

## Script

19401 strings: 40 exe, 547 menu, 18370 msg, 444 name.

♥ by the script-text scan (84 of 19401 strings match the sexual-vocabulary list (7 distinct terms)). The maintainer translates it; 0 strings have English so far.

## Limits

* Message lines wrap to the text window (its width from the script's window commands, or the widest Japanese line); `\n` forces a break.
* Menu items: each item's Japanese width (twice that in letters).
* Hard-coded strings: their original byte length unless moved past the hook.

## Not handled

* Text drawn into the artwork (logos, panel labels).
* Installer and driver messages.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Status windows, message window, map screen | OK |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
