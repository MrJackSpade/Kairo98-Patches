# Index sources

`tools/build_index.py` joins these. Raw copies are in `research/`; re-fetch them
to refresh, then rebuild.

| Source | What it gives | Fetched | File |
|---|---|---|---|
| `E:\PC98` (NeoKobe PC-98 set) | every title, publisher and media type | `tools/inventory.py` | `inventory.json` (not committed) |
| [archive.org: NEC PC 9801 Translation archive](https://archive.org/details/nec-pc-9801-translations) | pre-patched English builds of (in its own words) all PC-98 fan translations, with translator and version in each filename; AI translations are tagged | `curl https://archive.org/metadata/nec-pc-9801-translations` (last updated 09/17/26) | `research/ia_translations.json` |
| Kairo98 catalog research | joins between translated titles and NeoKobe groups, plus English and Japanese aliases | copied from `Kairo98/catalog/research/matches-v1.json` | `research/kairo98_matches.json` |
| [VNDB](https://vndb.org) API | every English PC-98 release (fan patch or official) with the patch site link | `POST https://api.vndb.org/kana/release` with filter `platform = p98, lang = en` | `research/vndb_p98_en.json` |
| GitHub search | patch repos and translations in progress | `api.github.com/search/repositories` for "pc98 translation" and similar | `research/gh_repos.json` |
| Hand mapping | archive and VNDB entries whose names don't match automatically; curated GitHub links with status | written by hand | `research/ia_manual.json`, `research/vndb_manual.json`, `research/patches_manual.json` |

Not used: romhacking.net's listing sits behind a Cloudflare browser check that a
script can't pass.

## Known gaps

* `Active.zip` was still being copied when the index was built, so its titles
  are missing. Re-run `tools/inventory.py` and `tools/build_index.py` once the
  copy finishes.
* *Peret em Heru* and *Wind's Seed* (archive.org) and *EMIT Vol. 2* (VNDB) have
  translations but no matching title in the collection.
* Translations published only on a translator's blog or forum, and not yet in
  the archive.org set, VNDB or GitHub, won't show up.
