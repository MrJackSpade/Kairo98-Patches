# Bacta (Himeya Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Bacta/Bacta [FD hd9]/Bacta (Disk A).d88` (sha256 in `strings.json`), with `Bacta (Disk B).d88`.
Clearance: no PC-98 English release or announcement found on 2026-10-23 (`research/clearance.json`).

## Engine

Himeya Soft's HMY engine on two self-booting 2HD floppies in Tokuma Shoten's MAKO-DOS: a directory of names and sizes, the files packed one after another from track 1 in its order.  AUTOEXEC.COM loads HMY.BIN (the engine) and runs A-01.COM; the scripts (`*.COM`) are op codes (29 of them) run at address 100h of their segment, with addresses (gotos, ifs, switches, each message's and menu's end) as words.  Text is drawn by MAKOBIOS.BIN (int 40h).  `pc98tl/hmy.py` documents the formats, `pc98tl/hmy_tl.py` the English.  A build with no English leaves the floppies as they are.

* The scripts are walked op by op and written again with their texts at any length, every address moved with what it points at; the floppies' files are packed again.  A-01.COM (the title and the load menu), which holds machine code, keeps its layout: a longer text goes after its end, its op made a goto to it.
* MAKOBIOS.BIN's own path for one-byte characters writes to no plane of the screen; the patch draws two ASCII letters into one 16-dot character with its full-width routine's coloured copy (a helper after the file's end, in memory nothing else uses up to MLF.BIN's segment).
* The message window shows 3 lines of 68 letters; its routine goes on down the screen past them, so the patcher breaks the English between words and puts a wait for a key and a cleared window after each 3 lines (the routine's 01, made to wait for a key and then its release, as the script's own wait after a message does).
* The patched floppies are written as `<output>` (disk A) and `<output> - Bacta (Disk B).d88` (disk B); `MTL_NOTE.TXT` is next to them (DOS cannot read a MAKO-DOS floppy).

## Script

5443 strings: 164 menu choices, 5229 messages, 50 speakers' names.

Translation and the content classification (♥) are done by the translation model; 0 of 5443 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 68 letters, 3 lines a window, more windows shown in turn; `\n` a new line.  The speaker's name before it is a string of its own.
* Speakers' names (`n` ids): up to 16 letters, put before each of their messages with a space.
* Menu choices (`c` ids): up to 12 letters (the menu's boxes); longer runs past the box and is reported by string id.
* A script with its English must fit its room (48,896 bytes, 3000h:0100h up to 3C00h); a build past it is refused and names the script.  The files must fit their floppy.
* English is ASCII; other characters are written as `?` (curly quotes, dashes, `…` and the brackets are made ASCII).

## Not handled

* Text drawn into the pictures (the opening's notice and titles, `*.DAD`, `*.DA1`).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Pseudo build boots (np21w, two floppies) | OK: MAKO-DOS finds every file of the repacked floppies |
| Title menu (pseudo) | OK: the choices half-width in their 12-letter boxes |
| Opening scenes (pseudo) | OK: speakers' names and messages half-width, wrapped to the window's second line |
| Command menus (pseudo) | OK: the five commands and their submenus in their boxes |
| Partly translated build | OK: a long message broken between words over three windows, each waiting for a key; the rest in Japanese as before |
| Unmodified build | OK: a build with no English is the source floppies byte for byte |

Past the first scenes and the first command menus the game was not played in the boot test; every script goes through the same rebuild.
