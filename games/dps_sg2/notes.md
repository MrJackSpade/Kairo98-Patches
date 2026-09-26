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
| Stress test (--pseudo) | **fails: the scenario floppies are full.** Each holds about 1 MB of CG next to the scenario; 2.5x filler needs up to 173 KB more than the disk has (72 KB after dropping the unused X68000/FM Towns/PC-88VA music files) |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

**Open decision:** the scenario floppies cannot hold a long English script. The game's own HDD install (AD.BAT / B_COPY.BAT / SET2.BAT) is the way around it: build a hard-disk image with the system files in `\SG_SET2` and each scenario in `SNR1`-`SNR3`. That needs a bootable DOS HDI to start from, which these floppies don't include.
