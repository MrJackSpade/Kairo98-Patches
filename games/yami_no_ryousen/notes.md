# ♥ Yami no Ryousen (Illusion)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Yami no Ryousen/Yami no Ryousen [FD]/Yami no Ryousen (Disk A) [installed].hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

Illusion's tmexec engine, `MAIN.EXE`. Messages are `#nnnnn` ... `$` records in `MSG1.D`, `MSG2.D`, `MSG3.D`, `MSG4.D`, `MSG5.D`, `MSG6.D`, `MSG7.D`, `MSG8.D`, `MSG9.D`, `MSGA.D`, `MSGB.D`; the engine's own Japanese strings (also `$`-terminated) are replaced in place.
The message files are stored as EUC-JP with every byte's top bit flipped; they are decoded for extraction and written back the same way.
The engine is packed with Microsoft EXEPACK; the patch unpacks it (`pc98tl/exepack.py`) and writes it back unpacked.
The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image, as its own HD installer does: every disk's files in `YAMI/`, and the engine's drive prefixes pointed at the hard disk (`b:` to `a:`). The base image is the collection's `Kankin/Kankin [HD]/Kankin.hdi` with its own game removed.

## English display (`pc98tl/illusion_font.py`)

* The message library draws a record one Shift-JIS character at a time from
  the kanji ROM. Its draw loop is rewritten in place (both far calls stay at
  their offsets, so the relocation table still matches): a byte below 80 is
  drawn as the kanji ROM's 8x16 ANK glyph, one column wide, so English is
  half-width and untranslated Japanese still draws as before.
* English is word-wrapped to the message window's width (taken from the
  engine's calls to the message routine); a line the engine wraps by itself
  swallows the line break right after it.
* Messages longer than the box page: the box area is saved on graphics page 1
  (unused by these games), the game waits for a click, the box is restored and
  the text continues at the top. Only messages longer than the box do this.
* The pager lives in a small DOS block of its own (under 1 KB) that an entry
  stub allocates at the top of memory before the game starts; the stub's
  load area is zeroed again afterwards. The game keeps all its other memory.
* The message lookup's end mark changes from `!` to the ^Z every message file
  ends with, so English may use `!`. All patch sites are found by byte
  signature.

## Script

1361 strings: 56 exe, 1305 msg.

Translation and the content classification (♥) are done by the translation model; 0 of 1361 strings have English so far.

## Limits

* Message lines wrap at the message window's width; `\n` forces a break, and a line that already fits is kept as written (spacing included).
* Clickable menus and buttons are hit-tested at the Japanese layout: those records carry a `note` in `strings.json` with the lines and columns to keep.
* Engine strings: their original byte length.

## Not handled

* Text drawn into the artwork (logos, captions, title menus drawn as pictures).
* Installer and driver messages.
* The chapter title cards are pictures.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Hard-disk layout boots (all seven disks' files in YAMI, drive prefixes pointed at A:) | OK |
| Opening scenes (pictures from the former data disks) | OK |
| Main message window | OK: half-width filler inside the frame, 5-line box |
| Following messages | OK |
| Gameplay past the opening scenes, save/load, endings | not yet seen |

The patched game is a hard-disk image; the floppies are not changed.
