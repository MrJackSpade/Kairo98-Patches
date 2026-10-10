# Valentine Kiss - Birth Days 2 (Silky's)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Valentine Kiss - Birth Days 2/Valentine Kiss - Birth Days 2 [HD]/Valentine Kiss - Birth Days 2.hdi` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-09 (`research/clearance.json`).

## Engine

Elf's **AI5** (`SIL.EXE`): the script is 140 `*.MES` files with text, bytecode with a dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every script tokenizes from its start to its end.

The patch works on the game's hard-disk release (the game in `VK/`), which has room for a longer script.  The scripts are in Silky's archives `DISK_A`, `DISK_B`, `DISK_C`, `DISK_D` (`pc98tl/silkdat.py`): a directory encrypted with an XOR running with the file offset and the members stored as they are; an archive with a rebuilt script is laid out anew.

* Nothing in a script is an address, so the scripts are rebuilt with the English in place of the Japanese.
* English is written as the engine's half-width strings (06 ... 06), between commands that set the character width to one column and back to two; the program is not changed.
* Lines are wrapped between words to the text window the script set up (its own commands, or a subroutine it calls), and a new page (a key wait and a clear) starts before a line would run past the window's bottom.
* Menu items are drawn by the menu itself, which takes characters only: their English is written in full-width letters.

## Script

7199 strings: 320 menu items, 6879 messages.

Translation and the content classification (♥) are done by the translation model; 0 of 7199 strings have English so far.

## Limits

* Messages (`m` ids): any length within the script's buffer (below); `\n` starts a new line.  `max_cells` is a line's room in its window (English letters); longer text wraps between words and pages.
* `{X0}` is the hero's name (the name entry's, たいちろう by default) (the script's subroutine 0): keep it in the English.
* `{X7}` is a key wait and a new page (the script's subroutine 7; the English goes on on a fresh page after it): keep it in the English.
* A script runs where it is loaded, at DS:0000 before the engine's variables at DS:E000h: a script with its English may take 57344 bytes.  Each English letter is one byte; a message takes up to twenty bytes more for the commands around it (two where messages follow one another), and a full-width character or a name call in it about twenty more.  A build whose script outgrows its buffer is refused and names the script and its strings.
* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is written full-width, so it holds half as many letters.  Longer ones are cut and reported.
* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.

## Not handled

* Text drawn into the artwork (the title logo, pictures).
* The name entry's character grid stays Japanese: the entry picks characters by their place in it.
* The name entry's frame and its prompt (主人公の名前を入力してください, 名前, おわり) are part of a picture.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| The hard-disk release; the opening lines, the title and its menu | OK: boots; half-width filler, the menu's items as full-width filler cut to their box |
| The first day (the plaza, the hero's self-introduction) | OK: filler wrapped in the bottom text box, pages waiting for a key |
| The name entry | OK: the default name taken with the mouse (the entry's frame and prompt are a picture; its kana grid stays Japanese) |
| Later scenes, the endings | not yet seen |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

Silky's runs Elf's AI5 engine as SIL.EXE; its scripts and pictures are in the DISK_ archives (an XOR-encrypted directory) DISK_A-DISK_D (`pc98tl/silkdat.py`), which the patch lays out anew with the rebuilt scripts. This later SIL.EXE codes text differently from Elf's AI5: dictionary characters from D0h, and C0h-CFh two-byte characters too (game.json version sil2).

The message box (columns 20-59) is set by DEFMAIN.MES, which the game runs first; the scripts after it set none, so game.json default_window gives it.
