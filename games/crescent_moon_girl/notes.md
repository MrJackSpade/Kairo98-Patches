# ♥ Crescent Moon Girl (Alice Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Crescent Moon Girl/Crescent Moon Girl [FD]/Crescent Moon Girl (Disk A).hdm` (sha256 in `strings.json`).
Also: `Crescent Moon Girl (Disk B).hdm` (scenario disk).
Also: `Crescent Moon Girl (Disk C).hdm` (scenario disk).
Clearance: no English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Alice Soft **System 1**, engine `ADV.COM`.
* Scenario set `b` BDISK.DAT on `Crescent Moon Girl (Disk B).hdm`.
* Scenario set `c` CDISK.DAT on `Crescent Moon Girl (Disk C).hdm`.

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

3575 strings: 5 exe, 39 menu, 3410 msg, 99 obj, 22 verb.

♥ by the safety valve: explicit sex scene found while translating (first at m00665) (2026-09-26). Claude translated 330 strings before that point; the rest is the maintainer's to translate.

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
| Gameplay past the opening scenes, save/load, endings | not yet seen |

The collection's `[FD]` set (three DOS floppies with ADV.COM) is the one patched; the `[FD hdb]` D88 dumps of the original disks are not used.
