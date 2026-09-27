# ♥ D.P.S (Dream Program System) SG (Alice Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `D.P.S (Dream Program System) SG/D.P.S (Dream Program System) SG [FD]/D.P.S (Dream Program System) SG (System disk).hdm` (sha256 in `strings.json`).
Also: `D.P.S (Dream Program System) SG (Fahnen Fliegen).hdm` (scenario disk).
Also: `D.P.S (Dream Program System) SG (Katei Kyoushi wa Suteki na Oshigoto).hdm` (scenario disk).
Also: `D.P.S (Dream Program System) SG (Nobunaga no Inbo).hdm` (scenario disk).
Clearance: no English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Alice Soft **System 1**, engine `ADV.COM`.
* Scenario set `s1` BDISK.DAT on `D.P.S (Dream Program System) SG (Fahnen Fliegen).hdm`.
* Scenario set `s2` BDISK.DAT on `D.P.S (Dream Program System) SG (Katei Kyoushi wa Suteki na Oshigoto).hdm`.
* Scenario set `s3` BDISK.DAT on `D.P.S (Dream Program System) SG (Nobunaga no Inbo).hdm`.

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

10861 strings: 8 exe, 691 menu, 10162 msg.

Translation and the content classification (♥) are done by the translation model; 46 of 10861 strings have English so far.

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
| Boot from the system floppy, scenario floppy in drive 2 | OK |
| Scenario menu, message window (Fahnen Fliegen) | OK: half-width letters in the text layer |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
