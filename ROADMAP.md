# Roadmap

Goal: every text-heavy game in the collection playable in English. The order
below is only priority; nothing gets dropped, except games a human team covers
(see the policy in README.md). Before starting any game, check
`index/INDEX.md`: it must not have status *human translation* or *announced by
proven team*, and the announcement sweep (`research/announced.json`) should be
recent.

## Order

1. **Alice Soft** (`alice-sys`): Funny Bee, Only You, Prostudent G,
   AmbivalenZ, Gakuen King, Mugen Houyou, Dalk (patcher done, needs MTL), then
   the rest. *Skipped:* Toushin Toshi II (BabaJeanmel & Alpharobo, announced,
   25%).
2. **JAST** (`jast`, 13 untranslated on their own engine).
3. **Illusion** (`tmexec`: the same engine also covers Heart Soft, Interheart,
   Pro Illusion and Dott Plan, 29 untranslated).
4. **Fairytale / Cocktail Soft** (`adv98v`, 87 untranslated; engine already cracked by
   existing patches).
5. Studios the user knows: Konami, Koei, Compile, Enix, Square (one-off engines,
   case by case).
6. Elf + Silky's (`elf-ai5`, `silkys`), D.O., Dante98 RPGs, and every other
   family in `index/ENGINES.md`, largest untranslated count first.

## Per game

1. Extractor → `games/<title>/strings.json` (JP text as displayed, empty `en`),
   then `tools/adult_scan.py` sets the final ♥ mark from the script text
2. Patcher → patched copy of the HDI (engine hooks as needed, e.g. half-width font)
3. Stress test with `--pseudo`, then boot-test in np21w (`tools/emu_shot.ps1`)
4. Translation: port an existing English script when one exists for another
   platform. Otherwise, **no ♥**: translated in this repo; **♥**: the maintainer
   machine-translates it with a separate model via `tools/mtl.py`
5. Status shows in `index/INDEX.md`

## Status

| Game | Engine | Extract | Patch | Boot test | Translation |
|---|---|---|---|---|---|
| ♥ Dalk | alice-sys (System 2) | done | done | done | UI/names done; script goes to the maintainer's model |
| ♥ Uchuu Kaitou Funny Bee | alice-sys (System 3) | done | done | intro + menus (filler) | script goes to the maintainer's model |
