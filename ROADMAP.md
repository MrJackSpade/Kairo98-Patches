# Roadmap

Goal: every text-heavy game in the collection playable in English. The order
below is only priority; nothing gets dropped, except games a human team covers
(see the policy in README.md). Before starting any game, check
`index/INDEX.md`: it must not have status *human translation* or *announced by
proven team*, and the announcement sweep (`research/announced.json`) should be
recent.

## Order

1. **Alice Soft** (`alice-sys`): Funny Bee, Only You, Prostudent G,
   AmbivalenZ, Gakuen King, Mugen Houyou, Dalk and the rest: every title is
   extracted and patchable (see the status table). *Skipped:* Toushin Toshi II (BabaJeanmel & Alpharobo, announced,
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

A game is finished when it meets **[DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md)**.
The list below summarizes it.

**Required layout** (checked by `tools/check_games.py`): every `games/<title>/`
holds `game.json`, `extract.py`, `patch.py` (contract: `patch.py IN OUT
[--pseudo]`), `strings.json`, `notes.md` with the machine-translation notice,
and **`PATCH.BAT`, byte-identical to `tools/PATCH.BAT.template`**. Double-clicking
`PATCH.BAT` patches the collection copy of the game (or an image dropped onto it)
and writes `output/<title> (English MTL).hdi` plus `notes.md`. That is the one
standard way to produce a patched game, for every game.


1. Extractor → `games/<title>/strings.json` (JP text as displayed, empty `en`),
   then `tools/adult_scan.py` sets the final ♥ mark from the script text
2. Patcher → patched copy of the HDI (engine hooks as needed, e.g. half-width font)
3. Stress test with `--pseudo`, then boot-test in np21w (`tools/emu_shot.ps1`)
4. Translation: port an existing English script when one exists for another
   platform. Otherwise, **no ♥**: translated in this repo; **♥**: the maintainer
   machine-translates it with a separate model via `tools/mtl.py`
5. Status shows in `index/INDEX.md`

## Status

**Ready to translate** means `games/<title>/strings.json` is final enough to
translate now; later tooling fixes carry translations forward. See
DEFINITION_OF_DONE.md for the full checklist.

| Game | Engine | Script | Translation | Patch | Boot test (filler) |
|---|---|---|---|---|---|
| ♥ Alice no Yakata III | alice-sys (System 3, 1 set) | extracted | **Ready to translate** (maintainer) | works, memory-neutral | OK (see notes) |
| ♥ Ambivalenz - Niritsu Haihan | alice-sys (System 3) | extracted | **Ready to translate** (maintainer) | works, memory-neutral | OK (see notes) |
| ♥ Ayumi-chan Monogatari | alice-sys (System 2) | extracted | **Ready to translate** (maintainer) | works, memory-neutral | OK (see notes) |
| ♥ Crescent Moon Girl | alice-sys (System 1, 2 sets) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 330 of 3575) | works, memory-neutral | OK (see notes) |
| ♥ D.P.S (Dream Program System) SG | alice-sys (System 1, 3 sets) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 46 of 10861) | works, memory-neutral | OK (see notes) |
| ♥ D.P.S (Dream Program System) SG Set 2 | alice-sys (System 1, 3 sets) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 48 of 16452) | works, memory-neutral; installs to a hard-disk image (floppies too small) | OK (see notes) |
| ♥ D.P.S (Dream Program System) SG Set 3 | alice-sys (System 1, 3 sets) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 86 of 13306) | works, memory-neutral; installs to a hard-disk image (floppies too small) | OK (see notes) |
| ♥ D.P.S Zenbu (All Dream Program System) | alice-sys (System 3, 4 sets) | extracted | **Ready to translate** (maintainer) | works, memory-neutral | OK (see notes) |
| ♥ Dalk | alice-sys (System 2) | extracted | **Ready to translate** (maintainer); 291 done | works, memory-neutral | OK (see notes) |
| ♥ Dr. Stop! | alice-sys (System 2) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 102 of 7426) | works, memory-neutral | OK (see notes) |
| ♥ Gakuen King | alice-sys (System 3) | extracted | **Ready to translate** (maintainer) | works, memory-neutral | OK (see notes) |
| ♥ Intruder - Sakura Yashiki no Tansaku (FM Towns conversion) | alice-sys (System 1) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 1106 of 1966) | works, memory-neutral | OK (see notes) |
| ♥ Mugen Houyou | alice-sys (System 3) | extracted | **Ready to translate** (maintainer) | works, memory-neutral | OK (see notes) |
| ♥ Ningyo - Tsutako | alice-sys (System 3) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 0 of 290) | works, memory-neutral | OK (see notes) |
| ♥ Only You - Seikimatsu no Juliet-tachi | alice-sys (System 3) | extracted | **Ready to translate** (maintainer) | works, memory-neutral | OK (see notes) |
| ♥ Otome Senki | alice-sys (System 3) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 813 of 2086) | works, memory-neutral | OK (see notes) |
| ♥ Pro Student G | alice-sys (System 2) | extracted | **Ready to translate** (maintainer) | works, memory-neutral | OK (see notes) |
| ♥ Rance 4.1+4.2 Hint Disk (Hashiri Onna II - Running Girls) | alice-sys (System 3) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 270 of 1013) | works, memory-neutral | OK (see notes) |
| ♥ Super D.P.S (Dream Program System) | alice-sys (System 2, 3 sets) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 176 of 9508) | works, memory-neutral | OK (see notes) |
| ♥ Toushin Toshi II - Soshite, Sorekara | alice-sys (System 3) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 1799 of 5485) | works, memory-neutral | OK (see notes) |
| ♥ Uchuu Kaitou Funny Bee | alice-sys (System 3) | extracted | **Ready to translate** (maintainer) | works, memory-neutral | OK (see notes) |
| ♥ Abunai Tengu Densetsu | alice-sys (System 1 scenario, N88-BASIC engine) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 98 of 4244) | works, memory-neutral; adds cylinders 77-81 to the disks for the longer script | OK (see notes) |
| ♥ Hyouryuu | tmexec (Illusion) | extracted | **Ready to translate** (maintainer) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Kankin | tmexec (Illusion) | extracted | **Ready to translate** (maintainer) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Kitoujima Joshi Keimusho | tmexec (Illusion) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 6 of 2602) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Mokkoriman RPG | tmexec (Illusion) | extracted | **Ready to translate** (maintainer) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Rankou Nyotaitsuri - Mokkoriman no Nani de Nushitsuri | tmexec (Illusion) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 45 of 301) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Red Cobra | tmexec (Illusion) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, Claude did 149 of 643) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Ura Mansion Hakkin | tmexec (Illusion) | extracted | **Ready to translate** (maintainer) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Yami no Ryousen | tmexec (Illusion), EXEPACK engine | extracted | **Ready to translate** (maintainer) | works; hard-disk layout (floppies full), pager in a <1 KB DOS block | OK (see notes) |
| ♥ Seisenshi Mokkoriman | Illusion MES.D (older engine) | extracted | **Ready to translate** (maintainer) | works; native half-width font, window pages instead of scrolling | OK (see notes) |
| ♥ Moeru Asoko no Paipai Yuugi | Illusion C engine, 24-dot font (EXEPACK) | extracted | **Ready to translate** (maintainer; ♥ by the safety valve, 0 translated) | works; letter pairs through the kanji-ROM path, hooks in a <1 KB DOS block | OK (see notes) |
| Angel Army | Illusion C engine, 24-dot font (EXEPACK) | extracted | **Translated** (Claude, 297/297) | works; letter pairs through the kanji-ROM path, quote boxes turned horizontal | OK (see notes) |
| ♥ Deep | jast OVL | extracted | **Ready to translate** (maintainer) | works | OK (see notes) |
| ♥ Eden no Kaori | jast OVL | extracted | **Ready to translate** (maintainer) | works | OK (see notes) |
| ♥ Hunting Roulette - Totsugeki Bakkon Street II | jast OVL | extracted | **Ready to translate** (maintainer) | works | boots; message window not yet reached |
| ♥ Setsujuu - Yuganda Kioku | jast OVL | extracted | **Ready to translate** (maintainer) | works | OK (see notes) |
| ♥ Tenshi-tachi no Gogo Collection | jast OVL | extracted | **Ready to translate** (maintainer) | works | OK (see notes) |
| ♥ Tenshi-tachi no Gogo Collection 2 | jast OVL | extracted | **Ready to translate** (maintainer) | works | OK (see notes) |
| ♥ Tenshi-tachi no Gogo Tenkousei | jast OVL | extracted | **Ready to translate** (maintainer) | works | boots; message window not yet reached |
| ♥ Tenshi-tachi no Hohoemi | jast OVL | extracted | **Ready to translate** (maintainer) | works | boots; message window not yet reached |
| ♥ Shuukan From H | jast OVL | extracted | **Ready to translate** (maintainer) | works | boots; message window not yet reached |
| ♥ Super Ultra Mucchin Puripuri Cyborg Marilyn DX | jast OVL | extracted | **Ready to translate** (maintainer) | works | boots; message window not yet reached |
| ♥ Tenshi-tachi no Gogo VI - My Fair Teacher | jast SCM | extracted | **Ready to translate** (maintainer) | works | OK (see notes) |
| ♥ Gomen ne Angel - Yokohama Monogatari | jast boot disk | extracted | **Ready to translate** (maintainer) | works; self-booting floppy set | OK (see notes) |
| ♥ Tenshi-tachi no Gogo III - Ribbon | jast boot disk (blob) | extracted | **Ready to translate** (maintainer) | works; self-booting floppy set, scenes read from disk, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo III Bangaihen | jast boot disk | extracted | **Ready to translate** (maintainer) | works; self-booting floppy set, message window pages | OK (see notes) |
| ♥ Yoru no Tenshi-tachi - Shitetsu Ensen Satsujin Jiken | jast boot disk (JIS) | extracted | **Ready to translate** (maintainer) | works; self-booting floppy set, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo IV - Yuko | jast boot disk | extracted | **Ready to translate** (maintainer) | works; self-booting floppy set, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo V - Nerawareta Tenshi | jast SCM | extracted | **Ready to translate** (maintainer) | works; floppy set, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo III Bangaihen Hanseiban | jast SCM | extracted | **Ready to translate** (maintainer) | works; hard-disk layout, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo Special II | jast SCM | extracted | **Ready to translate** (maintainer) | works; hard-disk layout | OK (see notes) |
