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
   handed straight to the translation model
2. Patcher → patched copy of the HDI (engine hooks as needed, e.g. half-width font)
3. Stress test with `--pseudo`, then boot-test in np21w (`tools/emu_shot.ps1`)
4. Translation, the ♥ classification and any content flags: all done by the
   translation model (porting an existing English script when one exists for
   another platform); `tools/mtl.py` checks its output
5. Status shows in `index/INDEX.md`

## Status

**Ready to translate** means `games/<title>/strings.json` is final enough to
translate now; later tooling fixes carry translations forward. See
DEFINITION_OF_DONE.md for the full checklist.

| Game | Engine | Script | Translation | Patch | Boot test (filler) |
|---|---|---|---|---|---|
| ♥ Alice no Yakata III | alice-sys (System 3, 1 set) | extracted | **Ready to translate** | works, memory-neutral | OK (see notes) |
| ♥ Ambivalenz - Niritsu Haihan | alice-sys (System 3) | extracted | **Ready to translate** | works, memory-neutral | OK (see notes) |
| ♥ Ayumi-chan Monogatari | alice-sys (System 2) | extracted | **Ready to translate** | works, memory-neutral | OK (see notes) |
| ♥ Crescent Moon Girl | alice-sys (System 1, 2 sets) | extracted | **Ready to translate** (330 of 3575 done) | works, memory-neutral | OK (see notes) |
| ♥ D.P.S (Dream Program System) SG | alice-sys (System 1, 3 sets) | extracted | **Ready to translate** (46 of 10861 done) | works, memory-neutral | OK (see notes) |
| ♥ D.P.S (Dream Program System) SG Set 2 | alice-sys (System 1, 3 sets) | extracted | **Ready to translate** (48 of 16452 done) | works, memory-neutral; installs to a hard-disk image (floppies too small) | OK (see notes) |
| ♥ D.P.S (Dream Program System) SG Set 3 | alice-sys (System 1, 3 sets) | extracted | **Ready to translate** (86 of 13306 done) | works, memory-neutral; installs to a hard-disk image (floppies too small) | OK (see notes) |
| ♥ D.P.S Zenbu (All Dream Program System) | alice-sys (System 3, 4 sets) | extracted | **Ready to translate** | works, memory-neutral | OK (see notes) |
| ♥ Dalk | alice-sys (System 2) | extracted | **Ready to translate**; 291 done | works, memory-neutral | OK (see notes) |
| ♥ Dr. Stop! | alice-sys (System 2) | extracted | **Ready to translate** (102 of 7426 done) | works, memory-neutral | OK (see notes) |
| ♥ Gakuen King | alice-sys (System 3) | extracted | **Ready to translate** | works, memory-neutral | OK (see notes) |
| ♥ Intruder - Sakura Yashiki no Tansaku (FM Towns conversion) | alice-sys (System 1) | extracted | **Ready to translate** (1106 of 1966 done) | works, memory-neutral | OK (see notes) |
| ♥ Mugen Houyou | alice-sys (System 3) | extracted | **Ready to translate** | works, memory-neutral | OK (see notes) |
| ♥ Ningyo - Tsutako | alice-sys (System 3) | extracted | **Ready to translate** (0 of 290 done) | works, memory-neutral | OK (see notes) |
| ♥ Only You - Seikimatsu no Juliet-tachi | alice-sys (System 3) | extracted | **Ready to translate** | works, memory-neutral | OK (see notes) |
| ♥ Otome Senki | alice-sys (System 3) | extracted | **Ready to translate** (813 of 2086 done) | works, memory-neutral | OK (see notes) |
| ♥ Pro Student G | alice-sys (System 2) | extracted | **Ready to translate** | works, memory-neutral | OK (see notes) |
| ♥ Rance 4.1+4.2 Hint Disk (Hashiri Onna II - Running Girls) | alice-sys (System 3) | extracted | **Ready to translate** (270 of 1013 done) | works, memory-neutral | OK (see notes) |
| ♥ Super D.P.S (Dream Program System) | alice-sys (System 2, 3 sets) | extracted | **Ready to translate** (176 of 9508 done) | works, memory-neutral | OK (see notes) |
| ♥ Toushin Toshi II - Soshite, Sorekara | alice-sys (System 3) | extracted | **Ready to translate** (1799 of 5485 done) | works, memory-neutral | OK (see notes) |
| ♥ Uchuu Kaitou Funny Bee | alice-sys (System 3) | extracted | **Ready to translate** | works, memory-neutral | OK (see notes) |
| ♥ Abunai Tengu Densetsu | alice-sys (System 1 scenario, N88-BASIC engine) | extracted | **Ready to translate** (98 of 4244 done) | works, memory-neutral; adds cylinders 77-81 to the disks for the longer script | OK (see notes) |
| ♥ Hyouryuu | tmexec (Illusion) | extracted | **Ready to translate** | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Kankin | tmexec (Illusion) | extracted | **Ready to translate** | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Kitoujima Joshi Keimusho | tmexec (Illusion) | extracted | **Ready to translate** (6 of 2602 done) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Mokkoriman RPG | tmexec (Illusion) | extracted | **Ready to translate** | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Rankou Nyotaitsuri - Mokkoriman no Nani de Nushitsuri | tmexec (Illusion) | extracted | **Ready to translate** (45 of 301 done) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Red Cobra | tmexec (Illusion) | extracted | **Ready to translate** (149 of 643 done) | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Ura Mansion Hakkin | tmexec (Illusion) | extracted | **Ready to translate** | works, pager in a <1 KB DOS block | OK (see notes) |
| ♥ Yami no Ryousen | tmexec (Illusion), EXEPACK engine | extracted | **Ready to translate** | works; hard-disk layout (floppies full), pager in a <1 KB DOS block | OK (see notes) |
| ♥ Seisenshi Mokkoriman | Illusion MES.D (older engine) | extracted | **Ready to translate** | works; native half-width font, window pages instead of scrolling | OK (see notes) |
| ♥ Moeru Asoko no Paipai Yuugi | Illusion C engine, 24-dot font (EXEPACK) | extracted | **Ready to translate** | works; letter pairs through the kanji-ROM path, hooks in a <1 KB DOS block | OK (see notes) |
| Angel Army | Illusion C engine, 24-dot font (EXEPACK) | extracted | **Translated** (297/297) | works; letter pairs through the kanji-ROM path, quote boxes turned horizontal | OK (see notes) |
| ♥ Deep | jast OVL | extracted | **Ready to translate** | works | OK (see notes) |
| ♥ Eden no Kaori | jast OVL | extracted | **Ready to translate** | works | OK (see notes) |
| ♥ Hunting Roulette - Totsugeki Bakkon Street II | jast OVL | extracted | **Ready to translate** | works; engine strings in place | OK (see notes) |
| ♥ Setsujuu - Yuganda Kioku | jast OVL | extracted | **Ready to translate** | works | OK (see notes) |
| ♥ Tenshi-tachi no Gogo Collection | jast OVL | extracted | **Ready to translate** | works | OK (see notes) |
| ♥ Tenshi-tachi no Gogo Collection 2 | jast OVL | extracted | **Ready to translate** | works | OK (see notes) |
| ♥ Tenshi-tachi no Gogo Tenkousei | jast OVL | extracted | **Ready to translate** | works; engine strings in place | OK (see notes) |
| ♥ Tenshi-tachi no Hohoemi | jast OVL | extracted | **Ready to translate** | works; engine strings in place | OK (see notes) |
| ♥ Shuukan From H | jast OVL | extracted | **Ready to translate** | works; engine strings in place | OK (see notes) |
| ♥ Super Ultra Mucchin Puripuri Cyborg Marilyn DX | jast OVL | extracted | **Ready to translate** | works; engine strings in place | OK (see notes) |
| ♥ Tenshi-tachi no Gogo VI - My Fair Teacher | jast SCM | extracted | **Ready to translate** | works | OK (see notes) |
| ♥ Cosmos Club | jast boot disk (D88, text blob) | extracted | **Ready to translate** | works; self-booting D88 floppy set, message window pages | OK (see notes) |
| ♥ Gomen ne Angel - Yokohama Monogatari | jast boot disk | extracted | **Ready to translate** | works; self-booting floppy set | OK (see notes) |
| ♥ Tenshi-tachi no Gogo II - Minako | jast font12 (typed commands) | extracted | **Ready to translate** | works; self-booting D88 floppy set, own 12x10 font, letter pairs, message window pages | OK (see notes) |
| Tenshi-tachi no Gogo II Bangaihen | jast menu12 (menus) | extracted | **Ready to translate** | works; self-booting D88 floppy set, own 12x10 font, letter pairs, main box and opening window page | OK (see notes) |
| Tenshi-tachi no Gogo | jast typed (first engine) | extracted | **Ready to translate** | works; self-booting N88-layout floppy, own 12x10 font, letter pairs, typed English commands, box pages without losing lines | OK (see notes) |
| Tenshi-tachi no Gogo Bangaihen | jast typed (scene viewer) | extracted | **Ready to translate** | works; self-booting N88-layout floppy, own 12x10 font, letter pairs, box pages without losing lines | OK (see notes) |
| ♥ Tenshi-tachi no Gogo III - Ribbon | jast boot disk (blob) | extracted | **Ready to translate** | works; self-booting floppy set, scenes read from disk, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo III Bangaihen | jast boot disk | extracted | **Ready to translate** | works; self-booting floppy set, message window pages | OK (see notes) |
| ♥ Yoru no Tenshi-tachi - Shitetsu Ensen Satsujin Jiken | jast boot disk (JIS) | extracted | **Ready to translate** | works; self-booting floppy set, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo IV - Yuko | jast boot disk | extracted | **Ready to translate** | works; self-booting floppy set, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo V - Nerawareta Tenshi | jast SCM | extracted | **Ready to translate** | works; floppy set, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo III Bangaihen Hanseiban | jast SCM | extracted | **Ready to translate** | works; hard-disk layout, message window pages | OK (see notes) |
| ♥ Tenshi-tachi no Gogo Special II | jast SCM | extracted | **Ready to translate** | works; hard-disk layout | OK (see notes) |
| Pia Carrot e Youkoso!! | adv98v (Adv98V 1.75) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged, hero name inline, procedure slots checked | OK (see notes) |
| Naomi - Bishoujo-tachi no Yakata | adv98v (Adv98V 1.70) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged | OK (see notes) |
| Angel (U-Jin Presents) | adv98v (Adv98V 1.70) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged, name tags and hero name inline, procedure slots and MEC buffer checked | OK (see notes) |
| Chiemi | adv98v (Adv98V 1.71) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged to the box its procedures set | OK (see notes) |
| Jinmon Yuugi | adv98v (Adv98V 1.75) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged | OK (see notes) |
| Sayaka - Gibo | adv98v (Adv98V 1.73) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged (its written-out message end) | OK (see notes) |
| Kurutta Kajitsu | adv98v (Adv98V 1.70, floppy set) | extracted | **Ready to translate** | works; floppies laid out on a hard disk, half-width ASCII messages wrapped and paged, full-width menu items | OK (see notes) |
| Necronomicon | adv98v (Adv98V 1.73) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged | OK (see notes) |
| Saori - Bishoujo-tachi no Yakata | adv98v (Adv98V 1.70.33) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages paged a line at a time by the key wait, full-width menu items | OK (see notes) |
| Akiko Gold | adv98v (Adv98V 1.74) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged in the 2-line box (key wait between pages) | OK (see notes) |
| Jankirou | adv98v (Adv98V, floppy set) | extracted | **Ready to translate** | works; floppies laid out on a hard disk, half-width ASCII strings, messages wrapped and paged, scripts in MES and MEC folders | OK (see notes) |
| Miho | adv98v (Adv98V 1.71) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged to the box its procedures set | OK (see notes) |
| Doki Doki Vacation | adv98v (Adv98V 1.74, floppy set) | extracted | **Ready to translate** | works; eight floppies laid out on a hard disk, half-width ASCII strings, name tags and messages wrapped and paged | OK (see notes) |
| Mayumi | adv98v (Adv98V 1.70.54) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged in the 3-line box, full-width menu items | OK (see notes) |
| Will no Dengon | adv98v (Adv98V 1.70.54) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged in the 2-line box, full-width menu items | OK (see notes) |
| Cosmic Psycho | adv98v (ADVH 1.53, floppy set) | extracted | **Ready to translate** | works; floppies laid out on a hard disk at the root, ADVH.EXE patched for half-width letters and repacked, disk-change waits skipped, one-line boxes paged | OK (see notes) |
| Can Can Bunny Premiere | adv98v (Adv98V 1.70.53) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages, full-width menu items | **Blocked**: past the opening not reached; the name-entry module takes no emulated input (mouse, keyboard, and skipping its call all tried) |
| Can Can Bunny Extra | adv98v (Adv98V 1.70.57) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged in the 2-line box | OK (see notes) |
| Miki | adv98v (Adv98V 1.70, floppy) | extracted | **Ready to translate** | works; floppy laid out on a hard disk, half-width ASCII messages wrapped and paged in the 3-line box, full-width menu items | OK (see notes) |
| Travel Junction | adv98v (Adv98V 1.75.63) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings (the build tokenizes, rebuilds and patches; no patched text reached on screen) | **Blocked**: no patched text reached; the setup wizard and the title menu take no emulated input (wizard clicked, wizard skipped in a test image, title tried with keys and mouse) |
| Dracula Hakushaku | adv98v (Adv98V 1.70.54) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged in the bottom box, full-width labels | OK (see notes) |
| Akiko Premium Version | adv98v (Adv98V 1.70.54) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged in the 3-line box (key wait between pages), full-width menu items | OK (see notes) |
| Demon City | adv98v (Adv98V 1.71.58) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII strings, messages wrapped and paged, name tags and names shown from variables inline, the opening roll's text file | OK (see notes) |
| Arabesque | adv98v (Adv98V 1.72.59) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged in the 3-line framed box | OK (see notes) |
| Virtuacall | adv98v (Adv98V 1.74.61) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged, the name window's labels in place | OK (see notes) |
| Virtuacall 2 | adv98v (Adv98V 1.75.62) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged around the hero's name, the name window's labels in place | OK (see notes) |
| Injuu Gakuen - La Blue Girl | adv98v (Adv98V 1.72.59) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged under the speaker's name, menus at their places; the system menu file (loaded into the engine's MEC buffer, no room to grow) keeps its size | OK (see notes) |
| Shinjuku Monogatari | adv98v (Adv98V 1.70.53) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged in the 2-line box, menus at their places | OK (see notes) |
| Dragon Eyes | adv98v (ADVH 1.31A, floppy set) | extracted | **Ready to translate** | works; three floppies laid out on a hard disk with the game's own mouse driver, ADVH patched for half-width letters (8x16 BIOS glyphs), messages wrapped and paged in the 2-line box, menus at their places | OK (see notes) |
| Hare Nochi Munasawagi! | adv98v (Adv98V 1.75.62) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged, speaker tags and the hero's name on the line, menus as fixed-length string variables, the name window's labels in place | OK (see notes) |
| Can Can Bunny Spirits | adv98v (Adv98V 1.70.39, floppy set) | extracted | **Ready to translate** | works; three floppies laid out on a hard disk (the floppy boots straight into AdvBIOS), half-width ASCII messages wrapped and paged, menus at their places, name tags in full-width letters (this engine hangs on an ASCII string in a procedure) | OK (see notes) |
| Custom Mate 3 | adv98v (Adv98V 1.75.62) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged in the 4-line box, speaker tags on their line, menus at their places, the name window's labels in place | OK (see notes) |
| Youjuu Kyoushitsu | adv98v (Adv98V 1.74.61) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged under the speaker's tag, menus and submenus at their places (an item whose label a flag picks counts as an item); the system menu file keeps its size in the MEC buffer | OK (see notes) |
| Koroshi no Dress 3 | adv98v (Adv98V 1.70.54) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged, menus in full-width letters (this build draws menus from Shift-JIS only) | OK (see notes) |
| Yumeji - Asakusa Kitan | adv98v (Adv98V 1.70.52) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged, menus in full-width letters (this build draws menus from Shift-JIS only) | OK (see notes) |
| Kanako | adv98v (Adv98V 1.75.63) | extracted | **Ready to translate** | works; hard-disk image, half-width ASCII messages wrapped and paged in the 2-line box, menus at their places | OK (see notes) |
