"""Write games/<title>/notes.md for every Alice Soft and Illusion game from the facts.

    python tools/write_notes.py [folder ...]

Sources: game.json, strings.json, research/adult_text.json (the heart mark and
its basis), research/clearance.json, research/boot_tests.json (np21w results)
and research/notes_extra.json (per-game remarks that no file records).
"""
import json
import os
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
    if cfg["encoding"] == "illusion_mes":
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
    if heart:
        basis = a.get("summary", "")
        if basis.startswith("manual:"):
            out.append("♥ by the safety valve: %s. Claude translated %d strings before that point; "
                       "the rest is the maintainer's to translate." % (basis[len("manual:"):].strip(), done))
        else:
            out.append("♥ by the script-text scan (%s). The maintainer translates it; %d strings "
                       "have English so far." % (basis, done))
    else:
        out.append("No ♥ (%s). Claude translates it; %d of %d strings done." % (
            a.get("summary", "not scanned"), done, len(strings)))
    out += ["", "## Limits", ""]
    if cfg["encoding"] == "illusion_mes":
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
        if cfg.get("encoding") in ("illusion", "illusion_mes"):
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
        if heart:
            basis = a.get("summary", "")
            if basis.startswith("manual:"):
                out.append("♥ by the safety valve: %s. Claude translated %d strings before that point; "
                           "the rest is the maintainer's to translate." % (basis[len("manual:"):].strip(), done))
            else:
                out.append("♥ by the script-text scan (%s). The maintainer translates it; %d strings "
                           "have English so far." % (basis, done))
        else:
            out.append("No ♥ (%s). Claude translates it; %d of %d strings done." % (
                a.get("summary", "not scanned"), done, len(strings)))
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
