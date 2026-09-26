# ♥ Ambivalenz - Niritsu Haihan (Alice Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Ambivalenz - Niritsu Haihan/Ambivalenz - Niritsu Haihan [HD]/Ambivalenz - Niritsu Haihan.hdi` (sha256 in `strings.json`).
Clearance: no English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Alice Soft **System 3**, engine `ADV.COM`.
* Opening/extra program `AMB_DEMO.COM`: its hard-coded text is extracted as `demo` strings and it gets the same display patch.

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

16226 strings: 80 demo, 6 exe, 409 menu, 15711 msg, 7 name, 1 obj, 12 verb.

♥ by the script-text scan (5 of 16140 strings match the sexual-vocabulary list (3 distinct terms)). The maintainer translates it; 0 strings have English so far.

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
| Opening demo (AMB_DEMO.COM) | OK: English narration; long runs are moved past the hook. Lines are centred by byte count, so English sits slightly right of centre |
| Title menu | OK: items fit the box |
| Message window, first scene | OK |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
