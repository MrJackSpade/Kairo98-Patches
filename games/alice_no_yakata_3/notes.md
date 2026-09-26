# ♥ Alice no Yakata III (Alice Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Alice no Yakata III/Alice no Yakata III [HD]/Alice no Yakata III.hdi` (sha256 in `strings.json`).
Clearance: no English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Alice Soft **System 3**, engine `ADV.COM` in `ALICE_Y3/`.
* Scenario set `pat` ALICE_Y3/ADISK.PAT (System 3 (Gakuen King command set) command set).
* Opening/extra program `ADVT2.COM`: its hard-coded text is extracted as `demo` strings and it gets the same display patch.

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

16831 strings: 9 demo, 6 exe, 627 menu, 9978 msg, 6211 name.

♥ by the script-text scan (77 of 13207 strings match the sexual-vocabulary list (9 distinct terms)). The maintainer translates it; 0 strings have English so far.

## Limits

* Message lines wrap to the text window (its width from the script's window commands, or the widest Japanese line); `\n` forces a break.
* Menu items: each item's Japanese width (twice that in letters).
* Hard-coded strings: their original byte length unless moved past the hook.

## Not handled

* Text drawn into the artwork (logos, panel labels).
* Installer and driver messages.
* The Windows version (SYSTEM3.EXE and its DLLs) on the same disk; the patch covers the DOS programs.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot, main menu with 2.5x filler | OK; the menu buttons on the right are drawn as graphics and stay Japanese |
| Message window | OK: filler wraps inside the frame |
| Sub-game (ADVT2.COM + ADISK.PAT) | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
