# ♥ Tenshi-tachi no Gogo III Bangaihen Hanseiban (JAST)

> This patch's script is a **machine translation (AI/MTL)**, not a human translation. It will be retired if a human translation is released.

Source image: `Tenshi-tachi no Gogo III Bangaihen Hanseiban/Tenshi-tachi no Gogo III Bangaihen Hanseiban [FD]/Tenshi-tachi no Gogo III Bangaihen Hanseiban (Disk A).hdm` (sha256 in `strings.json`).
Clearance: no PC-98 English release or announcement found on 2026-09-26 (`research/clearance.json`).

## Engine

JAST's later scene engine: 47 scene files (`*.SCM`), command tables then messages ended by `00 00`, found by count (`pc98tl/jast_scm.py`).
The floppies have no room for a longer script, so the patch lays the game out on a DOS hard-disk image (every disk's files in `TENSHI/`, started as the floppy's batch file does; the engine's select-disk call always picks the hard disk); the base image is the collection's `Kankin/Kankin [HD]/Kankin.hdi` with its own game removed.

## English display (`pc98tl/jast_scm.py`, `pc98tl/jast_console.py`)

* The engine prints on the PC-98 text layer, so ASCII is half-width already.
* English lines end with the engine's newline; the message window used to
  scroll a full box up, losing its start, so its scroll calls now go to a
  pager: it waits for a click or a key, clears the window and goes on at the
  top.  The pager sits in a zero-filled part of the program that the game
  never touches.

## Script

1262 strings (scene text).

♥ by the script-text scan (22 of 1309 strings match the sexual-vocabulary list (7 distinct terms)). The maintainer translates it; 0 strings have English so far.

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
| Hard-disk layout boots (drive-B reads go to the hard disk) | OK |
| Opening pictures | OK |
| Message window | OK: half-width filler inside the frame, wrapped between words |
| Paging on a full box | OK |
| Gameplay past the opening scenes, save/load, endings | not yet seen |
