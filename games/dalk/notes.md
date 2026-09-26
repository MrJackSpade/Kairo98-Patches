# ♥ Dalk (Alice Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Dalk/Dalk [HD]/Dalk (v1.08) (uncensored).hdi` (sha256 in `strings.json`).
Clearance: no English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Alice Soft **System 2**, engine `ADV.COM` in `DALK/`.
* Opening/extra program `DALK_DEM.COM`: its hard-coded text is extracted as `demo` strings and it gets the same display patch.

Every script page disassembles and reassembles byte for byte (`tools/verify_roundtrip.py`).

## English display (`pc98tl/alice2_font.py`)

* Two letters are packed into one unused Shift-JIS code; the engine draws it as
  one 16-dot cell built from its own ANK font table (A100:0000), so the script
  stays at about one byte per letter.
* Engines that draw straight from the kanji ROM ("direct" shape) get their 16-dot
  routine hooked, and their 24-dot routine too when they have one.
* The hook goes just above the program's old stack top, and the stack moves up
  past it (the DOS memory block grows to match). Nothing else changes size, so
  the patch is memory-neutral. All patch sites are found by byte signature.
* A text run hard-coded in a program that outgrows its place is written, in
  full, after the hook, and the code that loads it is pointed there.

## Script

16943 strings: 61 demo, 4 exe, 825 menu, 15768 msg, 249 name, 20 obj, 16 verb.

♥ by the script-text scan (6 of 16882 strings match the sexual-vocabulary list (4 distinct terms)). The maintainer translates it; 291 strings have English so far.

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
| Opening demo (DALK_DEM.COM) | OK |
| Title menu, message window, command menus | OK |
| Later scene with the status panel | OK; the panel labels (LV / EXP / H.P) are part of the artwork and stay Japanese |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

The 249 `name` entries, the verb/object captions, the engine strings and the title menu were translated by hand earlier (romanization of names without an official source, e.g. セイル = "Seil", is a guess).
