# ♥ Tenshi-tachi no Gogo V - Nerawareta Tenshi (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Gogo V - Nerawareta Tenshi/Tenshi-tachi no Gogo V - Nerawareta Tenshi [FD]/Tenshi-tachi no Gogo V - Nerawareta Tenshi (Disk A).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's later scene engine: 85 scene files (`*.SCM`), command tables then messages ended by `00 00`, found by count (`pc98tl/jast_scm.py`).
Every floppy's scene files are patched; the output is the full disk set.

## English display (`pc98tl/jast_scm.py`, `pc98tl/jast_console.py`)

* The engine prints on the PC-98 text layer, so ASCII is half-width already.
* English lines end with the engine's newline; the message window used to
  scroll a full box up, losing its start, so its scroll calls now go to a
  pager: it waits for a click or a key, clears the window and goes on at the
  top.  The pager sits in a zero-filled part of the program that the game
  never touches.

## Script

1959 strings (scene text).

♥ by the script-text scan (6 of 2002 strings match the sexual-vocabulary list (3 distinct terms)). The maintainer translates it; 0 strings have English so far.

## Limits

* Speaker lines are written `Name: text` (the name up to 14 columns, or a `%nnn` placeholder); `\n` starts a new paragraph.
* A scene file, with its English appended, must fit the engine's 16 KB scene buffer; the patcher leaves a scene that would not fit in Japanese and reports it.

## Not handled

* Text drawn into the artwork (logos, menus drawn as pictures).
* Strings hard-coded in the engine program (menus, item names).
* Installer and driver messages.

## Test status (np21w, `tools/boot_all.sh`)

| Test | Result |
|---|---|
| Title (floppy set, patched scenes on every disk) | OK |
| Message window, first page | OK: half-width filler inside the frame, wrapped between words |
| Long message: waits at a full box, next page after a click or key | OK |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
