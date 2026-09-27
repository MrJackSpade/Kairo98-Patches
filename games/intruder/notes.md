# ♥ Intruder - Sakura Yashiki no Tansaku (FM Towns conversion) (Alice Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Intruder - Sakura Yashiki no Tansaku (FM Towns conversion)/Intruder - Sakura Yashiki no Tansaku (FM Towns conversion) [FD]/Intruder - Sakura Yashiki no Tansaku (FM Towns conversion).hdm` (sha256 in `strings.json`).
Clearance: no English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Alice Soft **System 1**, engine `ADVINT.COM`.

Every script page disassembles and reassembles byte for byte (`tools/verify_roundtrip.py`).

## English display (`pc98tl/alice1_text.py`)

* System 1 prints on the text layer. Script bytes A0-DD carry English letters,
  and a hook writes each as one ASCII cell in text VRAM with the current
  attribute, so letters are half-width with no glyph work.
* Engines that count the cursor in full-width characters (D.P.S SG) fill each
  character cell with two letters.
* The hook goes just above the program's old stack top, and the stack moves up
  past it (the DOS memory block grows to match). Nothing else changes size, so
  the patch is memory-neutral. All patch sites are found by byte signature.
* A text run hard-coded in a program that outgrows its place is written, in
  full, after the hook, and the code that loads it is pointed there.

## Script

1966 strings: 4 exe, 136 menu, 1727 msg, 71 obj, 28 verb.

Translation and the content classification (♥) are done by the translation model; 1106 of 1966 strings have English so far.

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
| Title, first scenes, message window | OK: half-width letters in the text layer |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
