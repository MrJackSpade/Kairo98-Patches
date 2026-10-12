"""Write games/<title>/notes.md for every Alice Soft and Illusion game from the facts.

    python tools/write_notes.py [folder ...]

Sources: game.json, strings.json, research/adult_text.json (the heart mark and
its basis), research/clearance.json, research/boot_tests.json (np21w results)
and research/notes_extra.json (per-game remarks that no file records).
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)


def load(*p, default=None):
    path = os.path.join(ROOT, *p)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


SYSTEM = {1: "System 1", 2: "System 2", 3: "System 3", "gakuen": "System 3 (Gakuen King command set)"}

DISPLAY = {
    "halfkana": """## English display (`pc98tl/alice3_font.py`)

* The kana table in the engine is remapped so the script bytes A0-DD become NEC
  half-width ASCII glyphs from the kanji ROM, one byte per letter. Other
  characters are written as 2-byte half-width codes.
* The text drawer advances half a cell after a half-width character and a full
  cell otherwise, so untranslated Japanese still lays out correctly.
* Untranslated text hard-coded in a program has its half-width kana rewritten
  as full-width codes, so it still shows as Japanese.""",
    "packed": """## English display (`pc98tl/alice2_font.py`)

* Two letters are packed into one unused Shift-JIS code; the engine draws it as
  one 16-dot cell built from its own ANK font table (A100:0000), so the script
  stays at about one byte per letter.
* Engines that draw straight from the kanji ROM ("direct" shape) get their 16-dot
  routine hooked, and their 24-dot routine too when they have one.""",
    "nact": """## English display (`pc98tl/nact_text.py`, `pc98tl/n88basic.py`, `pc98tl/n88disk.py`)

* The game runs on N88-BASIC(86) from N88-DISK BASIC floppies (no DOS). The
  scenario (DISK-A/B/C) is System 1's page format, rebuilt byte for byte.
* Messages are drawn by the machine-code module NAC3.MAC. Its kana table now
  maps the script bytes A1-DE to ASCII, and a hook writes those as single
  half-width cells in text VRAM.
* The engine's own prompts live in the protected BASIC program NACT4 (each
  byte rotated one bit); they are replaced in place with ASCII of the same
  length.
* English makes the scenario files larger than the disks' free space, so the
  patched disks gain track sides 154-163 (cylinders 77-81) where needed:
  their FAT entries were already free, and N88-BASIC reads files there
  normally (tested in np21w). An emulator must accept D88 images with the
  full 164-track table.""",
    "textvram": """## English display (`pc98tl/alice1_text.py`)

* System 1 prints on the text layer. Script bytes A0-DD carry English letters,
  and a hook writes each as one ASCII cell in text VRAM with the current
  attribute, so letters are half-width with no glyph work.
* Engines that count the cursor in full-width characters (D.P.S SG) fill each
  character cell with two letters.""",
}

COMMON = """* The hook goes just above the program's old stack top, and the stack moves up
  past it (the DOS memory block grows to match). Nothing else changes size, so
  the patch is memory-neutral. All patch sites are found by byte signature.
* A text run hard-coded in a program that outgrows its place is written, in
  full, after the hook, and the code that loads it is pointed there."""


ILLUSION_DISPLAY = """## English display (`pc98tl/illusion_font.py`)

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
  signature."""


MES_DISPLAY = """## English display (`pc98tl/illusion_mes.py`)

* The engine draws a byte below 80 from its own 8x16 font (`FONT.DAT`, a full
  ASCII set), so English is half-width with no font work; records may change
  length.
* Its text windows scroll when their rows run out. The patch makes them page
  instead: the window waits for the space key or a left click, clears and
  goes on at the top. The pager sits in the dead scroll code itself, around
  the relocated calls there, so nothing moves and no memory is taken.
* Each message file loads into a 10000-byte buffer (up to the next buffer),
  so the patcher refuses a file that outgrows it."""


FONT24_DISPLAY = """## English display (`pc98tl/illusion_font24.py`)

* The engine draws text two bytes per 24-dot cell: its own 24-dot font for the
  characters it knows, the kanji ROM for the rest.  English is written as
  letter pairs whose first byte (A0-DF) no Shift-JIS lead, font code or
  control code uses, so the engine sends them down its kanji-ROM path.
* Two hooks there (the Shift-JIS to JIS step and the 16x16 fetch) put the
  kanji ROM's two 8x16 ANK letters side by side in the glyph buffer, which the
  engine scales like any kanji: two half-width letters per cell.  Untranslated
  Japanese draws as before.
* The hooks live in a small DOS block of their own (under 1 KB) that an entry
  stub allocates at the top of memory before the game starts; the drawer
  calls them through far pointers kept in data-segment bytes that stay zero
  at run time.  All patch sites are found by byte signature."""


def illusion_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    done = sum(1 for e in strings if e["en"])
    files = sorted({r.split(":")[0] for e in strings if e["kind"] == "msg" for r in e["refs"]})
    out = ["# %s%s (Illusion)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    where = "`%s/%s`" % (cfg["game_dir"], cfg["engine"]) if cfg["game_dir"] else "`%s`" % cfg["engine"]
    out += ["", "## Engine", ""]
    if cfg["encoding"] == "illusion_font24":
        out += ["Illusion's C-compiled engine (%s, packed with Microsoft EXEPACK; the patch unpacks "
                "it with `pc98tl/exepack.py` and writes it back unpacked). Its text is NUL-terminated "
                "Shift-JIS strings in the program itself, replaced in place; strings with line breaks "
                "are DOS messages and stay plain ASCII." % where, "", FONT24_DISPLAY]
    elif cfg["encoding"] == "illusion_mes":
        out += ["Illusion's older engine (`%s`). Messages are records in %s: `10 <index> <group>` "
                "then Shift-JIS text; group 90 is the character profiles (one record per frame "
                "line), A0 a song's lyrics, F4 the disk prompts, the rest scene messages."
                % (where, ", ".join("`%s`" % f for f in cfg["files"])),
                "", MES_DISPLAY]
    else:
        out.append("Illusion's tmexec engine, %s. Messages are `#nnnnn` ... `$` records in %s; "
                   "the engine's own Japanese strings (also `$`-terminated) are replaced in place."
                   % (where, ", ".join("`%s`" % f for f in files)))
        if cfg.get("msg_encoding") == "euc_x80":
            out.append("The message files are stored as EUC-JP with every byte's top bit flipped; "
                       "they are decoded for extraction and written back the same way.")
        if cfg.get("exepack"):
            out.append("The engine is packed with Microsoft EXEPACK; the patch unpacks it "
                       "(`pc98tl/exepack.py`) and writes it back unpacked.")
        if cfg.get("hdd"):
            h = cfg["hdd"]
            out.append("The floppies have no room for a longer script, so the patch lays the game out "
                       "on a DOS hard-disk image, as its own HD installer does: every disk's files in "
                       "`%s/`, and the engine's drive prefixes pointed at the hard disk (%s). The base "
                       "image is the collection's `%s` with its own game removed."
                       % (h["dir"], ", ".join("`%s` to `%s`" % kv for kv in cfg.get("drive_prefix", {}).items()),
                          h["base"].replace("\\", "/")))
        out += ["", ILLUSION_DISPLAY]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, k) for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", ""]
    if cfg["encoding"] == "illusion_font24":
        out += ["* Each string keeps its original byte length: one letter per byte, two per "
                "Japanese character (e.g. a 3-kanji hand name holds 6 letters).",
                "* Strings with a `%`-specifier are printf formats: keep the specifier, and keep the "
                "English on each side of it even in length (see the string's `note`)."]
    elif cfg["encoding"] == "illusion_mes":
        out += ["* Each string has `max_cols` (its window's width: profile lines %d, disk prompts %d, "
                "scene messages %d); longer lines are word-wrapped, `\\n` forces a break."
                % (cfg["cols"].get("90", 0), cfg["cols"].get("f4", 0), cfg.get("default_cols", 70)),
                "* Profile records are one frame line each.",
                "* A message file may grow to %d bytes." % cfg.get("max_file", 10000)]
    else:
        out += ["* Message lines wrap at the message window's width%s; `\\n` forces a break, "
                "and a line that already fits is kept as written (spacing included)."
                % (" (%d columns, set in game.json)" % cfg["window_cols"] if cfg.get("window_cols") else ""),
                "* Clickable menus and buttons are hit-tested at the Japanese layout: those records "
                "carry a `note` in `strings.json` with the lines and columns to keep.",
                "* Engine strings: their original byte length."]
    out += ["", "## Not handled", "",
            "* Text drawn into the artwork (logos, captions, title menus drawn as pictures).",
            "* Installer and driver messages."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for t, r in extra.get(name, {}).get("tests", []):
        out.append("| %s | %s |" % (t, r))
    out.append("| Gameplay past the opening scenes, save/load, endings | not yet seen |")
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


JAST_DISPLAY = """## English display (`pc98tl/jast_game.py`)

* The engine draws single-byte ASCII half-width from its own ANK font, so the
  English needs no font work.  Its character check dropped ASCII punctuation;
  the patch marks bytes 21-3F (but digits and `%`, the name placeholder) as
  single-byte characters in the engine's character class table.
* Scene files are never rearranged: each Japanese text run is overwritten
  with the engine's own goto (`0B 36` + file offset) to its English, appended
  at the end of the file, which ends with a goto back to just after the run.
  Every offset the scene code holds stays valid.
* English lines are padded with spaces so the engine's own wrap (78 columns,
  a speaker's lines hanging after the colon at 62) falls between words.
  Messages longer than the three-line box page as in the original."""


SCM_ROM_DISPLAY = """## English display (`pc98tl/jast_scm.py`)

* The engine draws every character from the kanji ROM.  Its glyph fetch is
  rewritten: a code whose first byte is below 80 is two ASCII letters, drawn
  as the kanji ROM's two 8x16 ANK glyphs side by side in one cell (a far
  routine in a small DOS block from the entry stub); Japanese draws as before.
* English is one stream of lines padded to the window's width, words
  stopping two columns short of the edge; the engine pages a full box itself
  (waits for a click)."""

SCM_TEXT_DISPLAY = """## English display (`pc98tl/jast_scm.py`, `pc98tl/jast_console.py`)

* The engine prints on the PC-98 text layer, so ASCII is half-width already.
* English lines end with the engine's newline; the message window used to
  scroll a full box up, losing its start, so its scroll calls now go to a
  pager: it waits for a click or a key, clears the window and goes on at the
  top.  The pager sits in a zero-filled part of the program that the game
  never touches."""


BOOT_DISPLAY = """## English display (`pc98tl/jast_boot.py`)

* The engine prints on the PC-98 text layer.  Its message and menu draws
  hand each Shift-JIS code to one character routine; both calls now go to a
  helper that draws a code whose first byte is below 80 as two ASCII letters
  in two half-width cells (the engine's own half-width put).  Japanese draws
  as before.
* English lines are wrapped to 72 columns between words and joined by the
  engine's line mark `↓` (builds without it: padded with spaces to the edge,
  where the engine wraps).  The three-line box scrolls a line at a time, so
  the line scrolls in the message draw go through a pager: every third new
  line of a message waits for a key or a left click first.  The helpers sit
  in the unused (zero) tail of the music table, which stays zero in a
  running game.
* A word file with a message table is rebuilt and loaded just below the
  engine, which gives the scene buffer the room the file leaves."""


FONT12_DISPLAY = """## English display (`pc98tl/jast_font12.py`)

* The game draws every character itself from its own font of 12x10 glyphs
  (text is one glyph number a byte).  English is two letters to a cell: a
  letter pair is two bytes, a first byte 09-16 (blank, unused glyph numbers)
  and a second byte numbering the pair.  The message draw's glyph call goes
  to a helper that builds the pair's glyph from a 6x10 font
  (`pc98tl/font6x10.py`) and draws it with the game's own routine; Japanese
  draws as before.
* Lines are padded with blank glyphs to the box edge (46 columns, 47 on the
  first line), where the engine wraps; the line scrolls in the message draw
  go through a pager.  The box shows 2 lines and starts each message empty:
  the pager waits for a key before a line would scroll out unread (at the
  message's first scroll, then every second one).
* The helpers, the 6x10 font and the moved system messages are one new
  block, loaded from a free track of the boot disk by the boot's own table
  load."""


MENU12_DISPLAY = """## English display (`pc98tl/jast_menu12.py`)

* The game draws every character itself from its own font of 12x10 glyphs
  (text is one glyph number a byte).  English is two letters to a cell: a
  letter pair is two bytes, a first byte from glyph numbers that are blank
  and unused by the script, and a second byte numbering the pair.  The
  message draw's and the menu draw's glyph lookups go to helpers that build
  the pair's glyph from a 6x10 font (`pc98tl/font6x10.py`) and hand it to
  the game's own draw; Japanese draws as before.
* Message lines are padded with blank glyphs to the window edge, where the
  engine wraps.  The main box is 3 lines of 40 cells that scroll; its
  scroll goes through a pager, which waits for a key before a scroll once 3
  lines of the message have been shown.  The opening's one-line window wraps
  at its frame, and a wrap there waits for a key, blanks the line and goes
  on in place.
* The helpers and the 6x10 font sit in the unused tail of the font's third
  bank, which the boot already loads.  The nouns move above the engine (the
  boot's engine load grows to cover them); the verbs, system messages and
  the save and load prompts are rebuilt in the word block, which the boot's
  word load reads over the old system messages.
* Scenes are rebuilt with the English; one that outgrows its sectors moves to
  free sectors of the scene disk.
* The title screen's Japanese is rewritten in its text-layer image."""


TYPED_DISPLAY = """## English display (`pc98tl/jast_typed.py`)

* The game draws every character itself from its own 12x10 font (text is
  one glyph number a byte, FF before a second-bank glyph).  English is two
  letters to a cell: a letter pair is two bytes, a first byte from glyph
  numbers that are blank and unused by the script, and a second byte
  numbering the pair.  The message draw's glyph lookup goes to a helper that
  builds the pair's glyph from a 6x10 font (`pc98tl/font6x10.py`); Japanese
  draws as before.
* Message lines are padded with blank glyphs to the box edge (53 cells),
  where the engine wraps.  The box pages itself, waiting for a key every
  fourth scrolled line; its count now starts at a message's first line, so
  no line scrolls out unread.
* The helpers, the 6x10 font, the engine's English strings and the rebuilt
  command panel sit in the engine load's zero tail, which stays zero in a
  running game; the engine's pointers to them follow.
* Scenes are rebuilt with the English and placed again, first fit, in their
  old sectors and the free ones; the scene table follows.
* Typed commands: the word tables get the English words, typed and shown
  with the game's own capitals; the romaji conversion is bypassed so a typed
  letter is stored as the capital itself."""


def jast_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    files = sorted({r.split(":")[0] for e in strings for r in e["refs"]})
    out = ["# %s%s (JAST)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", ""]
    if cfg["encoding"] == "jast_scm":
        out.append("JAST's later scene engine: %d scene files (`*.SCM`), command tables then messages "
                   "ended by `00 00`, found by count (`pc98tl/jast_scm.py`)." % len(files))
        if cfg.get("hdd"):
            out.append("The floppies have no room for a longer script, so the patch lays the game out on a "
                       "DOS hard-disk image (every disk's files in `%s/`, started as the floppy's batch file "
                       "does%s); the base image is the collection's `%s` with its own game removed."
                       % (cfg["hdd"]["dir"], ", with the engine's hard-disk switch `/h`" if cfg["hdd"]["run"][-1].endswith("/h")
                          else "; the engine's select-disk call always picks the hard disk",
                          cfg["hdd"]["base"].replace("\\", "/")))
        elif cfg.get("floppies"):
            out.append("Every floppy's scene files are patched; the output is the full disk set.")
        out += ["", SCM_TEXT_DISPLAY if cfg.get("native_ascii") else SCM_ROM_DISPLAY]
    elif cfg["encoding"] in ("jast_boot", "jast_ribbon", "jast_cosmos"):
        scenes = {r.split(":")[0] for e in strings for r in e["refs"] if r.startswith("scene")}
        out += ["JAST's self-booting engine: the floppies have no file system.  The boot sector loads "
                "the engine (hand-written assembly) from a fixed sector; directory tables in it give each "
                "file's disk, sector and length.  %d scenes hold command tables, then messages read two "
                "bytes at a time and ended by a zero word, found by count; the menu verbs and nouns are "
                "16-byte entries in one more file (`pc98tl/jast_boot.py` documents the layout)." % len(scenes),
                "",
                "The disk tool that built the floppies cut files at a sector boundary and left old sector "
                "contents after each file's end; the extractor stops each scene at the first leftover "
                "fragment, and keeps a scene's cut-off last message as it is.",
                "", BOOT_DISPLAY]
        if cfg["encoding"] == "jast_cosmos":
            out += ["* The oldest engine (`pc98tl/jast_cosmos.py`), on D88 floppies with 256-byte "
                    "sectors: the scenes' command parts and a text blob (the word file and every "
                    "scene's text part, with a header of offsets) are loaded whole into one segment "
                    "at start.  The patch rebuilds the text blob with the English and a new header; "
                    "it may grow to the end of its segment, and moves to free sectors when it no "
                    "longer fits its old ones.  Text is JIS without control words or colour codes; "
                    "every character write goes through the helper."]
        if cfg["encoding"] == "jast_ribbon":
            out += ["* This older build (`pc98tl/jast_ribbon.py`) keeps all scenes in one 64 KB blob "
                    "loaded whole at start, with a 2 KB scene buffer below the word file.  The patch "
                    "writes the rebuilt scenes to free sectors with a table of their places and makes "
                    "the scene copy read the scene from disk instead; the word file moves to the top "
                    "of the space below the engine, so the scene buffer grows to what is left.  Its "
                    "text is JIS like the oldest later build, with no colour codes, and every "
                    "character write (message, menu, string draws) goes through the helper."]
        if any(e["kind"] == "engine" for e in strings):
            out += ["* This is the oldest build: its text is JIS (low byte first), so an English "
                    "letter pair marks its first letter with bit 7.  Its title screen's sound "
                    "prompt is three JIS strings in the engine; they are rewritten in place, and "
                    "the engine's string put draws through the same helper."]
    elif cfg["encoding"] == "jast_font12":
        scenes = {r.split(":")[0] for e in strings for r in e["refs"] if r.startswith("scene")}
        out += ["JAST's typed-command engine on self-booting 2HD floppies (D88, 256-byte sectors, "
                "records 1-19 of each track side).  The boot sector loads the engine, the word "
                "tables, the system messages and the font, and draws the title screen (the sound "
                "setup) from a run-length text-layer image.  %d scenes on the second disk are found "
                "through a table of 6-byte entries in the engine; each is a picture, a command table "
                "and the messages, found by count.  The player types commands, looked up in two "
                "tables of 5-glyph words (`pc98tl/jast_font12.py` documents the layout)." % len(scenes),
                "", FONT12_DISPLAY,
                "* Scenes are rebuilt with the English and written back to back on the second disk "
                "using all 26 records of a track (the engine's reader takes 26 a track on that disk "
                "and still 19 on the boot disk); the scene table follows.",
                "* Typed commands: the word tables get the English words, typed and shown with the "
                "game's own A-Z glyphs, and the key tables give capitals for the letter keys.",
                "* The title screen's Japanese is rewritten in its text-layer image."]
    elif cfg["encoding"] == "jast_typed" and not any(e["kind"] == "word" for e in strings):
        scenes = {r.split(":")[0] for e in strings for r in e["refs"] if r.startswith("scene")}
        out += ["A scene viewer on JAST's first engine (one self-booting 2HD floppy laid out like an "
                "N88-BASIC disk): the player types a digit and the engine shows that scene's picture "
                "and its message; %d scenes come from a table of 4-byte entries in the engine "
                "(`pc98tl/jast_typed.py` documents the layout).  Its message box is 3 lines of 53 "
                "cells, empty at each scene; it pages at every third scrolled line from the first, so "
                "no line scrolls out unread." % len(scenes),
                "", TYPED_DISPLAY]
    elif cfg["encoding"] == "jast_typed":
        scenes = {r.split(":")[0] for e in strings for r in e["refs"] if r.startswith("scene")}
        out += ["JAST's first typed-command engine on one self-booting 2HD floppy laid out like an "
                "N88-BASIC disk (track 0 of 128-byte records, the game reading records 1-16 of the "
                "other tracks).  The boot loads the font and the engine; %d scenes are found through a "
                "table of 6-byte entries in the engine, each a run-length picture, the messages and a "
                "command table.  The player types romaji commands, looked up in two tables of 4-glyph "
                "words; a framed help panel lists the commands (`pc98tl/jast_typed.py` documents the "
                "layout)." % len(scenes),
                "", TYPED_DISPLAY]
    elif cfg["encoding"] == "jast_menu12":
        scenes = {r.split(":")[0] for e in strings for r in e["refs"] if r.startswith("scene")}
        out += ["JAST's menu engine on self-booting 2HD floppies (D88, 256-byte sectors, records 1-19 "
                "of each track side), a sibling of Tenshi II - Minako's engine with commands picked from "
                "menus.  The boot sector loads the engine, the word block and the font block (system "
                "messages, then the font), and draws the title screen (the sound setup) from a "
                "run-length text-layer image.  %d scenes on the second disk are found through a "
                "directory on its first track; each is a header, a command table, the messages (found "
                "by count) and the menus (lists of word numbers).  `pc98tl/jast_menu12.py` documents "
                "the layout." % len(scenes),
                "", MENU12_DISPLAY]
    else:
        out += ["JAST's scene engine (`%s/%s`): %d scene files (`*.OVL`) holding text and scene code "
                "in one stream (`pc98tl/jast_ovl.py` documents the format)." % (cfg["game_dir"], cfg["engine"], len(files)),
                "", JAST_DISPLAY]
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    labels = {"panel": "help panel rows", "title": "title screen", "msg": "scene text", "engine": "engine strings", "word": "menu words", "batch": "batch lines"}
    out += ["", "## Script", "", "%d strings (%s)." % (len(strings), ", ".join(
        "%d %s" % (n, labels.get(k, k)) for k, n in kinds.items())), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    if cfg["encoding"] in ("jast_boot", "jast_ribbon", "jast_cosmos"):
        out += ["", "## Limits", "",
                "* Messages: `{C2}` (name colour), `{C1}` (highlight) and `{C0}` (normal colour) switch "
                "the text colour and are not drawn; `{A<n>}` are animation controls; keep them. `\\n` "
                "starts a new line.  Full-width characters such as 「」 can stay in the English.",
                "* Menu words: 14 letters (7 cells shown); longer ones are cut and reported.",
                "* A rebuilt scene must fit the engine's scene buffer (it loads below the word file); "
                "the patcher refuses a scene that would not.  Grown scenes move to free sectors of "
                "their disk (no table refers to them, one filler byte throughout) and their directory "
                "entry is updated.",
                "* The disks have no file system, so the machine-translation notice is `MTL_NOTE.TXT` "
                "next to the patched images instead of a file on the disk."]
        if any(e["kind"] == "engine" for e in strings):
            out.append("* Engine strings (`e` ids): their original length (2 letters per cell); "
                       "longer ones are cut and reported.")
        out += [
                "", "## Not handled", "",
                "* Text drawn into the artwork (the title logo).",
                "* The engine's other screen strings (save/load, disk prompts) are English already, "
                "drawn full-width, and are left as they are."]
    elif cfg["encoding"] == "jast_font12":
        out += ["", "## Limits", "",
                "* Messages (`m` ids, scene text and the system messages): `\\n` starts a new line.  "
                "Letters and `.,'!?-` are drawn in pairs; digits and characters in the game's font "
                "(Japanese, brackets) use its own glyphs; anything else shows as `?`.",
                "* Command words (`w` ids: `verb:` and `noun:` refs): up to 5 capital letters or "
                "digits, typed by the player; longer ones are cut and reported.",
                "* The engine finds each command word anywhere in the typed line, trying the table's "
                "words in order, so a word must not contain an earlier word of its own table or a word "
                "of the other table (`SEE` inside `SEEK` makes `SEEK` read as `SEE`); the patcher "
                "reports each such pair by string id.",
                "* Title screen (`t` ids): the cells of the Japanese (`max_cells`), two letters each.",
                "* A rebuilt scene must fit the engine's 32 KB scene buffer, and all scenes the second "
                "disk; the patcher refuses a build that breaks either.",
                "* The disks have no file system, so the machine-translation notice is `MTL_NOTE.TXT` "
                "next to the patched images instead of a file on the disk.",
                "", "## Not handled", "",
                "* Text drawn into the artwork (the title logo, pictures)."]
    elif cfg["encoding"] == "jast_typed":
        out += ["", "## Limits", "",
                "* Messages (`m` ids): `\\n` starts a new line.  Letters and `.,'!?-` are drawn in "
                "pairs; digits and characters in the game's font (Japanese, brackets) use its own "
                "glyphs; anything else shows as `?`.",
                "* Command words (`w` ids: `verb:` and `noun:` refs): up to 4 capital letters or "
                "digits, typed by the player; longer ones are cut and reported.  The engine finds a "
                "word anywhere in the typed line, so a word holding another (`SEE` in `SEEK`) also "
                "matches that word's commands; the patcher reports each such pair.",
                "* Help panel rows (`p` ids): `max_cells` cells (2 letters each); longer ones are cut "
                "and reported.",
                "* Engine strings (`e` ids): no length limit.  The save and load prompts are drawn in "
                "pieces, one after another: `eng:033a` (\"DATAを\"), then `eng:0340` (\"ロード\", load) "
                "or `eng:0345` (\"セーブ\", save), then `eng:034a` (\"します。\").",
                "* A rebuilt scene must fit the engine's 24 KB scene buffer, and all scenes the disk; "
                "the patcher refuses a build that breaks either.",
                "* The disk has no file system, so the machine-translation notice is `MTL_NOTE.TXT` "
                "next to the patched image instead of a file on the disk.",
                "", "## Not handled", "",
                "* Text drawn into the artwork (the title logo, pictures) and the \"Presented by "
                "JAST\" glyphs on the title screen."]
    elif cfg["encoding"] == "jast_menu12":
        out += ["", "## Limits", "",
                "* Messages (`m` ids: scene text, the system messages and the engine's save and load "
                "prompts): `{A<n>}` are the talking face's animation controls (not drawn; keep them), "
                "`\\n` starts a new line.  Letters and `.,'!?-` are drawn in pairs; digits and "
                "characters in the game's font (Japanese, brackets) use its own glyphs; anything else "
                "shows as `?`.",
                "* The main box is 40 cells a line and pages by itself (any number of lines).  The "
                "opening's one-line window (the messages of scenes %s and the load prompt) is %d cells; "
                "longer messages there page a line at a time." % (
                    ", ".join(str(n) for n in cfg.get("opening_scenes", [])), cfg.get("opening_cols", 47)),
                "* Menu words (`w` ids: `verb:` and `noun:` refs): 8 cells (16 letters); longer ones "
                "are cut and reported.",
                "* Title screen (`t` ids): the cells of the Japanese (`max_cells`), two letters each.",
                "* A rebuilt scene must fit the engine's 4 KB scene buffer, the nouns the space above "
                "the engine (2816 bytes) and the verbs, system messages and prompts the word block "
                "(2560 bytes); the patcher refuses a build that breaks one.  Grown scenes move to free "
                "sectors of their disk and their directory entry is updated.",
                "* The disks have no file system, so the machine-translation notice is `MTL_NOTE.TXT` "
                "next to the patched images instead of a file on the disk.",
                "", "## Not handled", "",
                "* Text drawn into the artwork (the title logo, pictures)."]
    else:
        out += ["", "## Limits", "",
                "* Speaker lines are written `Name: text` (the name up to 14 columns, or a `%nnn` "
                "placeholder); `\\n` starts a new paragraph.",
                "* A scene file, with its English appended, must fit the engine's 16 KB scene buffer; "
                "the patcher leaves a scene that would not fit in Japanese and reports it.",
                "* Engine strings (`e` ids: menus, prompts, item and character names, bonus texts) are "
                "rewritten in place in the program (`pc98tl/engine_strings.py`): their original byte "
                "length, two letters per full-width cell; longer ones are cut and reported."]
        if cfg["encoding"] == "jast_scm":
            out += ["* Noun table words (`w` ids, NTBL.BIN: the objects of the command menus): 16 letters.",
                    "* Batch files' Japanese echo lines (`b` ids) are rewritten as they are."]
        out += ["", "## Not handled", "",
                "* Text drawn into the artwork (logos, menus drawn as pictures).",
                "* The name-entry character grids stay Japanese: the engine picks characters from them "
                "by position.",
                "* Driver messages (mouse and music drivers)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for t, r in extra.get(name, {}).get("tests", []):
        out.append("| %s | %s |" % (t, r))
    out.append("| Gameplay past the opening scenes, save/load, endings | not yet seen |")
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


ADV98V_DISPLAY = """## English display (`pc98tl/adv98v_tl.py`)

* The engine draws ASCII strings (`21 ... 00`) half-width itself, so English
  is written as ASCII strings in place of the Japanese text runs; the
  scripts are rebuilt with them (no offset table refers into a script).
* The engine wraps at the text frame's right edge even inside a word, and
  does not scroll (a fourth line of a 3-line frame draws over the first).
  So messages are broken between words to the frame's width (`A6` gives it
  in half-width columns) and cut into pages of its line count; between
  pages goes a wait and the file's message-end procedure call, as between
  the original messages.
* Menu items and text in one-line frames keep their Japanese width.
* Pieces of text with only colour, speed, pause or fade commands between
  them are one string; the English replaces all of it, without those
  effects."""


def adv98v_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    files = sorted({r.split(":")[0] for e in strings for r in e["refs"] if r.split(":")[0].upper().endswith((".MES", ".MEC"))})
    # (another maker's game on the engine: Elf's on its ADVH)
    other = {"elf": "Elf"}.get(cfg["key"].split(".zip/")[0])
    out = ["# %s%s (%s)" % ("♥ " if heart else "", cfg["title"],
                            "%s, on Cocktail Soft / Fairytale's engine" % other if other
                            else "Cocktail Soft / Fairytale"), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    has = {e["kind"] for e in strings}
    display = ADV98V_DISPLAY if cfg.get("engine") != "advh" else ADV98V_DISPLAY.replace(
        "* The engine draws ASCII strings (`21 ... 00`) half-width itself, so English\n"
        "  is written as ASCII strings in place of the Japanese text runs; the\n"
        "  scripts are rebuilt with them (no offset table refers into a script).",
        "* English letters are written as `85 xx` in place of the Japanese text runs\n"
        "  (see the engine note above); the scripts are rebuilt with them (no offset\n"
        "  table refers into a script).")
    names = any(r.startswith("TCM/NAMEWIND") for e in strings for r in e["refs"])
    subs = sorted({f.split("/")[0] for f in files if "/" in f})
    main = ", ".join(x for x, ext in (("`MES/*.MES`", ".MES"), ("`*.MEC`", ".MEC"))
                     if not subs or any("/" not in f and f.upper().endswith(ext) for f in files))
    where = main if not subs else "%s%sin the script folders %s, named `FOLDER/FILE` in the refs" % (
        main, ", and " if main else "", ", ".join("`%s/`" % s for s in subs))
    if cfg.get("parts"):
        # (games of their own in folders: each one's scripts, not script folders)
        where = "each game's `START.MES`: the main game's, and in its folders %s" % ", ".join(
            "`%s/`" % s for s in cfg["parts"])
    out += ["", "## Engine", "",
            "ides' Adv98V script engine (%s), %s: %d scripts with text (%s) in its bytecode "
            "(`pc98tl/adv98v.py` documents it%s).  Every script tokenizes and "
            "rebuilds byte for byte." % ("`%s/`" % cfg["game_dir"] if cfg["game_dir"] else "at the disk's root",
                                         "on a hard-disk image" if cfg.get("hdd") is None and cfg["image"].lower().endswith(".hdi")
                                         else "on its boot floppy, patched in place" if not cfg.get("hdd")
                                         else "on %d floppies" % (1 + len(cfg["hdd"]["disks"])), len(files), where,
                                         "; this build has the later engines' extended opcodes" if cfg.get("extraop") else "")
            + (("  The procedure table holds %d slots of %d bytes (read off the engine's memory)."
                % (cfg["proc_slots"], cfg["proc_slot"])) if "proc_slot" in cfg else
               ("  The procedure table was not measured, so a procedure may not grow: text in a procedure "
                "(`n` ids) keeps its Japanese byte length." if "inline" in has else
                "  No procedure holds text, so no procedure grows.")),
            "", display]
    if cfg.get("engine") == "advh":
        out[out.index(display):out.index(display)] = [
            "This is ADVH, the engine before Adv98V (`ADVH.EXE`, in most games run by `ADVSHELL.COM`): the same "
            "bytecode, but no ASCII string command, and every character drawn as a 16x16 glyph.  The "
            "patch adds half-width letters to the program (`pc98tl/advh.py`): each English letter is "
            "written as `85 xx` (xx its ASCII code), which the program draws from the BIOS's 8x16 "
            "font one column wide and steps the cursor one column on; a packed program is unpacked, patched "
            "and packed again with its own EXEPACK unpacker.  The disk-change command (wait for disk X "
            "in the floppy drive) goes straight on.  Messages page with the key wait `81 90`, which "
            "clears the box: a message longer than the box goes on after a key on a fresh page.", ""]
    if cfg.get("hdd"):
        out[out.index(display):out.index(display)] = [
            ("This game's mahjong is a separate engine (`MAH4.OVL`) with no Japanese text of its own. "
             if cfg["game_dir"] == "JANKI" else "") +
            "The floppies have no room for a longer script, so the patch lays the game out on a DOS "
            "hard-disk image (%s's files in `%s/`, with the scripts' drive letters taken off "
            "their file names, started as the floppy's boot does); the base image is the collection's "
            "`%s` with its own game removed." % ("the main disk" if cfg["hdd"].get("disk_dirs") else "every disk",
                                                 cfg["hdd"]["dir"], cfg["hdd"]["base"].replace("\\", "/"))
            + "".join("  %s's copy of %s is left out: another disk holds it differently, and the scripts load "
                      "only that one." % (disk, ", ".join("`%s`" % f for f in files))
                      for disk, files in cfg["hdd"].get("unused", {}).items())
            + ("  The data collections are games of their own, each with its engine and start script, "
               "so each disk goes into its own folder: %s.  The hard disk starts the main game; a "
               "collection is started from DOS with `cd \\%s\\FOLDER` and `ADVH START.MES`.  Their "
               "scripts' refs are `FOLDER/START.MES:n`, and a string the games share lists every "
               "game's refs." % (", ".join("`%s/%s/` (%s)" % (cfg["hdd"]["dir"], sub, disk.rsplit("/", 1)[-1])
                                         for disk, sub in cfg["hdd"]["disk_dirs"].items()), cfg["hdd"]["dir"])
               if cfg["hdd"].get("disk_dirs") else ""), ""]
    if "inline" in has:
        out.append("* A message after a speaker's name tag (a procedure that ends its line) starts on the "
                   "frame's second line.")
    out.append("* Procedures are read for what they print: a name tag ends its line, a fixed text (an "
               "ellipsis) or a name shown from a variable (%s) moves along it, a line break moves down, "
               "and a frame or text reset starts a fresh page.  A message continues the page of the text "
               "before it, wrapped from where that left off, with room left for what is printed after it."
               % ("up to %d columns, the name entry's limit" % cfg.get("name_cols", cfg.get("name_insert", {}).get("cols", 0))
                  if cfg.get("name_cols") or cfg.get("name_insert") else "its Japanese width"))
    if cfg.get("name_insert"):
        out.append("* The hero's name, printed mid-message by a procedure call with its inline flag set, "
                   "leaves room for the longest name the name entry takes (%d columns), and the text after "
                   "it carries on the same line." % cfg["name_insert"]["cols"])
    if "proc_slot" in cfg:
        out.append("* Procedures (`B9 n`) are copied into fixed slots of a table (one per number, run on "
                   "into free slots after it); a build that would overrun one is refused.")
    if "var" in has or "engine" in has:
        what = " and ".join(x for x, k in (("string variables' values (`@n='...'` arguments)", "var"),
                                           ("the strings in the engine's programs", "engine")) if k in has)
        out.append("* %s%s are rewritten in place." % (what[0].upper(), what[1:]))
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    labels = {"msg": "messages", "item": "menu items", "inline": "name tags (procedure text)",
              "var": "string variable values", "engine": "program strings", "file": "text file lines"}
    out += ["", "## Script", "", "%d strings (%s)." % (len(strings), ", ".join(
        "%d %s" % (n, labels.get(k, k)) for k, n in kinds.items())), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids): any length; `\\n` starts a new line.  Full-width characters can stay "
            "in the English; `{Uxxxx}` stand for the game's own characters (hearts, symbols) and are "
            "written back as they are."]
    if cfg.get("name_insert"):
        out.append("* The hero's name is printed between two message runs: the run before it ends where "
                   "the name starts (end it with a space if one should come before the name), the run "
                   "after it starts right after the name.")
    if cfg.get("page_break") == "8190":
        out.append("* This old build ends each message with a key wait (`81 90`) that clears the box, so "
                   "pages are split with it (in a one-line box, a line at a time).")
    if cfg.get("keep_flag"):
        out.append("* Where the script marks a message end to keep the page (a register set before the "
                   "message-end call), the next message goes on from where the last one ended, on the "
                   "same line: end the first with a space if one should come between them.")
    if cfg.get("script_room"):
        out.append("* A script runs from the engine's script buffer, which holds %d bytes (read off its "
                   "memory): a file that would outgrow it with the English is refused and named, so keep "
                   "the longest scripts' English about as long as the Japanese." % cfg["script_room"])
    if cfg.get("proc_fullwidth"):
        out.append("* This engine hangs on an ASCII string inside a procedure, so text kept in procedures "
                   "(the speakers' name tags, `n` ids) is written in full-width letters, each two columns "
                   "wide and two bytes long; a tag grows only into its procedure's free slots, so keep tags "
                   "about as long as the Japanese.")
    if cfg.get("menu_fullwidth"):
        out.append("* This engine draws menus from Shift-JIS only (an ASCII string in a menu crashes it), "
                   "so menu items are written in full-width letters: `max_cells` letters each, cut and "
                   "padded.")
    out.append("* Menu items (`i` ids), messages in one-line frames and text placed at a fixed spot on "
               "the screen (menu buttons, labels): twice their `max_cells` in letters; longer ones are "
               "cut and reported.")
    if any(r.split(":")[0].upper().endswith(".MEC") for e in strings for r in e["refs"]):
        out.append("* Strings in `*.MEC` files: the engine loads these into one shared buffer, each at its "
                   "own offset, so a `.MEC` file can only grow up to the next file's offset (or, for the "
                   "top one, as far as the original game's loads reach; past that the buffer meets the "
                   "engine's stack), often only a few dozen bytes past its Japanese.  The patcher refuses "
                   "a build where one outgrows its room and lists that file's strings.")
    if "inline" in has:
        out.append("* Name tags (`n` ids) live in procedures, and a procedure may only grow into the free "
                   "slots after its own%s, so the tags of one procedure share a few bytes beyond the "
                   "Japanese: keep names about as long as the Japanese ones.  The patcher refuses a build "
                   "that overruns a slot and names that procedure's strings."
                   % (" (%d bytes a slot)" % cfg["proc_slot"] if "proc_slot" in cfg else ""))
    if "var" in has:
        out.append("* String variables (`v` ids): the Japanese's byte length (twice `max_cells` in "
                   "letters)%s.  Longer ones are refused.  `'` and `\"` are written full-width (they "
                   "would end the script's quoting)." % (
                       "; the hero's default name parts (offered again by the name entry) up to %d letters"
                       % cfg["name_insert"]["cols"] if cfg.get("name_insert") else ""))
    if cfg.get("text_files") and cfg.get("text_fullwidth"):
        out.append("* Text file lines (`t` ids: %s, shown as they are, e.g. the opening roll): the files hold "
                   "Shift-JIS only (no half-width letters), so they are written in full-width letters, each "
                   "line up to `max_cells` letters (its Japanese byte length), as the file is loaded into a "
                   "fixed place in memory; longer ones are cut and reported."
                   % ", ".join("`%s`" % f for f in cfg.get("text_files", [])))
    elif cfg.get("text_files"):
        out.append("* Text file lines (`t` ids: %s, shown as they are, e.g. the opening roll): each line "
                   "up to its Japanese byte length (twice `max_cells` in letters), as the file is loaded "
                   "into a fixed place in memory; longer ones are cut and reported."
                   % ", ".join("`%s`" % f for f in cfg.get("text_files", [])))
    if "engine" in has and cfg.get("program_fullwidth"):
        out.append("* Program strings (`e` ids: %s): the module's text is Shift-JIS only, so they are "
                   "written in full-width letters, up to `max_cells` letters each, in place; longer ones are cut "
                   "and reported." % ", ".join("`%s`" % f for f in cfg.get("program_files", [])))
    elif "engine" in has:
        out.append("* Program strings (`e` ids): twice `max_cells` in letters, written in place; longer "
                   "ones are cut and reported.")
    if cfg.get("table_files"):
        out.append("* String tables (`t` ids from %s, e.g. a list box's lines or the load window's notes): "
                   "each file is a table of offsets to its strings, rebuilt with the English; `\\n` is a line "
                   "break, up to `max_cells` %s a line (the widest Japanese line).  The strings of a file share "
                   "its bytes, as it is loaded into a buffer of its size: where the English would outgrow the "
                   "file, the last strings stay Japanese and are reported." % (
                       ", ".join("`%s`" % f for f in cfg["table_files"]),
                       "full-width letters" if cfg.get("table_fullwidth") else "cells (two half-width letters each)"))
    if cfg.get("data_files") and cfg.get("engine") == "advh":
        out.append("* The hero's default name (an `e` id from %s): up to `max_cells`%s; that is as long a name "
                   "as the name entry takes from the player, or the Japanese name's length where the game has "
                   "no name entry.  Longer names are cut and reported.  The file pairs the name with the "
                   "placeholder `＊＊＊`, which the engine swaps for the name as it reads a message (the name "
                   "entry writes the name the player types under the same placeholder): keep `＊＊＊` in the "
                   "English of a message where the name goes." % (
                       ", ".join("`%s`" % f for f in cfg["data_files"]),
                       " full-width letters (the engine reads the name as message text)"
                       if cfg.get("data_fullwidth") else ", twice that in half-width letters"))
    elif cfg.get("data_files"):
        out.append("* Names in data files (`e` ids from %s): written in place, each up to its field's room "
                   "(`max_cells`%s: the name with the spaces around it and any `＠` padding after it), a "
                   "shorter one padded as the field was (`＠`, or the NUL or FF byte ending it); longer ones are "
                   "cut and reported." % (
                       ", ".join("`%s`" % f for f in cfg["data_files"]),
                       " full-width letters, as the files hold these names in Shift-JIS only"
                       if cfg.get("data_fullwidth") else ", twice that in half-width letters"))
    for fix in cfg.get("advh_fixes", []):
        out.append("* `ADVH.EXE` is changed in its unpacked program (a byte signature, the same length): %s."
                   % fix["why"])
    for fix in cfg.get("program_fixes", []):
        out.append("* `%s` is patched in place (a byte signature, the same length): %s." % (fix["file"], fix["why"]))
    out += ["", "## Not handled", "", "* Text drawn into the artwork (the title logo, pictures)."]
    if names:
        out.append("* The name window's character tables stay Japanese: the engine picks characters from "
                   "them by position (its English-letter table lets the player type an English name).")
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for t, r in extra.get(name, {}).get("tests", []):
        out.append("| %s | %s |" % (t, r))
    out.append("| Gameplay past the opening scenes, save/load, endings | not yet seen |")
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def ai5_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "item": "menu items", "label": "labels", "record": "names in data tables"}
    ext = cfg.get("script_ext", ".MES").upper()
    files = sorted({r.split(":")[0] for e in strings for r in e["refs"] if r.split(":")[0].upper().endswith(ext)})
    h = cfg.get("hdd")
    maker = "Silky's" if cfg["key"].startswith("Silkys.zip/") else "Elf"
    out = ["# %s%s (%s)" % ("♥ " if heart else "", cfg["title"], maker), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Elf's **%s** (`%s`): the script is %d `*%s` files with text, bytecode with a "
            "dictionary of the file's most frequent characters; `pc98tl/ai5.py` documents it.  Every "
            "script tokenizes from its start to its end." % (
                "AI4" if cfg.get("version") == "ai4" else "AI5",
                cfg.get("program", cfg.get("version", "ai5").upper() + ".EXE"),
                len(files), ext), "",
            ("The floppies use Elf's own file system (ELFDOS, `pc98tl/elfdos.py`) and have no room for a "
             "longer script, so the patch lays the game out on a DOS hard-disk image the way its own "
             "hard-disk installer does: every disk's files in `%s/`, started with `%s`.  The base image is "
             "the collection's `%s` with its own game removed." % (
                 h["dir"], " / ".join(h["run"][2:]), h["base"].replace("\\", "/")) if h else
             ("The patch works on the game's hard-disk release (the game in `%s/`)." if cfg.get("version") == "isaku"
              else "The patch works on the game's hard-disk release (the game in `%s/`), which has room for a "
              "longer script.") % cfg["game_dir"]) + (
                ("  The scripts are in Silky's data archives %s (`pc98tl/silkdat.py`): a directory "
                 "encrypted with a chained XOR and the members stored as they are; an archive with a rebuilt "
                 "script is laid out anew." if cfg.get("archive_format") == "silkdat" else
                 "  The scripts are in Silky's archives %s (`pc98tl/silkdat.py`): a directory encrypted "
                 "with an XOR running with the file offset and the members stored as they are; an archive with "
                 "a rebuilt script is laid out anew." if cfg.get("archive_format") == "silkdisk" else
                 "  The scripts are in Isaku's archives %s (`pc98tl/isakuarc.py`): a directory encrypted with "
                 "a rising XOR and a rotation, the members stored or packed (LZSS); an archive with a rebuilt "
                 "script is laid out anew, the script stored." if cfg.get("archive_format") == "isaku" else
                 "  The scripts are in Kakyuusei's archives %s (`pc98tl/kakyuarc.py`): a directory of 2300 "
                 "slots, each byte rotated and XORed, the scripts packed (LZSS); an archive with a rebuilt "
                 "script is laid out anew, the script packed again." if cfg.get("archive_format") == "kakyu" else
                 "  The scripts are in Elf's archives %s (`pc98tl/elfarc.py`): the archive holds name hashes "
                 "only, so the scripts are found from `start.mes` through the script names the scripts "
                 "give; a rebuilt script is compressed again and the archive laid out anew.") % ", ".join(
                    "`%s`" % f for f in cfg["archives"]) if cfg.get("archives") else ""), "",
            ("* Nothing in a script is an address, so the scripts are rebuilt with the English in place "
             "of the Japanese." if cfg.get("version") != "isaku" else
             "* Isaku's AI5 calls a script's routines by address (system call 2Ah), its scene scripts "
             "loaded at 0 below the libraries the game keeps loaded (`DEF.MES`, `DUNCALL.MES`, "
             "`ITEMMAIN.MES` at fixed addresses), with no room to grow: so its English is kept out of the "
             "scripts (`pc98tl/ai5_far.py`).  A rebuilt script's half-width strings become references "
             "(06 7Fh, an offset, 06) into its English, a member `NAME.ENG` beside it in its archive; every "
             "call's address is moved with what it points at."),
            ("* `AI5.EXE` is unpacked (EXEPACK) and given a helper: loading a script loads its English into "
             "a 64 KB segment of its own (the memory the program asks for grows by it), and the half-width "
             "string statement draws a reference's letters from there.  English is written as the engine's "
             "half-width strings, between commands that set the character width to one column and back "
             "to two." if cfg.get("version") == "isaku" else
             "* English is written as the engine's half-width strings (06 ... 06), between commands that "
             "set the character width to one column and back to two; the program is not changed."
             if cfg.get("version", "ai5") != "ai4" else
             "* This engine draws no half-width strings, so English is written in the PC-98's half-width "
             "two-byte letters (85 40-9E, the space 86 40), between commands that set the character "
             "width to one column and back to two; each rebuilt script's dictionary is laid out again "
             "so its most frequent letters take one byte; the program is not changed."),
            "* Lines are wrapped between words to the text window the script set up (its own commands, "
            "or a subroutine it calls), and a new page (a key wait and a clear) starts before a line "
            "would run past the window's bottom." + (
                "  A script that never waits for a key (the opening, timed to its music) gets no new "
                "page: its English is cut to its window's lines (reported)." if cfg.get("no_pages") else ""),
            "* Menu items are drawn by the menu itself, which takes characters only: their English is "
            "written in full-width letters.",
            "", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids): any length within the script's buffer (below); `\\n` starts a new "
            "line.  `max_cells` is a line's room in its window (English letters); longer text wraps "
            "between words and pages.",
            ] + ["* `{X%s}` is %s (the script's subroutine %s%s): keep it in the English." % (
                n, c.get("note", "a subroutine call"), n,
                "; the English goes on on a fresh page after it" if c.get("page") else "")
                for n, c in cfg.get("calls", {"26": {"note": "the hero's name"}}).items()] + [
            ("* A scene's English (its `.ENG`) may take what the English segment leaves after the "
             "libraries' (about 64 KB); a build past it is refused and names the script and its strings.  "
             "The scripts themselves only shrink." if cfg.get("version") == "isaku" else
             "* A script runs where it is loaded, at DS:0000 before the engine's variables at DS:%04Xh: "
             "a script with its English may take %d bytes.  Each English letter is one byte; a message "
            "takes up to twenty bytes more for the commands around it (two where messages follow one "
            "another), and a full-width character or a name call in it about twenty more.  A build "
            "whose script outgrows its buffer is "
            "refused and names the script and its strings." % (cfg.get("script_room", 0xE000),
                                                              cfg.get("script_room", 0xE000))),
            "* Menu items (`i` ids): `max_cells` is the Japanese item's width in cells; the English is "
            "written full-width, so it holds half as many letters.  Longer ones are cut and reported.",
            "* Labels (`l` ids: text the script puts in a slot of its own, such as the name entry's "
            "buttons): one line, `max_cells` half-width letters; longer ones are cut and reported.",
            ] + ["* Names in data tables (`r` ids: %s): `max_cells` full-width letters, the room of "
                 "their fixed fields (%d bytes, ended by a NUL); longer ones are cut and reported." % (
                     ", ".join("`%s`" % r["file"] for r in cfg["records"]), cfg["records"][0]["size"])
                 for _x in [0] if cfg.get("records")] + [
            "", "## Not handled", "",
            "* Text drawn into the artwork (the title logo, pictures).",
            "* The name entry's character grid stays Japanese: the entry picks characters by their "
            "place in it."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for t, r in extra.get(name, {}).get("tests", []):
        out.append("| %s | %s |" % (t, r))
    out.append("| Gameplay past the opening scenes, save/load, endings | not yet seen |")
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def gip_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "item": "menu items", "var": "string variable values"}
    files = sorted({r.split(":")[0] for e in strings for r in e["refs"]})
    out = ["# %s%s (Cocktail Soft)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Ides' **gip** 2.08 (\"Gun'sHip\"): `PQ.OV1` (the gip system) runs `PQ.OVL` (the script "
            "interpreter and the game's own commands) with the frame file `PQ.OV2`, all in `%s/` on the "
            "game's hard-disk release.  The script is bytecode in `EVT/*.EVT` (%d files with text); "
            "`pc98tl/gip.py` documents it.  Every command has a fixed length or a known form; the "
            "disassembler follows the code from each script's start (and from the entries the game's "
            "commands start) and reaches every Japanese string." % (cfg["game_dir"], len(files)), "",
            "* Messages, menu items and string variable values are reached only through the commands' "
            "pointers, so the English is laid out in the bytes the Japanese leaves free and after the "
            "script's end, and the pointers are moved to it; the code does not move.",
            "* The game's text driver draws ASCII half-width, so English is written as ASCII; the "
            "program is not changed.",
            "* Lines are wrapped between words to the window the script opened, a letter short of its "
            "width (a letter in the last column wraps the line itself), and a new page (key wait, "
            "clear) starts before a line would scroll the window.",
            "", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids): any length; `\\n` starts a new line.  `max_cells` is the line's room "
            "in its window (English letters); longer text wraps between words and pages.",
            "* `{Xn}` in a message is string variable n, which the script sets to a name, a speaker's name "
            "and opening bracket, an indent or a page break (the string's `note` says which): keep it in "
            "the English; the variable's own value is a `v` id.",
            "* Menu items (`i` ids): `max_cells` letters, the menu window's width; longer ones are cut and "
            "reported.",
            "* String variable values (`v` ids): up to 64 bytes (64 letters).",
            "* A script may not outgrow its buffer: the main one holds 20000 bytes, the second one "
            "(for the scripts the others load and call) 7003.  A script's English may take the bytes "
            "of all its Japanese strings and the room left in its buffer; a build whose English does "
            "not fit is refused and names the script and its strings.  The scripts in the second buffer "
            "have the least room: in some, the English should take about as many bytes as the Japanese.",
            "", "## Not handled", "",
            "* Text drawn into the artwork (the title logo, pictures).",
            "* The gip system's own messages in `PQ.OV1` (option, memory and disk errors) and the "
            "floppy release's disk prompts in `PQ.INI`; the hard-disk release does not ask for disks."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for t, r in extra.get(name, {}).get("tests", []):
        out.append("| %s | %s |" % (t, r))
    out.append("| Gameplay past the opening scenes, save/load, endings | not yet seen |")
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def silky_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "var": "string variable values", "engine": "program strings"}
    files = sorted({r.split(":")[0] for e in strings for r in e["refs"] if r.split(":")[0].upper().endswith(".MES")})
    h = cfg.get("hdd")
    prog = cfg.get("program", "SL.EXE")
    arcs = sorted({r.split("/")[0] for e in strings for r in e["refs"] if "/" in r.split(":")[0]})
    left, right = cfg.get("message_window", (17, 62))
    out = ["# %s%s (Silky's)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Silky's (Elf's) **General Message system-1** (`%s`): %d `*.MES` scripts with text, in "
            "the archives %s (one per floppy)%s; `pc98tl/silky.py` documents the archive, the compression "
            "and the bytecode, and `pc98tl/silky_tl.py` the English.  Every script tokenizes from its "
            "bytecode's start to its end, every address in it lands on a statement, and each rebuilds byte "
            "for byte." % (prog, len(files), ", ".join("`%s`" % a for a in arcs),
                           ", each compressed" if h else ", stored as they are"), "",
            ("The floppies have no room for a longer script, so the patch lays the game out on a DOS "
             "hard-disk image the way its own installer does (every disk's files in `%s/`, started with "
             "`%s`; one disk's `DISKNO` kept); the base image is the collection's `%s` with its own game "
             "removed." % (h["dir"], " / ".join(h["run"][2:]), h["base"].replace("\\", "/")) if h else
             "The patch works on the game's hard-disk release (the game in `%s/`)." % cfg["game_dir"]), "",
            "* The scripts hold addresses (jumps, loops, cases, calls), so a rebuilt script has them moved "
            "with its statements.",
            "* English is a text statement in the engine's mode 2: single-byte letters, drawn half-width "
            "(8x16) by the engine itself, which the game uses for its half-width katakana sound effects; "
            "the program's drawing is not changed.",
            "* Lines are wrapped between words to the text window the script set (46h; the message box "
            "is columns %d-%d, %d letters%s), with the engine's new line (04); the engine starts a new page "
            "by itself when a line would pass the window's bottom." % (
                left, right, right - left + 1,
                ", set by the system library and measured on screen" if "message_window" in cfg else ""),
            "* A changed script is %s and its archive laid out anew." % (
                "compressed again" if h else "stored as it is, like the game's own"),
            "", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids): any length within the script's room (below); `\\n` starts a new line. "
            "`max_cells` is a line's width in its window (letters); longer text wraps between words and "
            "pages.  A message that ends with a new line in the Japanese (a speaker's tag) should end "
            "with one too.  Letters only: the engine draws ASCII and half-width katakana in this mode, so "
            "anything else (full-width characters, accented letters) is written as `?`.",
            "* `{N}` is where the script prints a string variable (4Bh: the hero's name, from the name "
            "entry): keep it in the English, in order; the patcher keeps 12 columns for it.",
            "* A script is loaded at SS:0000 and the system library (`SYSTEM.MLL`) after it, at SS:%04Xh "
            "(read off `SL.EXE`): a script with its English may take that many bytes.  Each English letter "
            "is one byte, a Japanese character one or two, so the longest scripts must keep their English "
            "about as long in bytes as the Japanese; a build whose script outgrows its room is refused "
            "and names the script and its strings." % 0x7918,
            "* String variable values (`v` ids: names and menu labels the script keeps in a variable): "
            "`max_cells` letters (a string variable's 32-byte slot), an even number of them (a space is "
            "added); longer ones are cut and reported.",
            "* Program strings (`e` ids: `%s`): `max_cells` x 2 letters, written in place; longer ones are "
            "cut and reported." % "`, `".join(cfg.get("program_files", [])),
            "", "## Not handled", "",
            "* Text drawn into the artwork (the title logo, pictures).",
            "* The name entry's character grid stays Japanese: the entry picks characters by their "
            "place in it."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    out.append("| Gameplay past the opening scenes, save/load, endings | not yet seen |")
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def _cells_range(strings, kind):
    cells = sorted({e["max_cells"] for e in strings if e["kind"] == kind})
    if not cells:
        return "none"
    return "%d" % cells[0] if len(cells) == 1 else "%d to %d by table" % (cells[0], cells[-1])


def adl5_engine(cfg, files, tables, prog):
    helpers = cfg.get("program_files", [])
    v98 = cfg.get("version") in ("adl98", "adl98s", "adl21", "nadl")
    label = {"adl98": "ADL98", "adl98u": "ADL98", "adl21": "ADL21", "adl98s": "ADL98S", "adl3a": "ADL3A", "nadl": "NADL",
             "adl3b": "ADL3B"}.get(cfg.get("version"), "ADL5")
    return ["", "## Engine", "",
            "D.O.'s **%s** engine (`%s`): %d scripts with text (%s), the speaker name table%s (%s); "
            "`pc98tl/adl5.py` documents the script format%s and the program patch "
            "(`pc98tl/adl.py` the characters and the tables), `pc98tl/adl_tl.py` the English.  Every "
            "script tokenizes from its statements' start to its end (where a table the walker never steps "
            "onto sits among the statements, the walk is picked up again at the next entry and the table "
            "moves as it is), and each rebuilds byte for byte." % (
                label, prog, len(files), ", ".join("`%s`" % f for f in files),
                " and the menu command table" if any(t.upper().startswith("KOM") for t in tables) else "",
                ", ".join("`%s`" % f for f in tables),
                " (the scripts are coded: after a 4-byte prefix, each byte inverted)" if v98 else ""), "",
            ("The patch works on the game's hard-disk release (the game in `%s/`)%s." % (
                cfg["game_dir"], "; the scripts and the tables are members of %s (a word, the entries' size; "
                "entries of a 12-byte name and a dword offset; the members), which the patch lays out anew" % (
                    "the archive `%s`" % cfg["archive"] if isinstance(cfg["archive"], str) else
                    "the archives " + " and ".join("`%s`" % a for a in cfg["archive"]))
                if cfg.get("archive") else "")
             if cfg["image"].lower().endswith(".hdi") else
             "The patch works on the disk that holds the program and its scripts (`%s`); the other "
             "disks are used as they are." % cfg["image"].replace("\\", "/").split("/")[-1]), "",
            "* A script starts with its entries (the targets of its gotos, calls and menus, as offsets), "
            "so a rebuilt script has them moved with its statements.",
            "* `%s` gets a helper in 512 bytes put in at the end of its code segment (the data and work "
            "segments after it move up, every relocation with them).  In a run of text, 20h (a "
            "character the engine skips) switches to half-width letters: ASCII drawn 8 dots wide from "
            "the BIOS 8x16 font into the graphics planes, in the text's colour (bold where the engine's "
            "text is), with the engine's own character wait and paging (a new line whose row would run past "
            "the window's bottom pages first).  Before each English word the "
            "helper measures it against the window's right edge and starts a new line when it would not "
            "fit (a space at a line's start is not drawn): the windows a script uses change as it calls "
            "and jumps, so the wrap is the program's, not the patcher's." % prog,
            "* The speaker's name indents the text by its name table's slot; the engine's new line (06) "
            "waits for a key itself before it clears a full window.",
            "* Speaker names, menu commands and the program's own strings take ASCII as well.",
            ] + (["* %s (run before the game) draws its lines with the same graphics drawer: it gets "
                  "the same half-width letters (a 256-byte helper, put in the same way), and its lines are "
                  "`e` strings too." % " and ".join("`%s`" % h for h in helpers)] if helpers else [])


def arq_engine(cfg, prog, n_msgs):
    helpers = cfg.get("program_files", [])
    return ["", "## Engine", "",
            "D.O.'s **ARQ98** engine (`%s`): its %d messages are in the program itself, a block in its data "
            "segment (a top table of groups, each group's table of messages, the messages: controls and runs "
            "of text, ADL's characters); `pc98tl/arq.py` documents the block and its patch, `pc98tl/adl5.py` "
            "the program patch (its run is ADL5's, with one window), `pc98tl/adl_tl.py` the English.  The "
            "block rebuilds byte for byte." % (prog, n_msgs), "",
            "The patch works on the game's hard-disk release (the game in `%s/`)." % cfg["game_dir"], "",
            "* The block is rebuilt, with the English, in a segment of its own put in after the program's "
            "image (the work segments after it move up), and the routine that shows the messages is "
            "rewritten in its own bytes to read it there: the messages may take 64 KB together.",
            "* `%s` gets ADL5's helper in 512 bytes put in at the end of its code segment.  In a run of "
            "text, 20h switches to half-width letters: ASCII drawn 8 dots wide from the BIOS 8x16 font into "
            "the graphics planes, with the engine's own character wait and paging (a new line whose row "
            "would run past the window's bottom pages first).  Before each English word the helper "
            "measures it against the window's right edge and starts a new line when it would not fit." % prog,
            "* The program's own strings (the disk prompt, the save and load messages) take ASCII in their "
            "own bytes.",
            ] + (["* %s (run before the game) draws its lines with ADL5's graphics drawer: it gets the same "
                  "half-width letters (a 256-byte helper), and its lines are `e` strings too."
                  % " and ".join("`%s`" % h for h in helpers)] if helpers else [])


def chan_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    prog = cfg["program"]
    names = {"msg": "messages (quiz questions and profiles)", "cmd": "quiz choices", "engine": "program strings"}
    out = ["# %s%s (D.O.)" % ("\u2665 " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "D.O.'s **CHAN** engine (`%s`), a mahjong game with a quiz: the quiz in `QDAT` (a directory of "
            "its members; each a table of 100 questions, then the questions with every byte inverted: four "
            "offsets, the right choice, the question and its three choices), the girls' profiles and the "
            "program's strings in `%s` itself.  `pc98tl/chan.py` documents the formats and the program "
            "patch, `pc98tl/chan_tl.py` the English.  `QDAT` and the profiles rebuild byte for byte."
            % (prog, prog), "",
            "The patch works on the game's hard-disk release (the game in `%s/`)." % cfg["game_dir"], "",
            "* `%s` gets a helper put in at the end of its code segment (the segments after it move up).  "
            "A byte under 80h is a half-width letter: drawn 8 dots wide from the BIOS 8x16 font, bold as the "
            "program's characters, in the caller's colour.  In the text window (the questions, the "
            "profiles) the line's room is taken one for it, a word that would not fit what is left of the "
            "line starts a new line (the window's own, paging at its last row), and a space at a line's "
            "start is not drawn; the string routine (the choices, the menus) draws it the same way." % prog,
            ("* `QDAT` is rebuilt with the English (each member padded to a paragraph, the directory anew); "
             "past the program's five reads (143360 bytes) the last read is made 8000h bytes and the stack "
             "and the memory the program asks for move up with it, 163840 bytes in all."
             if cfg.get("qdat_max", 163840) > cfg.get("qdat_read", 143360) else
             "* `QDAT` is rebuilt with the English (each member padded to a paragraph, the directory anew), "
             "within the program's reads (%d bytes)." % cfg.get("qdat_max")),
            "* The profiles are rebuilt as one block in the room the Japanese took, their table's offsets "
            "anew; the program's other strings are written in their own bytes."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (\u2665) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids): a quiz question in the quiz window (`max_cells` 50 letters a line, 3 "
            "lines, then a key wait and the window scrolled); a profile in its window (38 letters a "
            "line); `\\n` starts a new line.  The program wraps between words.  ASCII is drawn half-width; "
            "another character is drawn full-width when Shift-JIS has it (two cells), else written as `?`.",
            "* Quiz choices (`c` ids): one line each at its place, `max_cells` letters to the screen's edge; "
            "a new line is written as a space.",
            "* `QDAT` with its English may take %s bytes (now %s with the Japanese): each English letter "
            "is one byte, a Japanese character two; a member (its questions) may take 32 KB.  A build "
            "past either is refused." % (cfg.get("qdat_max", 163840), cfg.get("qdat_size", "139760")),
            "* The profiles share the bytes the Japanese took (%s); a build past it is refused and names "
            "them." % cfg.get("profile_room", "their room"),
            "* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); longer ones "
            "are cut and reported.",
            "", "## Not handled", "",
            "* Text drawn into the artwork (the title logo, pictures, the mahjong tiles)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def lmern_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    prog = cfg["program"]
    names = {"msg": "messages (maps, events, the ending)", "name": "speaker names",
             "engine": "program strings", "opening": "opening messages"}
    out = ["# %s%s (Panther Software)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Panther Software's own RPG engine (`%s`): the maps' scripts (`MDTnnn`, their messages inline "
            "in their events, the speaker names in a table), the events' (`%s`) and the ending's (`%s`, run by "
            "`ENDG.EXE`) share one message routine (a copier building the message, then a window drawing it a "
            "character at a time); the program's own text (monsters, items, magic, battle and system messages, "
            "menus) is in its data segment; the opening (`%s`) has a script of its own that puts each "
            "character's glyph into a gaiji.  `pc98tl/lmern.py` documents the formats and the program patches, "
            "`pc98tl/lmern_tl.py` the English.  Unchanged files rebuild byte for byte."
            % (prog, ", ".join(cfg.get("event_files", [])), ", ".join(cfg.get("ending_files", [])),
               cfg["opening"]), "",
            "The patch works on the game's hard-disk release (the game in `%s/`)." % cfg["game_dir"], "",
            "* `%s` and `ENDG.EXE` get a helper put in at the end of their code segment, their data segment "
            "grown to 64 KB (the message buffer moved to its end, 2 KB) and a segment of English put in after "
            "it.  A byte from 20h to 7Fh is a half-width letter, drawn 8 dots wide from the BIOS 8x16 font, "
            "bold, in the caller's colour; the window breaks lines between words.  Every string keeps its "
            "own bytes (lists walked by counting their strings keep their layout): English past them goes on "
            "elsewhere through an escape (7Fh into the map's script, 7Ch into the English segment, back at "
            "7Dh; 7Eh filler is skipped), followed by the copier, the window and the string routine alike." % prog,
            "* A map's script is rebuilt with its English, the speaker names put at its end and their table "
            "pointed at them.",
            "* `%s` gets a helper drawing two letters into each gaiji; each message's text and its pages' "
            "layout (where the gaiji go, line by line) go into room put in after the program, the layout "
            "made anew for the English (wrapped between words to the page's width), the page's timing, "
            "sounds and faces kept in their order." % cfg["opening"],
            "* `LM.COM` and `OP.COM` (the menu run first) get the half-width letters in their string routine."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` 52, the map window's line): any length.  The window wraps "
            "between words and waits for a key when full; `\\n` starts a new line.  ASCII is drawn "
            "half-width; another character is drawn full-width when Shift-JIS has it (two cells), else "
            "written as `?`.  A map's script with its English may take %d bytes; a build past it is refused "
            "and names it." % lmern_max(),
            "* Speaker names (`n` ids): one line, `max_cells` 24.",
            "* Program strings (`e` ids): messages (`max_cells` 52) as the maps' are; names and labels any "
            "length, but `max_cells` is the room of the menu, box or line they sit in (past it they run over "
            "its edge, and what is drawn outside a menu stays on screen after it closes).  Past their own "
            "bytes they are written in ASCII only (`?` for another character).  A program's English segment "
            "may take 65520 bytes; a build past it is refused.  The two lines of the menu run first are cut "
            "to their own bytes (reported).",
            "* Opening messages (`o` ids): wrapped by the patcher to `max_cells` letters a line (the page's "
            "width), ASCII only, at most %d letters a message (two to a gaiji; past it cut and reported); "
            "`\\n` starts a new line." % (2 * 188)]
    out += ["", "## Not handled", "",
            "* Text drawn into the artwork (the title logo, the status window's labels, which are English "
            "already, the pictures)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def zyx_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "message runs", "item": "menu items", "label": "placed labels", "name": "speakers' names",
             "command": "menu commands",
             "engine": "program messages"}
    prog, arc = cfg["program"], cfg["archive"]
    out = ["# %s%s (ZyX)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "ZyX's engine (`%s`): the scripts are the members of the archive `%s` (a directory of names and "
            "offsets); each is run from the code offset at its start, its labels (the words before the code) "
            "the only places a jump or call goes, so a script may grow when its labels move with it.  A "
            "message is a run of commands (colour, a key and a new page, a new line, the speaker, inserted "
            "names and numbers) and text after FFh up to a NUL: bytes below 80h are characters from the "
            "program's table, the rest Shift-JIS.  The speakers' names are a coded member the scripts load "
            "(op 19h).  "
            "`pc98tl/zyx.py` documents the formats and the program patch, `pc98tl/zyx_tl.py` the English.  "
            "Unchanged files rebuild byte for byte." % (prog, arc), "",
            "* The scripts are walked with the program's own op lengths (its table, and its routines for "
            "the ops of variable length, recognised by their code) from their start and every label; the "
            "text runs are rewritten and the labels moved by the bytes before them.",
            "* `%s` gets a helper, put in after its code segment (the segments after it moved up): 80h "
            "turns half-width letters on and off; a letter is drawn 8 dots wide from the ROM's ANK font "
            "through the program's own drawing (colour, outline, the delay between letters); at a space "
            "the line is broken when the next word would pass the window's edge, with the program's own "
            "new line and, past the window's bottom, its key wait and new page.  The speakers' names' "
            "loop gets the same letters." % prog]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Message runs (`m` ids, `max_cells` %d: a line's letters after the speaker's name): any "
            "length; the window breaks lines between words and pages when full.  The line breaks and "
            "pages of the Japanese are the script's own commands around a run, so `\\n` is a space.  A "
            "run its note says is followed by an inserted name or number is drawn on directly before it.  "
            "A script with its English may take 64 KB; a build past it is refused and names the script." %
            cfg.get("window_cells", 0),
            "* Choice menus' items (`i` ids): one line in the menu's box, `max_cells` its widest Japanese "
            "item; past it the line breaks inside the box.",
            "* Labels (`l` ids): text the script places on the screen, one line without breaks: "
            "`max_cells` the Japanese's; past it the letters run on over what is beside them.",
            "* Speakers' names (`n` ids): `max_cells` bytes (the room the program copies each into): a "
            "letter one, two more for the half-width letters' start and end, a full-width character two; "
            "past it cut and reported.",
            "* Commands of the menus (`c` ids): as the speakers' names.",
            "* Program messages (`e` ids): in their own bytes, `max_cells` the room; past it cut and "
            "reported.  The pieces of the two disk prompts that the program writes a drive's letter and a "
            "disk's number into keep their Japanese.",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has "
            "it, else as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures (the title logo, the menus' frames)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def scoop_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "name": "speakers' tags", "item": "menu items", "title": "menu headings",
             "batch": "batch file lines"}
    out = ["# %s%s (Scoop)" % ("\u2665 " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Scoop's Adventure Script Interpreter (`%s`, with SCBIOS.COM and GSHELL.COM resident): each "
            "script (`*.BIN`, \"Adventure v1.00\") is a stack machine's code followed by its strings; the code "
            "pushes a string's offset in the table (op 0Dh) right before the op that shows it (44h a "
            "message or a speaker's tag, 4Ah a menu's item, 4Bh a menu's heading).  The English goes after "
            "the end of the file and only those pushes change, so the code, every jump and every other "
            "string stay where they were.  `pc98tl/scoop.py` documents the format, `pc98tl/scoop_tl.py` "
            "the English.  Unchanged files rebuild byte for byte." % cfg["program"], "",
            "* The program draws ASCII half-width itself (SCBIOS.COM writes the text VRAM, a byte a cell) "
            "and pages the window itself, so the English needs no program patch; the patcher breaks the "
            "lines between words (0Dh) at the window's %d cells, from where the message before left the "
            "line." % cfg["window_cells"],
            "* Bytes A0h-DFh are characters from AI.COM's table (the hiragana the scripts use); `jp` shows "
            "them as they look."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (\u2665) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` %d: the window's width): any length; the patcher breaks the "
            "lines between words, the window waits for a key and starts over when full.  `\\n` in the "
            "English forces a new line.  `[` and `]` around words show them in the highlight colour, as in "
            "the Japanese.  A script with its English may take 64 KB; a longer build is refused and names "
            "the script." % cfg["window_cells"],
            "* Speakers' tags (`n` ids), menu items (`i` ids) and menu headings (`t` ids, shown "
            "highlighted): one line, `max_cells` the Japanese's; past it reported.",
            "* Batch file lines (`b` ids): printed by `%s` when the game cannot start (memory or "
            "interrupts in use); one line." % cfg.get("batch", ""),
            "* `{C1}`-style tokens are the colour commands inside a string and must be kept; `{X86A2}` is "
            "NEC's long line (the scripts draw out a vowel with it).",
            "* English is ASCII (half-width); `<` and `>` (a tag's marks) are written `(` and `)`; another "
            "character is written full-width when Shift-JIS has it, else as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures (the title logo, the window frames)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def sgs_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "name": "speakers' names", "item": "menu items", "system": "system messages",
             "console": "program console lines"}
    out = ["# %s%s (Sogna)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Sogna's SGS (`%s/%s`): each script (`*.SIL`, up to 16 KB) is read into the program's segment "
            "and run op by op.  The ops' lengths are read off the program's own routines (each build has "
            "its own table), so the scripts are walked exactly; the gotos, conditional jumps and calls hold "
            "script offsets and move with the text, so a script may grow.  `pc98tl/sgs.py` documents the "
            "format, `pc98tl/sgs_tl.py` the English.  Unchanged files rebuild byte for byte." % (
                cfg["game_dir"], cfg["program"]), "",
            "* The patch hooks the program's message and menu loops: a 7Fh mark (no JIS pair starts with it) "
            "turns half-width letters on and off, each letter one text-VRAM cell in the message's colour, the "
            "line breaking at the window's edge as for the program's own characters.  The hook's code sits "
            "at the end of the script's 16 KB room, so every script is written with it there.",
            "* The patcher breaks the lines between words at the window's edge (op 03 sets the window, op 4E "
            "the indent after a speaker's name; the program keeps them from script to script), counting the "
            "names a message inserts."]
    if cfg.get("scripts"):
        out.append("* The scripts patched are game.json's `scripts`: %s.  The disk keeps other .SIL files "
                   "that nothing in this edition loads." % ", ".join(cfg["scripts"]))
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` the window's usual width): any length; the patcher breaks the "
            "lines between words and the window scrolls.  `\\n` in the English forces a new line.  A script "
            "with its English may take 16 KB less the hook's bytes; a longer build is refused and names the "
            "script and its strings.  The fullest scripts are close to that already, so their English must "
            "stay about as long in bytes as the Japanese (two bytes a character, one a letter).",
            "* Menu items (`i` ids): one line, `max_cells` the menu's widest Japanese item; past it reported.",
            "* Speakers' names (`n` ids): `max_cells` the Japanese's; the program keeps 48 bytes (a letter "
            "one, a full-width character two, two more for the half-width marks), past them cut and reported.",
            "* System messages (`s` ids, the disk prompts): 79 bytes; past them cut and reported.",
            "* Program console lines (`c` ids): printed before the game starts; in place, `max_cells` the "
            "Japanese's bytes; past them cut and reported.",
            "* `{C1}`-style tokens are the commands inside a string (key waits, colours, inserted names, "
            "pictures) and must be kept; `{X7625}`-style tokens are the game's own characters (JIS row 76h).",
            "* English is ASCII (half-width); another character is written full-width when JIS has it, else "
            "as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures (the titles, the picture menu's captions)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def sys98_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "menu": "menu items and titles", "label": "labels", "name": "speakers' names",
             "console": "program console lines"}
    out = ["# %s%s (four nine System-98)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "four nine's System-98 (`%s`, packed with LZEXE): the scripts (`*.s`, the bytes after 100h XORed "
            "with 1) are members of the `DISK_?.LIB` archives, listed in the `DISK_?.CAT` catalogs, both "
            "LZSS-compressed; a script on its own next to the archives is the one the program reads.  A script is "
            "16-bit ops with their messages and data between them; the patcher walks the code from its start and "
            "every jump (the ops' lengths and pointers read off the program's own routines) and finds every "
            "pointer to a message, a name, a file or data.  The shared routines' script (`%s`, loaded 4000h above "
            "the others, which call it) keeps its layout.  `pc98tl/sys98.py` documents the formats, "
            "`pc98tl/sys98_tl.py` the English.  Unchanged files rebuild byte for byte." % (
                cfg["program"], cfg["sub_script"]), "",
            "* The program is written unpacked and patched: an ASCII byte, which it drew as a blank, is drawn from "
            "the kanji ROM's half-width row, one cell, so English takes a byte a letter.  The hook's code sits "
            "where the program's three exits were; they share one tail now, each still printing its line and "
            "exiting with its code.",
            "* A changed script's old messages are cut out and the English goes at its end, every pointer moved; "
            "the archives with a changed script are written anew, compressed as the originals are.",
            "* Messages (in the wide windows) are broken between words at the window's width and get a key wait "
            "and a cleared window past its lines; menus keep their lines."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` the window's width): any length.  `\\n` in the English forces a new "
            "line.  A script with its English may take 16 KB (the program reads that much); a longer build is "
            "refused and names the script and its strings.  The fullest scripts are close to that already, so "
            "their English must stay about as long in bytes as the Japanese (two bytes a character, one a letter).",
            "* Menus (`i` ids): one item a line, at most `max_cells` (the window's width), no more lines than the "
            "Japanese; past it reported.",
            "* Speakers' names (`n` ids): the program keeps 79 bytes; past them cut and reported.",
            "* Program console lines (`c` ids): in place, `max_cells` the Japanese's bytes; past them cut and "
            "reported.",
            "* `{C1}`-style tokens are the controls inside a text (colours, names and numbers inserted, key waits, "
            "new pages) and must be kept; `{XEBC3}`-style tokens are the game's own characters (the faces and "
            "marks it defines).",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else "
            "as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures (the title, the title menu's items).",
            "* Messages no op points at (left over in the scripts) are not extracted; they stay as they are."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def ail_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "name": "speakers' names", "item": "choice items", "title": "scene titles",
             "prompt": "prompts", "label": "program strings"}
    widths = sorted({e["max_cells"] for e in strings if e["kind"] == "msg"})
    used = sorted({m for e in strings if e["kind"] != "label" for m in re.findall(r"%[A-Za-z]", e["jp"])})
    out = ["# %s%s (Ail ADV.EXE)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Ail's `%s` (packed with EXEPACK): the scenarios are in `%s`, each LZSS-compressed; a scenario is "
            "its tables, labels, code and text, the code reading each text by its offset.  The patcher walks the "
            "code op by op (the sub-ops' arguments counted off the program's own routines) and lays the text "
            "section out anew with the English, every offset moved; the code stays as it is.  `pc98tl/ail.py` "
            "documents the formats, `pc98tl/ail_tl.py` the English.  Unchanged files rebuild byte for byte." % (
                cfg["program"], cfg["scenarios"]), "",
            "* The program draws a single byte half-width from the kanji ROM by itself, so English takes a byte a "
            "letter; it lays a text out two bytes at a time, so each text is padded to an even length.",
            "* The program breaks a message's lines by itself (%d cells in a slot indented under the name, %d in "
            "one from the window's edge, read off the program) and pages the window; the patcher fills each line "
            "with spaces to that width so the breaks fall between words." % (widths[0], widths[-1]),
            "* The program's own strings (menus, prompts, messages) are replaced in place in the program."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` the line's width, %s cells): any length; the patcher breaks "
            % " or ".join(str(w) for w in widths) +
            "the lines between words and the program pages.  `\\n` in the English forces a new line.  A scenario "
            "with its English may take %d bytes unpacked (the program's buffer); a longer build is refused and "
            "names the scenario's strings.  The fullest scenarios are within a few hundred bytes of that already, "
            "so their English must take no more bytes than the Japanese (two bytes a character, one a letter)." %
            cfg["scenario_room"],
            "* Speakers' names (`n` ids): `max_cells` the Japanese's.",
            "* Choice items (`i` ids): one line in the choice's box, `max_cells` the choice's widest Japanese "
            "item; past it reported.",
            "* Scene titles (`t` ids): shown with a choice and kept with a save, `max_cells` the Japanese's; "
            "past it reported."]
    if kinds.get("prompt"):
        out.append("* Prompts (`p` ids): a line shown on its own, `max_cells` the Japanese's; past it reported.")
    out += ["* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width "
            "character two); past it cut and reported.  `%s`-style marks are kept."]
    if used:
        out.append("* Inserts (%s) must be kept: `%%m` the hero's name (the program string the name entry "
                   "starts with, as the player types it), `%%s` the pronoun the player picks (the program strings "
                   "listing them), `%%A` to `%%Z` a number.  The patcher breaks lines with an insert at its widest "
                   "and fills them at its narrowest, so a longer one only moves a few spaces to the next line.  An "
                   "insert the program has no string for is refused." % ", ".join("`%s`" % m for m in used))
    out += ["* `>` is the program's colour mark: in the English it is written `)`; a `%` that is no insert is "
            "written `pct`.",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else "
            "as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def active_if_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "name": "speakers' names", "item": "choice items", "title": "scenario titles",
             "label": "program strings"}
    widths = sorted({e["max_cells"] for e in strings if e["kind"] == "msg"})
    out = ["# %s%s (Active MAIN.EXE)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Active's `%s` (Borland C): each scenario's scripts are `*.ADV` files in its folder under `%s`, blocks "
            "of ops and texts; the patcher walks every op (their operands read off the program's own routines) "
            "and lays a changed script out anew, every pointer (the blocks' chain, the jumps, the choices' "
            "targets) moved.  `pc98tl/active_if.py` documents the format, `pc98tl/active_if_tl.py` the English.  "
            "Unchanged files rebuild byte for byte." % (cfg["program"], cfg["game_dir"]), "",
            "* The program draws a text two bytes at a time and counts its window's columns in cells; it is "
            "patched to draw a pair of ASCII letters as two half-width letters from the kanji ROM's half-width row, "
            "so English takes a byte a letter, two a cell.",
            "* The program breaks a line at its window's edge and waits for a key and clears the window past its "
            "lines; the patcher fills each line with spaces to the window's width so the breaks fall between "
            "words, following the window the scripts set (op 6Fh) from script to script.",
            "* The program's own strings (menus, prompts) are replaced in place, the scenarios' titles in their "
            "`TITLE.DAT`.",
            "* When the English does not fit on the disk, the patcher grows the volume by whole cylinders, up to "
            "the clusters its FAT has room for, without moving anything (`DiskImage.grow_volume`); past that "
            "the build is refused."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` the line's width in letters, %s): any length; the patcher breaks "
            % " or ".join(str(w) for w in widths) +
            "the lines between words and the program pages.  `\\n` in the English forces a new line.  A message "
            "is the texts up to a key wait; the key wait it ends with is the patcher's.  The program reads at most "
            "32768 bytes of a script: a longer build is refused and names the script's strings."]
    if kinds.get("name"):
        out.append("* Speakers' names (`n` ids, with their `「`): `max_cells` the Japanese's; the message goes on "
                   "after the name on its line and the program starts the message's other lines under the "
                   "name's end, so a longer name makes the message's lines shorter.")
    out += ["* Choice items (`i` ids): one line in the choice's box, `max_cells` the choice's widest Japanese "
            "item; past it reported.",
            "* Scenario titles (`t` ids): `max_cells` the Japanese's; past it reported.",
            "* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width "
            "character two); past it cut and reported.  `%s`-style marks and a menu item's leading `*0` are kept.",
            "* `{p}`-style tokens are the controls inside a message (`{v0A}` a pause and its length, `{w}` a new "
            "window, `{e01}`, `{f}` and the others); keep the ones that matter.  `\\`, `{` and `}` are written `/`, "
            "`(` and `)`.",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else "
            "as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures.",
            "* The install batch files' lines (run from the floppies only)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def active_halo_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "item": "choice items", "prompt": "prompts", "opening": "opening blocks",
             "menu": "main menu descriptions", "label": "program strings"}
    out = ["# %s%s (Active MAIN98.EXE)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Active's `%s` (Borland C): the game's files are in the archive `%s` (its files found by a hash of "
            "their names); the scripts (`*.HGO`) are a table of entries (labels, menus' items, switches' cases, "
            "each with its places in the code) and the code, ops and texts.  The patcher walks every op (their "
            "operands read off the program's own routines) and lays a changed script out anew, every place (the "
            "entries', the switches' and the conditions') moved; the archive is written anew.  `pc98tl/active_halo.py` "
            "documents the formats, `pc98tl/active_halo_tl.py` the English.  Unchanged files rebuild byte for byte."
            % (cfg["program"], cfg["archive"]), "",
            "* The program draws ASCII half-width by itself, so English takes a byte a letter.",
            "* A message's lines are each a text of their own (a text starts a new line); the patcher breaks the "
            "English between words into lines of the narrower window's width (56 cells) and the program pages "
            "the window past its lines.",
            "* The opening (`OPENING.DAT`, lines of text) is broken between words at its widest Japanese line and "
            "its blocks' line counts set; the main menu's descriptions (`*.GMO`) are written anew with their places."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` the line's width, 56): any length; the patcher breaks the lines "
            "between words and the program pages.  `\\n` in the English forces a new line.  A message is the "
            "texts up to another op; a key wait it ends with (`{P}`, `{W}`) is put back when the English leaves it "
            "out.  The program holds a script of at most 49152 bytes: a longer build is refused and names the "
            "script's strings.",
            "* Choice items (`i` ids): `max_cells` the script's widest Japanese item; past it reported.",
            "* The opening (`o` ids): any number of lines, each at most `max_cells`, centred by the program.",
            "* Main menu descriptions (`d` ids): one line, `max_cells` the menu's widest Japanese one; past it "
            "reported.",
            "* Prompts (`p` ids): `max_cells` the Japanese's; past it reported.",
            "* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width "
            "character two); past it cut and reported.  `%s`-style marks are kept.",
            "* `{W}`-style tokens are the controls inside a message (`{P}` a key wait, `{W}` a key wait and a "
            "cleared window, `{V0102}` a control and its two bytes); keep the ones that matter.  `\\`, `{` and `}` "
            "are written `/`, `(` and `)`.",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else "
            "as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures (the main menu's items, the opening's titles)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def sgs21_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "name": "speaker names", "item": "menu items", "label": "program strings",
             "console": "program console lines"}
    out = ["# %s%s (Sogna, SGS21)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Sogna's `%s` (protected mode): the scripts (`*.WIN`) are files in `SGS.DAT` (a directory of "
            "32-byte entries, most files LZ-compressed); a script is ops, each a byte and its operands (the "
            "formats read off the program's own routines), and the ops that go somewhere hold a place in the "
            "script.  The patcher lays a changed script out anew with those places moved, compresses it again "
            "and puts it at `SGS.DAT`'s end (the archive is mostly pictures and sounds).  `pc98tl/sgs21.py` "
            "documents the formats, `pc98tl/sgs21_tl.py` the English.  Unchanged files rebuild byte for byte."
            % cfg["program"], "",
            "* The program draws ASCII half-width by itself (messages, menus, its dialogs).",
            "* A message's window breaks its line at the right edge and does not scroll; the patcher breaks the "
            "English between words (following the column from one message to the next, as the program does) "
            "and, when the window's rows are full, ends the message there and goes on after a key wait and a "
            "clear.",
            "* The game is started from its hard-disk boot floppy's menu, with the CD in the drive "
            "(`game.json` `boot_fd`, `cd`); the program refuses to start from the hard disk's prompt."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids): any length.  `max_cells` is a line's room in half-width cells (the window's "
            "width less the indent where a line after the first starts).  `{N03}`-style tokens are a speaker's "
            "name (an `n` string) drawn at that place: keep them.  `{CLR}` clears the window, `{W}` is a "
            "mark the program skips; `\\n` forces a new line.  A script may take 65535 bytes; a longer build "
            "is refused and names its strings.",
            "* Speaker names (`n` ids): at most 63 bytes (cut past it and reported); `max_cells` the Japanese's "
            "width, past it reported (a message's text goes on right after the name).",
            "* Menu items (`i` ids): at most 81 bytes (cut and reported); `max_cells` the menu's widest Japanese "
            "item, past it reported (the box grows with its longest item).",
            "* Program strings (`l` ids, its dialogs) and console lines (`c` ids, printed before the game): in "
            "place, `max_cells` the room in bytes (a letter one, a full-width character two); past it cut and "
            "reported.  The dialogs' YES / NO line keeps its two words where the Japanese has them (the "
            "mouse's places are fixed).",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else "
            "as `?`.  `\\` and `~` are written `/` and `-`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures (the title menu).",
            "* The boot floppy's install menu (`INSMENU`), which is not part of the game's disk."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def yjwar_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "scene messages", "scene": "animated scenes' messages", "profile": "profile lines",
             "battle": "battle lines", "doc": "data pages' paragraphs", "name": "unit names",
             "label": "program strings"}
    out = ["# %s%s (D.O.)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "D.O.'s `%s`: the scenes' messages are `*.TXB` files and the animated scenes `*.SC` files in "
            "NCA archives (`SYSDATA.NCA`, `ANMSC.NCA`), their Shift-JIS with every bit inverted; the battle "
            "lines (`*.MSG`), the data pages (`DATA_*.TXT`) and the unit table (`UNIT.DAT`) are plain files.  "
            "`pc98tl/yjwar.py` documents the formats, `pc98tl/yjwar_tl.py` the English.  Unchanged files "
            "rebuild byte for byte." % cfg["program"], "",
            "* The program draws ASCII half-width by itself and breaks a line at its window's edge (mid-word); "
            "the patcher breaks the English between words, filling each line's end with spaces.",
            "* A message window holds four lines (a fifth is drawn over the screen); the patcher makes a longer "
            "text several messages, a click each.",
            "* The program's strings and its unit table are replaced in place in the program.",
            "* The game asks for DIP switch SW2-8 off (`game.json` `dipsw`)."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Scene messages (`m` ids) and animated scenes' messages (`s` ids): any length, `max_cells` the "
            "window's width (70 half-width cells).  `\\n` forces a new line.  The opening's pages are centred "
            "line by line.",
            "* Profile lines (`p` ids): one line each at a fixed place, `max_cells` 36; past it reported.",
            "* Battle lines (`b` ids): broken at the battle window's 28 cells; at most 78 bytes (the longest "
            "Japanese line), past it cut and reported.",
            "* Data pages (`d` ids): a paragraph each, any length, broken at the page's 62 cells with the "
            "Japanese's indents.",
            "* Unit names (`n` ids): at most 19 bytes (cut past it); `max_cells` 16, the panels' room, past it "
            "reported.",
            "* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width "
            "character two); past it cut and reported.  Keep `%s`/`%d` marks.",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, "
            "else as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def flz_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "label": "program strings"}
    out = ["# %s%s (U-Me Soft)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "`%s`: the messages are in the `*.TXB` files, blocks of strings packed with LZSS (\"FLZ0\"); the "
            "scripts name a message by its block and number.  The patcher packs a changed block again and "
            "writes the program's own strings in place.  `pc98tl/flz.py` documents the format, "
            "`pc98tl/flz_tl.py` the English.  Unchanged files rebuild byte for byte." % cfg["program"], "",
            "* The program draws ASCII half-width by itself and breaks a line at 58 half-width cells "
            "(mid-word); the patcher breaks the English between words with the program's new line."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` 58, the window's width in half-width cells): five lines at most "
            "(the window's); the patcher breaks the English between words and cuts a message past five lines "
            "(reported).  `\\n` forces a new line.  A block (a scene's messages) may take 65535 bytes; a "
            "longer build is refused and names its strings.",
            "* Program strings (`l` ids, its menus and notices; `\\n` a new line): in place, `max_cells` the "
            "room in bytes (a letter one, a full-width character two); past it cut and reported.",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, "
            "else as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures, and the prologue that scrolls before the title (it is in none of "
            "the game's text files)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def choreo_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "message texts", "date": "pieces of the date line", "choice": "choices and buttons",
             "menu": "menu titles"}
    out = ["# %s%s (Space Project)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "`%s`, Arigata-ya's \"Choreographer Inter-Book View Finder\": the `*.SCE` scenarios are bytecode for "
            "a stack machine, the text in them (Shift-JIS, a string with its length).  The patcher writes the "
            "scenarios again with the English, the jumps and the calls between scenarios moved to where their "
            "operations now are.  `pc98tl/choreo.py` documents the format, `pc98tl/choreo_tl.py` the English.  "
            "Unchanged files rebuild byte for byte." % cfg["program"], "",
            "* The game is played with the mouse.",
            "* The program draws ASCII half-width by itself.  The message box is 36 half-width cells wide; the "
            "program breaks a line at its edge (mid-word) and pages a full box (▼).  A message is built from "
            "pieces (a speaker's name, a paragraph), each going on where the last ended; the patcher breaks the "
            "English between words, following the column across a box's pieces."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Message texts (`m` ids, `max_cells` %d): any length; the patcher breaks the English between "
            "words at %d half-width cells (a full line's new line would leave an empty one) and the program "
            "pages the box.  `\\n` forces a new line; keep a piece's leading `\\n` (its paragraph break), as a "
            "piece without one goes on from where the last ended." % (cfg["line_cells"], cfg["line_cells"]),
            "* The date line (`d` ids: month, day, weekday): its box first shows the line's last 12 half-width "
            "cells, the numbers taking 4; `max_cells` is each piece's share (month 2, day 2, weekday 4); past "
            "it reported.",
            "* Choices (`c` ids: the choice box, 24 cells; the title menu's buttons, 15; the システム button, "
            "4) and menu titles (`u` ids): one line, `max_cells` the room; past it reported.",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, "
            "else as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def aaru_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "item": "choice items", "label": "program strings"}
    maker = cfg["key"].split(".zip")[0]
    width = cfg.get("window_cells", 60)
    loose = maker != "Aaru"
    out = ["# %s%s (%s)" % ("♥ " if heart else "", cfg["title"], maker), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "%s's `%s`%s: the scripts (`*.AB`) are %s, compressed with LZSS in some games; "
            "a script is ops, each a word and its operands (the formats read off the program's own handlers).  "
            "The patcher lays a changed script out anew, its jumps moved, compresses it again when it was and "
            "writes it back.  `pc98tl/aaru.py` documents the formats, `pc98tl/aaru_tl.py` the English.  "
            "Unchanged files rebuild byte for byte." % (
                maker, cfg["program"], " (Aaru's engine)" if loose else "", "files of their own" if loose else
                "files in the FL1 archives (`*.FL1`, a directory of names and sizes at the end)"), "",
            "* The program draws ASCII half-width by itself, but from 60h one letter low (its half-width codes "
            "step over Shift-JIS's missing 857Fh); the patcher writes those bytes one higher, so lowercase "
            "letters show as they should.",
            "* The program breaks a message's line at its window's edge; the patcher breaks the English between "
            "words with the program's new line (`\\N`) between the lines.",
            "* The program's own strings (its menus) are replaced in place in the program (packed, but with its "
            "code and data as they are), their room filled with spaces."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` the window's width, %d half-width cells): any length; the patcher "
            "breaks the lines between words; the program waits for a key when its window is full.  `\\n` in "
            "the English forces a new line (the Japanese's speaker names stand on a line of their own).  A "
            "script may take 65535 bytes unpacked; a longer build is refused and names its strings." % width,
            "* Choice items (`i` ids): one line, `max_cells` the script's widest Japanese item; past it reported.",
            "* Program strings (`l` ids): in place, `max_cells` the room in bytes (a letter one, a full-width "
            "character two); past it cut and reported.",
            "* The program's controls are tokens: keep them in the English.  `{C7}` a colour, `{S}` a key wait, "
            "`{G08-z}` a face picture shown beside the window and `{G}` the picture taken away.",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, else "
            "as `?`.  `\\`, `%`, `|`, `` ` ``, `{`, `}` and `~` are written `/`, `pct`, `!`, `'`, `(`, `)` and `-`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures (the titles)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def cinema_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "name": "speakers' names", "item": "menu items", "engine": "program messages"}
    cols, rows = cfg["window"]
    out = ["# %s%s (Foster)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Foster's CINEMA engine (`%s` loads the archive's driver, FAD.BIN, which serves the members of "
            "`%s` and B.FA1; CINEMA.BIN runs the scripts, MB3N.BIN draws the text).  The archive is a "
            "directory of names and sizes at its end; most members are compressed (an LZ of 16-bit flag "
            "words), a member written back is stored unpacked, which the driver reads as it is.  A script "
            "is run op by op from its start in a 32 KB buffer whose last 2 KB hold ESC.BIN (the escape "
            "menu); the ops' lengths are CINEMA.BIN's, and the ones that hold an address in the script "
            "(gotos, calls, switches, the ifs, a message's or a menu's end, the menus' items) are rewritten "
            "when the text before them grows.  `pc98tl/cinema.py` documents the formats, "
            "`pc98tl/cinema_tl.py` the English.  Unchanged files rebuild byte for byte." % (cfg["program"], cfg["archive"]),
            "",
            "* The program draws bytes below 80h itself as half-width letters (the ROM's ANK font), so the "
            "English needs no program patch.  The patcher breaks the lines between words and pages the "
            "window: it follows the cursor from message to message (a message after a speaker's name goes "
            "on along the name's row), puts the program's new line (\\n) at the window's edge, and when "
            "the window's %d rows are full ends the page (\\f) and waits for a key (op 3Fh) before the rest." % rows,
            "* AUTOEXEC.BIN (the title and its menus) runs machine code from its own bytes, so it keeps its "
            "layout: a text that fits is written in its place, a longer one after the script's end (a "
            "message reached by a goto put in its place, an item by its address)."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` %d: the window's width): any length; the patcher breaks the "
            "lines between words and pages the window (%d rows).  A message after a speaker's name goes on "
            "along the name's row (its note says so); one whose Japanese starts with a full-width space "
            "gets a space before the English when it has none.  `\\n` in the English forces a new line.  "
            "A script with its English must end before ESC.BIN's place (7800h, 30 KB); a build past it is "
            "refused and names the script." % (cols, rows),
            "* Speakers' names (`n` ids): one line, `max_cells` the Japanese's; a longer name leaves less "
            "of its row to the message after it.",
            "* Menu items (`i` ids): one line in the menu's box, `max_cells` the menu's widest Japanese "
            "item; past it reported.",
            "* Program messages (`e` ids): TSM.COM's, printed by DOS when memory or a file is missing, in "
            "their own bytes, `max_cells` the room; past it cut and reported.",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has "
            "it, else as `?`; a backslash (the commands' mark) as `/`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures (the title menu's items, the logo)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def elfai_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"msg": "messages", "item": "menu items", "tag": "speaker tags", "name": "names and prompts"}
    out = ["# %s%s (Elf)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Elf's early AI engine (`%s`, EXEPACK'd), before AI5: the scripts (`*.MES` in `%s/`) are run "
            "a byte at a time, statements 99h-BFh with numbers, variables and blocks in braces, Shift-JIS "
            "text drawn where it stands, each script's own dictionary (codes C0h-EFh, defined by statement "
            "A4h, run in place).  Nothing in a script is an address.  `pc98tl/elfai.py` documents the format "
            "and the program patch, `pc98tl/elfai_tl.py` the English.  Unchanged scripts stay byte for byte "
            "as they are." % (cfg["program"], cfg["game_dir"]), "",
            "The patch works on the game's hard-disk release.", "",
            "* A script may not grow much: it is loaded at DS:2000h under the animations' buffers "
            "(DS:8000h and up).  So the messages' English is kept in `NAME.ENG` next to each script, and the "
            "script draws it line by line through a statement the program did not use (BBh and the line's "
            "offset).  `%s` is unpacked and given a helper at the end of its code: the statement draws the "
            "line a byte to a half-width letter, as the program draws a string; loading a script loads its "
            "`.ENG` into a 64 KB segment past the program's memory, which it grows by as much." % cfg["program"],
            "* Lines are wrapped between words to the text window (followed through the script: `A7` sets "
            "it, 3 lines of 80 letters for the messages), starting where the text before leaves the cursor "
            "(after a speaker's tag), and a new page (a key, then the window cleared) begun when it is full.",
            "* Menu items and speakers' tags are written as strings in the script; names (the defaults "
            "KPUT.COM, the name entry, starts from, and its prompts) full-width."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Messages (`m` ids, `max_cells` 79): any length; wrapped and paged by the patcher.  `\\n` "
            "starts a new line.  `{N24}`/`{N25}` stand for the hero's family/given name (keep them; each "
            "is counted as 12 letters).",
            "* Menu items (`i` ids, `max_cells` 14): one line, past the box's edge beyond it (reported).",
            "* Speakers' tags (`t` ids): one line; the message goes on after it on the same line.",
            "* Names (`n` ids): written full-width; a name 6 letters at most (KPUT.COM's), a prompt its "
            "`max_cells`; past it cut and reported.",
            "* English is ASCII (half-width); another character is written as `?` (`\"` in a menu item or "
            "tag as `'`).  A script with its English may take 24 KB (less where it names a lower buffer), its "
            "`.ENG` 64 KB; a build past either is refused and names the script."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures and the name entry's character grid (KPUT.COM's own)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def ppdisk_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    names = {"article": "articles", "page": "full-screen pages", "title": "menu titles", "menu": "menu items",
             "balloon": "Pia's balloons", "engine": "program messages", "install": "installer text",
             "demo": "REIRA demo messages", "demo_item": "REIRA demo menu items", "demo_label": "REIRA demo labels"}
    h = cfg["hdd"]
    out = ["# %s%s (Mediax / P's PSYTEC)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`), with `%s` next to it." % (
               cfg["image"].replace("\\", "/"), h["disks"][0])]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "A disk magazine: on each floppy the viewer `PPDISK.EXE` (the same program on both), its menus "
            "(`PPDISK.SCR`: the menus, Pia's speech balloons and a pool of strings the program relocates when "
            "it loads it) and its text (`PPDISK.TXT`: records of lines, shown in the menus' box or on the whole "
            "screen).  Disk B also carries Silky's *REIRA* demo (`SIL.EXE`, `SILK0.DAT`: the AI5 engine, patched "
            "by `pc98tl/ai5.py`) and its installer (`PPCOPY.EXE` with `PPCOPY.CMD`).  `pc98tl/ppdisk.py` "
            "documents the formats and the program patch, `pc98tl/ppdisk_tl.py` the English.  Unchanged files "
            "rebuild byte for byte.", "",
            "The floppies have no room for the English (5 KB and 3 KB free), so the patch lays them out on a DOS "
            "hard disk, as the other floppy games here are: Disk A in `\\%s`, Disk B in `\\%s\\%s`.  "
            "AUTOEXEC.BAT starts Disk A's viewer and then Disk B's, each with `-d` (the program's own switch: ESC "
            "on the main menu quits, which on the floppies it never does).  The demo runs with `GAME` in "
            "`\\%s\\%s`." % (h["dir"], h["dir"], list(h["disk_dirs"].values())[0], h["dir"],
                                 list(h["disk_dirs"].values())[0]), "",
            "* `PPDISK.TXT` is rebuilt with the English, wrapped between words, and the menus' offsets of its "
            "records rewritten.",
            "* The menus' strings are written in their own bytes, or at the end of the pool (its size in the "
            "header grows).",
            "* `PPDISK.EXE`: the viewers' tables of page starts (32 on the stack) are moved to the last 512 bytes "
            "of the 32 KB text buffer (256 pages), every read into the buffer stopping short of them.  ASCII is "
            "drawn half-width by the program's own text routine.  Its messages are written in their own bytes."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Articles (`a` ids, `max_cells` 46): lines wrapped between words to 46 letters, 8 lines to a "
            "page; full-screen pages (`p` ids, `max_cells` 80): 80 letters, 24 lines to a page.  `\\n` "
            "between lines (a line's leading spaces are kept).  A record may take 32255 bytes (a byte a letter "
            "and one for each line's end) and 256 pages; a build past either is refused and names it.",
            "* Menu titles (`t` ids, `max_cells` 36) and items (`m` ids, `max_cells` 46): one line; past it "
            "they run over the box (reported).",
            "* Pia's balloons (`b` ids): wrapped to 16 letters, 6 lines at most; past them the build is refused.",
            "* Program messages (`e` ids): in their own bytes, `max_cells` the room; past it cut and reported.  "
            "`{S1}`/`{N1}` stand for the name/number the program puts in.",
            "* Installer text (`i` ids): lines wrapped to 78 letters; the screen shows 23, past them the first "
            "scroll off (reported).",
            "* REIRA demo (`dm`, `di`, `dl` ids): as the AI5 games' messages, menu items and labels "
            "(`games/reira/notes.md`).",
            "* English is ASCII (half-width); another character is written full-width when Shift-JIS has it, "
            "else as `?`."]
    out += ["", "## Not handled", "",
            "* Text drawn into the pictures (the title screen, the map, the icons)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def lmern_max():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from pc98tl import lmern
    return lmern.MDT_MAX


def panther_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    prog, op = cfg["program"], cfg.get("opening")
    names = {"msg": "scene strings", "engine": "program strings", "opening": "opening strings"}
    kept = sum(1 for e in strings if e["kind"] == "msg" and "note" in e)
    out = ["# %s%s (Panther Software)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    out += ["", "## Engine", "",
            "Panther Software's own engine (`%s`): the scenes (`*.P`, `*.CMN`, `START*.BIN`) are code overlays "
            "the engine reads into its overlay segment, their strings among their code, a message named by "
            "the `mov si` before the engine's message call; the program's own strings are in its data "
            "segment%s.  `pc98tl/panther.py` documents the formats and the program patches, "
            "`pc98tl/panther_tl.py` the English.  Unchanged files rebuild byte for byte."
            % (prog, "; the opening (`%s`) has its text in its own data segment" % op if op else ""), "",
            "The patch works on the game's hard-disk release (the game in `%s/`)." % cfg["game_dir"], "",
            "* `%s` gets a helper put in at the end of its code segment (the segments after it move up).  "
            "A byte from 20h to 7Fh is a half-width letter: drawn 8 dots wide from the BIOS 8x16 font, bold "
            "as the program's characters, two to a character's place; in the message window and the string "
            "routine (menus) alike." % prog,
            "* A scene's message longer than its own bytes is put at the scene's end and its `mov si` pointed "
            "at it; the overlay segment grows to the largest scene (up to 65535 bytes), the segments after "
            "it moving up.",
            "* The program's messages and menu labels longer than their own bytes go in room put in after "
            "its data segment, their `mov si` / `mov bx` pointed at them."]
    if op:
        out.append("* `%s` gets the same half-width drawing in its character loops, its reveal and its string "
                   "routine; its text is rebuilt in room put in after its data segment (story lines centred "
                   "anew, the characters' names centred in their card)." % op)
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            "* Scene messages (`m` ids, `max_cells` 45): any length.  The patcher wraps between words at 45 "
            "letters a line; the engine pages every 5 lines with a key wait.  `\\n` starts a new line.  ASCII "
            "is drawn half-width; another character is drawn full-width when Shift-JIS has it (two cells), "
            "else written as `?`.",
            "* Scene strings no `mov si` names (%d, their `note` says so: the ending's credits and a few "
            "lines): each within its own bytes (`max_cells`); longer ones are cut and reported." % kept,
            "* A scene may take 65535 bytes with its English (the engine's read); a build past it is refused "
            "and names the scene.",
            "* Program strings (`e` ids): messages (`max_cells` 45) as the scenes' are; menu labels one line "
            "each, `max_cells` the Japanese's room (past it reported, the box does not grow); the weapons' "
            "names and the disk prompts within their own bytes (longer ones are cut and reported).  The "
            "data segment has 39152 bytes of room for the moved ones; a build past it is "
            "refused."]
    if op:
        out.append("* Opening strings (`o` ids): one line each, `max_cells` letters (80 for the story and "
                   "glossary lines, the card's columns for the characters' names, the Japanese's room for "
                   "the mode labels, past which is reported); longer lines are cut and reported.")
    out += ["", "## Not handled", "",
            "* Text drawn into the artwork (the title logo, the pictures; the opening's map and mecha "
            "screens are English already)."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def adl_notes(name, cfg, doc, adult, clear, tests, extra):
    a = adult.get(cfg["key"], {})
    heart = bool(a.get("adult"))
    strings = doc["strings"]
    done = sum(1 for e in strings if e["en"])
    kinds = {}
    for e in strings:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    v5 = cfg.get("version") in ("adl5", "adl5a", "adl98", "adl98s", "adl98u", "adl21", "adl3a", "adl3b", "nadl")
    prog = cfg.get("program", "ADL.EXE")
    names = {"msg": "messages", "name": "speaker names", "cmd": "menu commands",
             "engine": "program strings" if v5 or cfg.get("version") == "arq98" else "save slot names"}
    files = sorted({r.split(":")[0] for e in strings for r in e["refs"] if e["kind"] == "msg"})
    name_cells = min([e["max_cells"] for e in strings if e["kind"] == "name"] or [8])
    tables = sorted({r.split(":")[0] for e in strings for r in e["refs"] if e["kind"] in ("name", "cmd")})
    cmd_cells = min([e["max_cells"] for e in strings if e["kind"] == "cmd"] or [16])
    out = ["# %s%s (D.O.)" % ("♥ " if heart else "", cfg["title"]), "",
           "> This patch's script is a **machine translation (AI/MTL)**, not a human "
           "translation. It will be retired if a human translation is released.", "",
           "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
    c = clear.get(cfg["key"])
    if c:
        res = c.get("result", "")
        out.append("Clearance: %s on %s (`research/clearance.json`)." % (
            "no PC-98 English release or announcement found" if res == "clear" else res, c.get("checked", "")))
    arq = cfg.get("version") == "arq98"
    if arq:
        out += arq_engine(cfg, prog, kinds.get("msg", 0))
    elif v5:
        out += adl5_engine(cfg, files, tables, prog)
    else:
        out += ["", "## Engine", "",
            "D.O.'s **%s** engine (`%s`): %d scripts with text (%s), the speaker name tables and "
            "the menu command tables (%s); `pc98tl/adl.py` documents the formats and the program patch, "
            "and `pc98tl/adl_tl.py` the English.  Every script tokenizes from its statements' start (1000h) "
            "to its end (where bytes the walker never steps onto sit among the statements, the walk is "
            "picked up again at the next entry and the bytes move as they are), and each rebuilds byte "
            "for byte." % (
                "ADL2" if cfg.get("version") == "adl2" else "ADL", prog, len(files),
                ", ".join("`%s`" % f for f in files), ", ".join("`%s`" % f for f in tables)), "",
            ("The patch works on the game's hard-disk release (the game in `%s/`)." % cfg["game_dir"]
             if cfg["image"].lower().endswith(".hdi") else
             "The patch works on the floppy (`%s`)." % cfg["image"].replace("\\", "/").split("/")[-1]), "",
            "* A script starts with its entries (the targets of its gotos and menus, as offsets), so a "
            "rebuilt script has them moved with its statements.",
            "* `%s` gets a helper in 768 bytes put in at the end of its code segment (the data and "
            "work segments after it move up, every relocation with them).  In a run of text, 20h (a "
            "character the engine skips) switches to half-width letters: ASCII drawn one text cell each, "
            "with the engine's own character wait, wrapped at the window's right edge and paged (the "
            "blinking key-wait mark, then the window cleared) at its bottom." % prog,
            "* Lines are wrapped between words by the patcher to the text window the script set (71h), "
            "the speaker's name indenting the text 10 cells; %s" % (
                "the engine's new line (06) waits for a key itself before it clears a full window."
                if cfg.get("version") == "adl2" else
                "a full window that the script's new line (06) would clear waits for a key first when "
                "text was drawn since the last wait."),
            "* Speaker names, menu commands and the save slots' names take ASCII as well (one cell or "
            "one 8-dot column each, the menus' from the BIOS 8x16 font).",
            "* A menu's text window (sized by the script to the longest Japanese choice) is widened, "
            "with its frame, to the longest English choice, so that each choice stays one line."]
    out += ["", "## Script", "",
            "%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, names.get(k, k))
                                                       for k, n in sorted(kinds.items()))), ""]
    out.append("Translation and the content classification (♥) are done by the translation model; "
               "%d of %d strings have English so far." % (done, len(strings)))
    out += ["", "## Limits", "",
            ("* Messages (`m` ids): any length within the block's room (below); `\\n` starts a new line.  "
             "`max_cells` is a line's width in the window (letters); longer text wraps between words and "
             "pages.  ASCII is drawn half-width; another character is drawn full-width when Shift-JIS has "
             "it (two cells), else written as `?`." if arq else
             "* Messages (`m` ids): any length within the script's room (below); `\\n` starts a new line. "
             "`max_cells` is a line's width in its window (letters); longer text wraps between words and "
             "pages.  A menu's choices (the messages right after a menu) should stay within one line: "
             "their `max_cells` is the widest the screen allows the menu's window.  ASCII is drawn "
             "half-width; another character is drawn full-width when Shift-JIS has it (two cells), else "
             "written as `?`."),
            ("* `{X1}`, `{X2}`...: the message's controls between its runs (a key wait, a new line, the "
             "window cleared, the portrait); the note says what each does.  Keep each once, in any order; "
             "a message without them all is refused." if arq else
             "* `{X1}`, `{X2}`...: the script's controls between the runs of a message (a key wait, a "
             "colour change, a new line, the next statement going on along the same line); the note says "
             "what each does.  Keep each once, in any order; a message without them all is refused."),
            ("* The messages are rebuilt into one 64 KB segment: with their English they may take 65536 "
             "bytes together.  Each English letter is one byte; a Japanese kana one, a kanji two.  A build "
             "that outgrows it is refused." if arq else
             "* A script is read whole into a 64 KB segment: with its English it may take 65536 bytes.  "
             "Each English letter is one byte; a Japanese kana one, a kanji two.  A build whose script "
             "outgrows its segment is refused and names the script and its strings."),
            ("* Speaker names (`n` ids): `max_cells` letters (%s, the slot the script gives the name's "
             "table, 19h); the text after a name starts as many cells in as its table's slot.  Longer ones "
             "are cut and reported." % _cells_range(strings, "name")
             if v5 else
             "* Speaker names (`n` ids): %d letters (the table's 9-byte slot), drawn before the colon; the "
             "text after them starts 10 cells in.  Longer ones are cut and reported." % 8),
            ("* Menu commands (`c` ids): `max_cells` letters (%s: the slot the script gives the command's "
             "table, 18h, within the menu boxes drawn while it is loaded); longer ones would run into the "
             "next command's, so they are cut and reported." % _cells_range(strings, "cmd")
             if v5 else
             "* Menu commands (`c` ids): `max_cells` (%d) letters fit the menus' boxes; up to 16 are taken "
             "(the table's slot), longer ones are cut and reported." % cmd_cells)]
    if arq:
        out = [x for x in out if not x.startswith(("* Speaker names", "* Menu commands"))]
    if v5 or arq:
        out += ["* Program strings (`e` ids): each within the Japanese's bytes (`max_cells` letters); a "
                "character the program writes in at run time (a drive letter, a digit) is `{X1}`..., kept "
                "in the English, which is placed so that it stays where the program writes it.  Longer "
                "ones are cut and reported.",
                "", "## Not handled", "",
                "* Text drawn into the artwork (the title logos, pictures)."]
    else:
        out += ["* Save slot names (`e` ids, in `ADL.EXE`): 16 letters (their 17-byte slots).",
            "", "## Not handled", "",
            "* Text drawn into the artwork (the title logos, pictures).",
            "* `ADL.EXE`'s disk prompts (insert the system or scenario disk): shown only when the game "
            "runs from floppies, never on the hard-disk release the patch builds."]
    for line in extra.get(name, {}).get("not_handled", []):
        out.append("* " + line)
    out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
    for t, r in tests.get(name, []):
        out.append("| %s | %s |" % (t, r))
    for line in extra.get(name, {}).get("remarks", []):
        out += ["", line]
    return out


def main():
    names = sys.argv[1:] or sorted(os.listdir(os.path.join(ROOT, "games")))
    adult = load("research", "adult_text.json", default={})
    clear = load("research", "clearance.json", default={})
    tests = load("research", "boot_tests.json", default={})
    extra = load("research", "notes_extra.json", default={})
    for name in names:
        here = os.path.join(ROOT, "games", name)
        cfg = load("games", name, "game.json")
        doc = load("games", name, "strings.json")
        if cfg is None or doc is None:
            continue
        if cfg.get("encoding") in ("jast", "jast_scm", "jast_boot", "jast_ribbon", "jast_cosmos", "jast_font12", "jast_menu12", "jast_typed"):
            out = jast_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "ai5":
            out = ai5_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "silky":
            out = silky_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "lmern":
            out = lmern_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "scoop":
            out = scoop_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "sys98":
            out = sys98_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "yjwar":
            out = yjwar_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") in ("aaru", "sgs21", "flz", "choreo"):
            out = {"aaru": aaru_notes, "sgs21": sgs21_notes, "flz": flz_notes,
                   "choreo": choreo_notes}[cfg["encoding"]](
                name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "active_halo":
            out = active_halo_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "active_if":
            out = active_if_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "ail":
            out = ail_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "sgs":
            out = sgs_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "cinema":
            out = cinema_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "zyx":
            out = zyx_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "elfai":
            out = elfai_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "ppdisk":
            out = ppdisk_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "panther":
            out = panther_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "chan":
            out = chan_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "adl":
            out = adl_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "gip":
            out = gip_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") == "adv98v":
            out = adv98v_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        if cfg.get("encoding") in ("illusion", "illusion_mes", "illusion_font24"):
            out = illusion_notes(name, cfg, doc, adult, clear, tests, extra)
            open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            print("wrote", name)
            continue
        key = cfg["key"]
        a = adult.get(key, {})
        heart = bool(a.get("adult"))
        strings = doc["strings"]
        kinds = {}
        for e in strings:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        done = sum(1 for e in strings if e["en"])
        out = ["# %s%s (Alice Soft)" % ("♥ " if heart else "", cfg["title"]), "",
               "> This patch's script is a **machine translation (AI/MTL)**, not a human "
               "translation. It will be retired if a human translation is released.", "",
               "Source image: `%s` (sha256 in `strings.json`)." % cfg["image"].replace("\\", "/")]
        for st in cfg.get("sets", []):
            if st.get("image"):
                out.append("Also: `%s` (scenario disk)." % st["image"])
        for name in cfg.get("n88", []):
            out.append("Also: `%s`." % name)
        c = clear.get(key)
        if c:
            res = c.get("result", "")
            out.append("Clearance: %s on %s (`research/clearance.json`)." % (
                "no English release or announcement found" if res == "clear" else res, c.get("checked", "")))
        out += ["", "## Engine", ""]
        eng = cfg.get("engine", "ADV.COM")
        out.append("Alice Soft **%s**, engine `%s`%s." % (
            SYSTEM.get(cfg["version"], cfg["version"]), eng,
            " in `%s/`" % cfg["game_dir"] if cfg["game_dir"] else ""))
        for st in cfg.get("sets", []):
            disks = ", ".join(v for v in st["disks"].values())
            out.append("* Scenario set `%s` %s%s%s." % (
                st["prefix"].rstrip(":"), disks,
                " on `%s`" % st["image"] if st.get("image") else "",
                " (%s command set)" % SYSTEM.get(st["version"], st["version"]) if st.get("version") else ""))
        for d in cfg.get("demos", []):
            out.append("* Opening/extra program `%s`: its hard-coded text is extracted as `demo` strings "
                       "and it gets the same display patch." % d)
        out.append("")
        out.append("Every script page disassembles and reassembles byte for byte "
                   "(`tools/verify_roundtrip.py`).")
        out += ["", DISPLAY.get(cfg["encoding"], ""), COMMON, "", "## Script", ""]
        out.append("%d strings: %s." % (len(strings), ", ".join("%d %s" % (n, k) for k, n in sorted(kinds.items()))))
        out.append("")
        out.append("Translation and the content classification (♥) are done by the translation model; "
                   "%d of %d strings have English so far." % (done, len(strings)))
        out += ["", "## Limits", "",
                "* Message lines wrap to the text window (its width from the script's window "
                "commands, or the widest Japanese line); `\\n` forces a break.",
                "* Menu items: each item's Japanese width (twice that in letters).",
                "* Hard-coded strings: their original byte length unless moved past the hook.",
                "", "## Not handled", "",
                "* Text drawn into the artwork (logos, panel labels).",
                "* Installer and driver messages."]
        for line in extra.get(name, {}).get("not_handled", []):
            out.append("* " + line)
        out += ["", "## Test status (np21w, `tools/boot_all.sh`)", "", "| Test | Result |", "|---|---|"]
        for t, r in tests.get(name, []):
            out.append("| %s | %s |" % (t, r))
        for t, r in extra.get(name, {}).get("tests", []):
            out.append("| %s | %s |" % (t, r))
        out.append("| Gameplay past the opening scenes, save/load, endings | not yet seen |")
        for line in extra.get(name, {}).get("remarks", []):
            out += ["", line]
        open(os.path.join(here, "notes.md"), "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
        print("wrote", name)


if __name__ == "__main__":
    main()
