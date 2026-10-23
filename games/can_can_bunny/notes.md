# Can Can Bunny (Cocktail Soft)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Can Can Bunny/Can Can Bunny [FD]/Can Can Bunny.hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-10-23 (`research/clearance.json`).

## Engine

Cocktail Soft's PC-98 version of its PC-8801 game: one self-booting 2HD floppy (1024-byte sectors).  The boot sector loads the program from track 95; the program decodes itself (a stub at its end).  It is the PC-8801 game's Z80 code ported to x86 by machine, each part running with a 64 KB segment as its 8080 memory: the main part's data comes with the program, the five girls' talks (`CHR1KJ.COM`-`CHR5KJ.COM`, PC-8801 files on the disk) are read into it, and the opening and the ending run in a part of their own.  `pc98tl/cocktail.py` documents the formats and the patch, `pc98tl/cocktail_tl.py` the English.  A build with no English leaves the disk as it is.

* The patch draws a character of two ASCII bytes as their two half-width glyphs side by side (the program's glyph read, and the opening's copy of it).
* The English is kept in a store on the free tracks at the disk's end (124 on), which the patched program reads at its start into memory the game does not use (segment 5200h, above the program's segments and its disk buffer at 5000h), with the helpers.  A translated text's first two bytes become a mark of its English; the program's reads of text (the main part's two loops, its one-byte loop, the opening's) go through a helper that reads the English from the store on a mark and goes on after the original text's end, so no text moves and no address changes.
* The message box (two lines of 50 cells) scrolls a line as the program's own multi-line messages do: the helper takes a line break to the box's second line, or scrolls the box with the program's routine.
* In the opening, a text longer than its rows is shown a page at a time (about 3 seconds a page, or a key); a line the Japanese centred is centred again.
* The PC-8801 files MAIN.COM, USER.COM, GAME.COM, PROLOG.COM and ENDING.COM carry copies of the program's texts; their copies get the same marks.  The player's entries (the name, the age... in USER.COM's defaults and the disk's two saved games) get marks too.
* The disk has no file system, so the machine-translation notice is `MTL_NOTE.TXT` next to the patched image instead of a file on the disk.

## Script

1177 strings: 137 commands, 955 messages, 60 opening and ending pages, 25 words.

Translation and the content classification (♥) are done by the translation model; 0 of 1177 strings have English so far.

## Limits

* Messages (`m` ids): any length; broken between words at 50 letters, the box scrolling for more lines; `\n` a new line.  A Japanese line is a record of its own: the patcher gives each record a line of the English and the last record the rest.  `{N0}`-`{N6}` an entry the player made (the name, the age, the job, the blood type, the personality, the hobby, the type liked): the program puts it where the Japanese has it, so keep it once (it counts 14 letters); a message without it gets the entry after its text, reported by string id.
* Commands (`c` ids): one row of the command panel, `max_cells` letters (12, or 14 for a row the program does not indent); longer runs past the panel's frame and is reported.
* Words (`w` ids): a choice of the player's entries, or the disk's own entries: up to 14 letters.
* Opening and ending pages (`p` ids): broken between words at `max_cells` letters, as many rows a page as the Japanese has (the picture beside a profile takes the rest), more pages shown in turn; `\n` a new line, `{C1}`-`{C7}` a colour.
* The store holds 240 KB on the disk; the marks 4096 English texts.  A build past either is refused.
* English is ASCII; other characters are written as `?` (curly quotes, dashes, `…` and the brackets are made ASCII).

## Not handled

* Text drawn into the pictures (the title, the notebook's names, the status panel's labels).
* The program's own messages for a DOS run of the game ("READ_SEG" and the like: they print with DOS, which the self-booting disk has not).

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Pseudo build boots (np21w, floppy) | OK: the store loads from track 124, the program runs |
| Opening (pseudo) | OK: the story's lines half-width at the bottom, centred again; a two-line text shown as two pages; the five profiles wrapped beside their pictures, a longer one paged |
| Notebook and a girl's room (pseudo) | OK: the box's messages wrapped to its second line, a longer one scrolled; the command panel's rows and submenus; the player's name put mid-line |
| Player's room (pseudo) | OK: its commands and messages |
| Partly translated build | OK: six strings in English (a real sentence wrapped over the box's two lines, a command, the opening's first lines), the rest in Japanese as before |
| Unmodified build | OK: a build with no English is the source image byte for byte |

The ending (the same part as the opening, the same records) and the player's entry screen were not reached in the boot test; their texts go through the same helpers.
