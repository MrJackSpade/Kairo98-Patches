"""Write games/<title>/notes.md for every Alice Soft game from the facts.

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
