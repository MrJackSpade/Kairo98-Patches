# Excluded titles

Games whose disk images were removed from the collection because the text met
the exclusion rule in the decomp role's skill: explicit sexual content with a
character who is unmistakably a young child. The rule is kept narrow on
purpose; it doesn't cover teenagers, school-age romance, or anything
ambiguous.

Each entry keeps the evidence and what was removed. The records and work
around the game (clearance, index entries) stay. **Acknowledged** records
when the maintainer was told; until then, every session raises the entry.

---

## Totsugeki! Bakkon Street (JAST)

* **Index key:** `Jast.zip/Totsugeki! Bakkon Street`
* **Found:** 2026-09-27, during a format survey. The first 700 bytes of the
  first event scene file were dumped to learn the text encoding.
* **Acknowledged:** yes, 2026-09-27 (discussed with the maintainer in the
  session that set up this document).

### What the game is

A board and card game (`BOS/BOS.EXE`, `CARD.DAT`) with about 35 event scene
files, `S001.MSG` to `S035.MSG`. Most have a matching `-H` file
(`S001-H.MSG`...), the sex-scene version of the event. Landing on board
events triggers the scenes. Public descriptions call it a board game, which
is its main loop.

### Evidence (`BOS/S001-H.MSG`, the first 700 bytes; nothing past them was read)

No age is stated in the part that was read. The character, "Yunyun", is
written as a small child by several markers together:

* she speaks in toddler baby-talk throughout ("でしゅ" for "desu") and calls
  the player "onii-tan";
* she's thrilled to be given candy;
* she doesn't know what the word "sex" means when the player says it;
* she's proud that she can take her clothes off "all by herself";
* she plans to play on the swings the next day.

The player frames it as "playing doctor". The text then goes into explicit
sexual activity with her: she says she "feels strange", then come licking
sound effects, her saying it tickles, and repeated thrusting sound effects,
where the dump ended.

Not known: whether an age is stated elsewhere, and what the other `-H` files
contain.

### Removed from `E:\PC98\Totsugeki! Bakkon Street\` (2026-09-27)

| File | Bytes | sha256 |
|---|---|---|
| `[FD]/Totsugeki! Bakkon Street (Disk A).hdm` | 1261568 | `95c3cf215dffcf423ecb51855a0c8835f1616dcebbdb9a280c37ba1512a700bb` |
| `[FD]/Totsugeki! Bakkon Street (Disk B).hdm` | 1261568 | `72def0d1bd72b7822fa9136d9486d405c1c3f34e4689984d998e29f8aa2bfdc4` |
| `[FD]/alts/Totsugeki! Bakkon Street (Disk A) [Alt 1].hdm` | 1261568 | `eea5ad1ed36b0d32e94ea226d63343be4464a43743d5735acb9288a83a6b5cde` |
| `[HD]/Totsugeki! Bakkon Street.hdi` | 10479616 | `b1a16cfbfd78a627beca7132d992f21a193df5ddc5424a2507fc7acee8df29fd` |

There was no local zip: `Jast.zip` had already been unpacked and deleted. The
original `Jast.zip` on the NAS still contains the game, and wasn't touched.
Nothing was ever extracted into the repo.

---

## Dangel (Mink)

* **Index key:** `Mink.zip/Dangel`
* **Found:** 2026-10-12, while debugging the patcher's test build. The build
  stopped the game at start-up; to find out why, the strings of the start-up
  script (`DANGEL/B.ARC`, member 1, in the CD version's hard-disk install)
  were listed to see what the script draws.
* **Acknowledged:** yes, 2026-10-12 (the maintainer, in the session that found it).

### What the game is

An RPG on its own script engine (`3RDO.EXE`). The scenario is compiled
scripts inside the `*.ARC` archives, each with a block of Shift-JIS strings.
The start-up script holds the title's PCM-mode menu, the scrolling prologue
text and the opening scene.

### Evidence (`DANGEL/B.ARC` member 1, its string list)

The opening scene, right after the prologue text, is an explicit sex scene
between an adult woman and a character the script calls "男の子" (boy). In
the middle of it the woman asks him whether he is really nine years old (a
stated age of 9), and the scene goes on with him. The lines around it
describe the sexual activity directly (moaning, sound effects, the acts
named); the scene isn't implied or off-screen.

Not known: anything past this member's strings. Nothing else was read.

### Removed from `E:\PC98\Dangel\` (2026-10-12)

| File | Bytes | sha256 |
|---|---|---|
| `Dangel (CD version) [HD]/Dangel (CD version).hdi` | 20955136 | `e40098c3f49dcfa82dd317dd103a7787e503a4e6a2d119db57e8a73a064432b8` |
| `Dangel (FD version with Special Disk) [HD]/Dangel (FD version with Special Disk).hdi` | 20955136 | `064eeeb70ca60aaae9858cf3afc9d889c229acce96331882763ab50a32f21f26` |
| `Dangel (Special Disk) [FD]/Dangel (Special Disk) (Disk 1).hdm` | 1261568 | `b528cbfdf9ce0c4273c6c34e81c5eafe7e2ae4eca43efb41ec7ab14fde668c9a` |
| `Dangel (Special Disk) [FD]/Dangel (Special Disk) (Disk 2).hdm` | 1261568 | `686b36da10488547b43957148c7caa17693e46784050a38b58f6baf7bd2e3fa4` |
| `Dangel (Special Disk) [FD]/Dangel (Special Disk) (Disk 3).hdm` | 1261568 | `a6065af944d765ad5f96b82887c46b44317af92dc7b59e54f61129fe4f82caed` |
| `Dangel (Special Disk) [FD]/Dangel (Special Disk) (Disk 4).hdm` | 1261568 | `8e3d1087840b8114026d206344a57e452a98061776dd9337486a7d1fc4301fe6` |
| `Dangel (Special Disk) [FD]/alts/Dangel (Special Disk) (Disk 1) [Alt 1].hdm` | 1261568 | `b4f34849669f2b40a8373e1bda5bcdea48c519da31b71e26d012b91b9b6dd221` |
| `Dangel (Special Disk) [FD]/alts/Dangel (Special Disk) (Disk 2) [Alt 1].hdm` | 1261568 | `01dd9b06e7b2d5f4ecffaaf0831ae2530619fcdbbf1c415cef372d45a0eee62a` |
| `Dangel (Special Disk) [FD]/alts/Dangel (Special Disk) (Disk 3) [Alt 1].hdm` | 1261568 | `7f28bf764d1057f36bf21836f2905c325592d23f5e18ca8eea68e90955d976cd` |
| `Dangel [CD]/Dangel.ccd` | 772 | `c976ed63a726f4df7bdfefaf307096b2cead6866d8a09e22ede49b27efe13533` |
| `Dangel [CD]/Dangel.img` | 298943904 | `4fb986b975fba9df365169762ecc0fcfb879ded29183265b142016a5d05945c7` |
| `Dangel [CD]/Dangel.sub` | 12201792 | `8c3c8c4e40f15f3fa54ca792ea425394ac910690747298d4c5a37571d8e7cf7d` |
| `Dangel [FD]/Dangel (Disk 01).hdm` | 1261568 | `ceea8dd91a61f8ed88165a40d4d47c2e2da03c52fabbcc59a7cea3f392384e62` |
| `Dangel [FD]/Dangel (Disk 02).hdm` | 1261568 | `407ae09295db508d0cc7b2c3eec5d68f33562fb0568c69e150ba28959e54ff58` |
| `Dangel [FD]/Dangel (Disk 03).hdm` | 1261568 | `7704d11ad5567a3c9237470508f0e2164268ca1ab2a34586ab9a396476fbdc41` |
| `Dangel [FD]/Dangel (Disk 04).hdm` | 1261568 | `783da28957e047b62f999ddd7290c4c56706d0c26d83c87ec6d0e7108de4fbd7` |
| `Dangel [FD]/Dangel (Disk 05).hdm` | 1261568 | `e3394640577deb7b01ebd8b23d3272d7b5f12029a78981f6a4d69b7977f5aa33` |
| `Dangel [FD]/Dangel (Disk 06).hdm` | 1261568 | `6b9f741eea0150cf9b3fada28be2a865137c561ad364fb300e9bcad541c3198d` |
| `Dangel [FD]/Dangel (Disk 07).hdm` | 1261568 | `20235b12aac0b3048ae8e421d4c79f2739164e62091f883146c120f28ac4c733` |
| `Dangel [FD]/Dangel (Disk 08).hdm` | 1261568 | `b5d2b2c33feb293247552c5a52b17ba0540e7733682734314206d88aec9298af` |
| `Dangel [FD]/Dangel (Disk 09).hdm` | 1261568 | `7f67ea5cf06869ca18c63d5fa11644103631148a4e01db8cbb9d253bce558dca` |
| `Dangel [FD]/Dangel (Disk 10).hdm` | 1261568 | `498f41df6f5d1d3a8a39ccb8e6c715457bdecfe49728243cfd0dbd39c092e060` |
| `Dangel [FD]/alts/Dangel (Disk 01) [Alt 1].hdm` | 1261568 | `abca8984c7c4586fc0c4c5ba91f42ae4d9116aa5e69ec54a0f881ba3684a3ba8` |
| `Dangel [FD]/alts/Dangel (Disk 05) [Alt 1].hdm` | 1261568 | `6041a3213a6b9aa9d9ec177f83d4c11928696096fea6a7909791f64eeefb3d06` |
| `Dangel [FD]/alts/Dangel (Disk 07) [Alt 1].hdm` | 1261568 | `9896f72c81cae1c158d67f08a19e7df9dc1bc539c153d6e96e65048a04c47799` |
| `Dangel [FD]/alts/Dangel (Disk 08) [Alt 1].hdm` | 1261568 | `5b3c57137cb0f173b0a2e2fcfdeb25271b2295e68e84e999f27b96be5371850f` |
| `Dangel [FD]/alts/Dangel (Disk 10) [Alt 1].hdm` | 1261568 | `93182518c483aa8384eb36aa05150abdd234b7b7d9bf7411392ec2d03a2f4139` |

The CD image went too: it carries the same archives. There was no local zip:
`Mink.zip` had already been unpacked and deleted; the original on the NAS
wasn't touched. Test builds in the session's scratch folder were deleted. The
script had been extracted to `games/dangel/strings.json` before the finding;
that file was deleted and never committed. The format work (`pc98tl/dangel.py`,
`dangel_tl.py`) was kept out of the repo.

### Review (2026-10-14): is the scene reachable in play?

The maintainer played the CD version from a new start. The first scene after
the prologue showed an adult protagonist. A recheck of the script placed that
scene and the flagged scene apart:

* **The scene the maintainer reached is `B.ARC` member 3.** It is the wake-up
  ten years later: Anduke sees his adult body reflected in Alicia's eye
  (strings 63 and 76). This member has no age mention, and the maintainer's
  screenshots match it.
* **The flagged scene is `B.ARC` member 1.** Its speakers are only 女, ？？ and
  男の子. It contains the stated age (string 51) and the "child" exchange
  (string 84). It ends with a flash of light and a scream (strings 105–106),
  which is the event before the ten-year sleep. The findings above stand.
* **It did not appear in the maintainer's playthrough.** The member has about
  65 voiced lines, each waiting for a key, and none showed. All that appeared
  between the prologue and the wake-up was a one-frame flash. The member may
  play only under a condition (for example, a start-up menu choice or a flag),
  or the game may never call it.

**Status: still excluded.** The open question is whether member 1 is reachable
in real gameplay. Two checks would answer it:

1. Run the game under the execution watch on the archive loader and log which
   members load from start-up through the wake-up. This needs no screenshots.
2. Search the other scripts for calls into member 1.

If the member is unreachable, the maintainer decides whether the game comes
off this list. One option is leaving member 1 out of extraction. The images
were restored to `E:\PC98\Dangel\` for this review (the CD version's `.hdi`
and `.zip`).
