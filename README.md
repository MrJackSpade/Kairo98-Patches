# PC-98 translation patch kit

> **The translations made here are machine translations (AI/MTL). They are not
> human translations.** They exist so games nobody has translated can be played
> at all. Where a human translation exists or has been announced by a team with
> a track record, we don't make one. We link to theirs instead, and when a human
> translation comes out for a game we've done, our version is retired.

This repo has two parts:

1. **An index of the PC-98 library and the human translations of it**
   ([index/INDEX.md](index/INDEX.md)). It links every finished, partial, and
   announced translation we know of, plus the teams behind them
   ([index/TEAMS.md](index/TEAMS.md)). Please support those teams directly.
2. **Tools that make machine translations possible** for the rest. They extract
   the Japanese script from a PC-98 disk image into JSON, the JSON gets machine
   translated, and the patcher writes it back into a copy of the image.

No game data lives in this repo. Every tool reads an image you supply and
writes a new one next to it; the originals are never modified.

## Policy

The full checklist for finishing a game, including clearance, the ♥ rule, patching,
testing and publishing, is **[DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md)**.


* **Skip** any game with a human English translation for the PC-98, or one
  announced for the PC-98 by a team that has finished releases
  (`index/TEAMS.md`). Those are listed in the index with their source and the
  date we checked. A translation of another version (e.g. a Win95 release)
  doesn't count: it's linked, and its script can be ported, but the game is
  still ours.
* A game announced only by a team with no finished releases is still fair game,
  since we don't wait for a new team to prove itself. The announcement stays
  linked.
* Every machine translation is labeled as one in this README, in its game's
  `notes.md`, and in the index.
* When a human translation of a game we've machine-translated appears, ours is
  marked superseded and removed, and the index links to theirs.
* **Two roles do the work,** decomp (tooling) and translation (script
  content). `AGENTS.md` defines them; every agent loads its own role's skill
  before starting. ♥ marks adult content. Until a script has been classified,
  a provisional mark comes from VNDB's erotic-content flag or the publisher's
  record.

## Layout

```
pc98tl/                 shared library
  disk.py               HDI / HDM images, read-write FAT12/16 (files can grow)
  alice_sys2.py         Alice Soft System 2 scenario disassembler/reassembler
  alice_sys2_tl.py      System 2 extract/patch (strings.json <-> ADISK.DAT, AG00.DAT)
  packfont.py           two English letters per 16px cell (1 byte per letter)
  text.py               Shift-JIS widths, word wrap, pseudo-translation filler
games/<title>/
  extract.py            image -> strings.json
  patch.py              image + strings.json -> patched image
  strings.json          Japanese text + empty English fields
  notes.md              engine notes, limits, test status
tools/                  one-off research helpers
```

## Making a patched game

Every game folder has the same `PATCH.BAT`. Double-click it to patch your copy
of the game from the collection (`C:\PC98`, or set `PC98_ROOT`), or drag the
game's disk image onto it. The patched image and its notes are written to
`games/<title>/output/`. You need Python 3 and `pip install -r requirements.txt`
(once).

## Workflow

```
pip install -r requirements.txt
python games/dalk/extract.py  "Dalk (v1.08) (uncensored).hdi"     # only needed to regenerate
# ...fill in the "en" fields of games/dalk/strings.json...
python games/dalk/patch.py    "Dalk (v1.08) (uncensored).hdi"  "Dalk (English).hdi"
```

Re-running `extract.py` keeps any English already in `strings.json`.

### strings.json

```json
{"id": "m00004", "kind": "msg",
 "jp": "［ＤＡＬＫ］基本メニュｰ\n 初ﾒｶﾗ  ：初ﾒｶﾗｼﾏｽ｡ ...",
 "en": "",
 "refs": ["p00:0de1"], "max_cells": 34}
```

* Translate `jp` into `en`, and leave every other field as it is.
* Empty `en` keeps the Japanese, so a partial translation is playable.
* Identical Japanese lines appear once, and the translation applies wherever the line is used.
* `\n` in `en` forces a line break. Otherwise the patcher wraps the text to fit the window.
* Tokens like `{X1}` are inserted at runtime (character names). Keep them in the English.
* `kind`: `msg` is dialogue or narration, `menu` is a choice, `name` is a stored name string, and `verb`/`obj` are command-menu captions.

### Machine translation helpers

```
python tools/mtl.py split games/dalk/strings.json batches/     # {id: jp} files, untranslated only
# translate each batch into {id: english}
python tools/mtl.py merge games/dalk/strings.json batches_en/  # fill "en" fields back in
python tools/mtl.py check games/dalk/strings.json              # progress + {X1} token mismatches
```

### Testing in an emulator

`tools/emu_shot.ps1` boots an image in np21w, sends keys and saves screenshots.
It works even with the desktop locked:

```
pwsh tools/emu_shot.ps1 -Hdi "Dalk (English).hdi" -Out shots/dalk -Steps "22:shot,0.5:enter,2:shot"
```

`patch.py IN OUT --pseudo` fills every string with filler 2.5 times as long as
the Japanese, tagged with its id, to find layout or size limits before any real
translation exists.

### Machine translation tips

Send the `jp` fields in batches together with their ids. Ask the model to return
`{id: english}` and to keep `{X1}`-style tokens and `\n` intact, then merge the
results back by id. Character names (the `name` entries) are worth fixing first
and passing to the translator as a glossary.

## Status

| Game | Engine | Extract | Patch | Boot-tested |
|---|---|---|---|---|
| Dalk (Alice Soft, 1992) | System 2 | yes | yes | yes: title, intro, first scenes; stress test passes |
