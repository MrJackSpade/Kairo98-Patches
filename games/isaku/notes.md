# Isaku (Elf)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Isaku/Isaku [HD]/Isaku.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's **AI5** (`AI5.EXE`): the script is 319 `*.MES` files with text, bytecode with a dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every script tokenizes from its start to its end.

The patch works on the game's hard-disk release (the game in `ISAKU/`).  The scripts are in Isaku's archives `ISAKU_A`, `ISAKU_B`, `ISAKU_C`, `ISAKU_D`, `ISAKU_E`, `ISAKU_F`, `ISAKU_G` (`pc98tl/isakuarc.py`): a directory encrypted with a rising XOR and a rotation, the members stored or packed (LZSS); an archive with a rebuilt script is laid out anew, the script stored.

* Isaku's AI5 calls a script's routines by address (system call 2Ah), its scene scripts loaded at 0 below the libraries the game keeps loaded (`DEF.MES`, `DUNCALL.MES`, `ITEMMAIN.MES` at fixed addresses), with no room to grow: so its English is kept out of the scripts (`pc98tl/ai5_far.py`).  A rebuilt script's half-width strings become references (06 7Fh, an offset, 06) into its English, a member `NAME.ENG` beside it in its archive; every call's address is moved with what it points at.
* `AI5.EXE` is unpacked (EXEPACK) and given a helper: loading a script loads its English into a 64 KB segment of its own (the memory the program asks for grows by it), and the half-width string statement draws a reference's letters from there.  English is written as the engine's half-width strings, between commands that set the character width to one column and back to two.
* Lines are wrapped between words to the text window the script set up (its own commands, or a subroutine it calls), and a new page (a key wait and a clear) starts before a line would run past the window's bottom.
* Menu items are drawn by the menu itself, which takes characters only: their English is written in full-width letters.

## Script

15278 strings: 511 menu items, 14767 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 15278 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's buffer (below); `\n` starts a new line.  `max_cells` is a line's room in its window (English letters); longer text wraps between words and pages.
* `{X26}` is the hero's name (the script's subroutine 26): keep it in the English.
* A scene's English (its `.ENG`) may take what the English segment leaves after the libraries' (about 64 KB); a build past it is refused and names the script and its strings.  The scripts themselves only shrink.
* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is written full-width, so it holds half as many letters.  Longer ones are cut and reported.
* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Boot from the hard disk (AI5.EXE unpacked, with its helper; the English segment) | OK: the first menu (colour or monochrome) with its filler items, then the Elf logo |
| Opening (OPENIN.MES): its lines from the English segment | OK: the filler drawn half-width line after line |
| The first scene (a menu at the shoe lockers, then the classroom): the message window | OK: the filler read from the scene's English, wrapped between words at the window's width (62 letters), paged with a key |
| Calls between the scripts (DEF.MES's routines, ITEMMAIN.MES) with the scripts rebuilt | OK: the game goes on from scene to scene |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
