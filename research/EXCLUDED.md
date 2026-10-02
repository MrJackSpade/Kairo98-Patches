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
