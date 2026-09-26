# ♥ D.P.S (Dream Program System) SG Set 2 (Alice Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `D.P.S (Dream Program System) SG Set 2/D.P.S (Dream Program System) SG Set 2 [FD] [Set 1]/D.P.S (Dream Program System) SG Set 2 [Set 1] (System disk).hdm` (sha256 in `strings.json`).
Also: `D.P.S (Dream Program System) SG Set 2 [Set 1] (Akai Yoru).hdm` (scenario disk).
Also: `D.P.S (Dream Program System) SG Set 2 [Set 1] (Antique House).hdm` (scenario disk).
Also: `D.P.S (Dream Program System) SG Set 2 [Set 1] (Ikenai Naika Kenshin Futatabi).hdm` (scenario disk).
Clearance: no English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Alice Soft **System 1**, engine `ADV.COM`.
* Scenario set `s1` BDISK.DAT on `D.P.S (Dream Program System) SG Set 2 [Set 1] (Akai Yoru).hdm`.
* Scenario set `s2` BDISK.DAT on `D.P.S (Dream Program System) SG Set 2 [Set 1] (Antique House).hdm`.
* Scenario set `s3` BDISK.DAT on `D.P.S (Dream Program System) SG Set 2 [Set 1] (Ikenai Naika Kenshin Futatabi).hdm`.

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

16452 strings: 5 exe, 738 menu, 15709 msg.

♥ by the safety valve: sexual advances toward a character stated to be 17 found while translating (first at u00049) (2026-09-26). Claude translated 48 strings before that point; the rest is the maintainer's to translate.

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
| Boot the hard-disk image, D.P.S menu, scenario 1 (Antique House) | OK: half-width letters in the text layer |
| Scenarios 2 and 3 (SET2 2 / SET2 3) | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

**Output is a hard-disk image.** The scenario floppies hold about 1 MB of CG each and cannot fit a long English script, so `PATCH.BAT` installs the game the way its own HDD installer does (AD.BAT / B_COPY.BAT): system files in `\SG_SET2`, each scenario in `\SG_SET2\SNR1`-`SNR3`, the installer's `SET2A.ORG` as `\SET2.BAT`, scenario 1 as the default copy. The DOS setup comes from the collection's Super D.P.S hard-disk image (its own game is removed), so that image must be in the collection. It boots straight into scenario 1; to pick another, quit to DOS and type `SET2 2` or `SET2 3` (`SET2 ?` lists them).
