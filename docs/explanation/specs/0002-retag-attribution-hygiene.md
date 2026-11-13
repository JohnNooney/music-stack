# Spec 0002: `retag` — attribution hygiene for embedded tags

**Status:** ready-for-agent
**Labels:** `ready-for-agent`
**Glossary:** use the terms defined in `CONTEXT.md` at the repo root (album folder, pseudo-album, song, canonical copy, duplicate copy, playlist, playlist file, playlist artifacts, migration, Deemix path, trash, inventory).
**Prior spec:** `docs/explanation/specs/0001-album-folder-migration-and-jellyfin-playlists.md` (the migration this follows up).

## Problem Statement

After the migration, browsing by artist/album in Jellyfin is still polluted — not by folders anymore, but by embedded tags. An audit of all ~4,700 files against their album folders found three classes of defect:

- **Files whose `ALBUM` tag names a different album than their album folder** (82 files). Each spawns a real one-or-few-song album entity in Jellyfin named after the tag and attributed to the song's artists — e.g. `Me and Bobby McGee` inside `Janis Joplin - Pearl (Legacy Edition)` is tagged `album='Collections'` with artist list `Janis Joplin, Pearl Pearl, Vince Mitchell, Phil Badella, John Cooke` (corrupt contributor data). Other examples: `What I Need` tagged `Pure House`, `Tender Surrender` tagged `Alien Love Secrets`, `Haitian Divorce` tagged `The Royal Scam`, `Zombie` tagged `No Need To Argue`.
- **`ALBUMARTIST` values that credit featured artists** (Deemix writes all Deezer contributors into the tag): `War Wounds`, `Shabba REMIX`, `Hella Hoes`, `Juice`, `I Wanna Get High with Da Blanksta`. The album page then shows guests as album artists. Compilations have the inverse problem — empty `ALBUMARTIST`, so Jellyfin falls back to each song's track artist (`Habibi Funk 015` shows five artists instead of `Verschiedene Interpreten`).
- **Bogus track-artist data**: contributor lists with junk names (`Pearl Pearl`, `Vince Mitchell`, `Phil Badella`, `John Cooke`, `Zashawn`), which create junk artist entities in Jellyfin.

A plain library rescan does not fix any of this — Jellyfin retains stale album→artist links even when tags change.

## Solution

A new `retag` command rewrites the three attribution fields (`ARTIST`, `ALBUM`, `ALBUMARTIST`) of every audio file in the library to match Deezer's metadata — the same source of truth the migration already used to compute each file's Deemix path, so tags and folders stop diverging. Everything else in the file (title, track/disc numbers, ISRC, barcode, date, embedded art, and the audio itself) is untouched.

The command is a normal tool run: `--dry-run` preview by default-first convention, a manifest + report per run, original file bytes backed up to the trash before any rewrite, inventory rewritten and committed to the library git repo afterwards. Files are only rewritten when their tags substantively differ from the canonical values — pure spelling variants (case, punctuation) are reported but not written.

The tool remains stdlib-only: `tags.py` grows a writer alongside the existing reader (FLAC Vorbis comments, MP3 ID3v2, art and unknown fields preserved).

## User Stories

1. As a listener, I want each album in Jellyfin to be attributed only to its real album artist, so that featured guests stop showing up as album owners.
2. As a listener, I want albums whose `ALBUM` tag names a different release than their album folder to be corrected, so that phantom one-song albums stop appearing.
3. As a listener, I want bogus contributor names (`Pearl Pearl`, `Phil Badella`, `Zashawn`, …) removed from song artist tags, so that junk artists stop appearing in the artist list.
4. As a listener, I want compilation album folders (`Verschiedene Interpreten - …`) attributed to that single album artist, so that a compilation displays as one album by one album artist rather than by every track artist.
5. As a listener, I want track artists left intact on songs (featuring credits stay on the song), so that I can still find a song by any of its performers — only the album-level attribution is collapsed.
6. As a listener, I want album names in tags to match the album folder, so that Jellyfin merges songs into the album its folder represents instead of spawning tag-named phantoms.
7. As the maintainer, I want `retag --dry-run` to show me every planned rewrite as a per-field diff (old value → new value) before anything changes, so that I can sanity-check the metadata source before trusting it.
8. As the maintainer, I want files rewritten only when the difference is substantive, so that a run doesn't churn thousands of files for punctuation.
9. As the maintainer, I want cosmetic-only differences (`Abbey Road (Remastered)` vs `Remastered 2009`-style variants, `Lil' Keke` vs `Lil' KeKe`) listed in the report but not written, so that I can review them without blessing a mass rewrite.
10. As the maintainer, I want files whose tags are *right* but sit in the wrong folder (Deezer agrees with the tag, not the folder) listed under a "misplaced" heading, so that I can decide on a move later without this command touching paths or playlist entries.
11. As the maintainer, I want files Deezer can't resolve (no ISRC/barcode, lookup failure) to fall back to their album folder name for `ALBUM`/`ALBUMARTIST` and keep their `ARTIST` untouched, so that an API outage degrades the run gracefully rather than corrupting tags.
12. As the maintainer, I want every rewritten file's original bytes preserved in the trash, so that `rollback` can restore a botched retag exactly.
13. As the maintainer, I want the run to re-read every file it rewrote and verify the new tags parse and match what was intended, so that a writer bug fails loudly instead of leaving corrupt files.
14. As the maintainer, I want the library inventory rewritten and committed after a live run, so that tag changes show up in the library's git history like layout changes do.
15. As the maintainer, I want the command to make no Jellyfin API calls, so that tag hygiene stays independent of whether the server is up — I rescan afterwards myself.
16. As the maintainer, I want the report to count and summarize each outcome class (retagged, cosmetic, misplaced, lookup-failed), so that one glance tells me library health.
17. As a future run of `import`, I want new downloads eventually retagged the same way, so that tag hygiene is repeatable rather than a one-off — the command must be safe to re-run (idempotent: clean files produce a no-op plan).
18. As the maintainer, I want MP3 files to keep their ID3 version and unaffected frames (art, ISRC, custom frames) through a rewrite, so that a retag can't strip metadata it doesn't understand.
19. As the maintainer, I want FLAC files to keep their picture block, vendor string, and unaffected comments through a rewrite, so that art and non-attribution tags survive.
20. As the maintainer, I want multi-artist songs written back as multi-value artist fields (repeated Vorbis comments / the file's own ID3 multi-value convention), so that featuring credits are preserved in the form the player expects.

## Implementation Decisions

- **New `retag` command** in the CLI, alongside `migrate`/`import`/`export`/`rollback`, with `--dry-run`. Same run conventions: `Context`, run dir under `.reorganize/runs/`, `Report`, `Executor`, manifest, `record_history` (inventory + commit) at the end.
- **Scope of the audit:** every audio file returned by `library.scan()` (all locations — the legacy `Playlists/` tree is gone, but the command must not assume it stays gone). Per-file, not per-song: duplicates get retagged like any other file.
- **Source of truth:** live Deezer, reusing the migration's lookup order — `BARCODE` → `album/upc:<barcode>`, else `ISRC` → `track/isrc:<isrc>` → album id → `album/<id>`. The Deezer client gains track contributors so `ARTIST` can be canonicalized too.
  - `DeezerTrack` extends to `{id, album_id, contributors: list[str]}` — `contributors` from the track payload's `contributors[].name` (main artist first), falling back to `artist.name`. Cached the same way; `FakeDeezer.add` gains a `contributors` parameter.
  - Canonical values per file: `ALBUM` ← `DeezerAlbum.title`; `ALBUMARTIST` ← `[DeezerAlbum.artist]` (always a single value — this is what collapses feat-artist creep and fills empty compilation album artists); `ARTIST` ← `DeezerTrack.contributors`.
  - Deezer names are written **verbatim** (including `Verschiedene Interpreten` for compilations — it matches the folder name and future Deemix downloads).
- **Fallback when Deezer can't resolve a file** (no ISRC and no barcode, or lookup miss): parse the album folder name `<Artist> - <Album>` for `ALBUM`/`ALBUMARTIST`; leave `ARTIST` as tagged. Reported under "Deezer lookup failed" so the run's weak spots are visible.
- **Substantive vs cosmetic:** a field difference is *substantive* when the normalized values differ (same normalization style as the existing `_same`/`_normalise_words`: NFC, case-folded, punctuation stripped, whitespace collapsed). If **any** of the three fields differs substantively, all three are rewritten to canonical (a partially-fixed file is worse than a fully-fixed one). If the only differences are cosmetic, nothing is written; the file is listed under "Cosmetic differences (not rewritten)".
- **Misplaced files:** when Deezer's album title matches the file's `ALBUM` tag but not the folder's album part, the file is misplaced, not mistagged. Reported under "Misplaced (tag agrees with Deezer)". `retag` never moves or deletes audio.
- **Tag writer (new, in `tags.py`):** `write_tags(path, *, artists, album, album_artists)` (exact signature the implementer chooses) that rewrites only those three fields.
  - FLAC: rebuild the metadata section replacing the `VORBIS_COMMENT` block's `ARTIST`/`ALBUM`/`ALBUMARTIST` entries (multi-value = repeated entries); preserve vendor string, all other comments, PICTURE and every other block; append the audio bytes unchanged.
  - MP3: rebuild the ID3v2 tag at the same version, replacing `TPE1`/`TALB`/`TPE2`; preserve every other frame including `APIC`; multi-value artists use the file's existing convention (the reader already decodes NUL-separated values; the writer must round-trip `read_tags`' view of the file).
  - Whole-file rewrite (read all bytes, write new file): metadata lives at the head of both formats and may change length.
- **Executor:** gains a backup-and-rewrite op — copy the original file bytes to `trash_path(src)`, then write the new bytes in place. Manifest records it so `rollback` can restore the original bytes. (Follows the existing Trash/rollback pattern; no audio file is ever left without a recoverable original.)
- **Self-check (live run):** re-read every rewritten file with `read_tags`; it must parse and the three fields must equal the intended values. Failures reported and counted; the run's exit code reflects failure like `migrate` does.
- **Report sections (order):** `Retagged` (per-file, per-field `old → new`), `Misplaced (tag agrees with Deezer)`, `Cosmetic differences (not rewritten)`, `Deezer lookup failed (folder fallback used / artist kept)`, `Failed actions`.
- **No Jellyfin calls.** The command neither scans nor mutates Jellyfin; the report tells the user to run a library scan afterwards.
- **Idempotent:** a clean library produces an empty plan — required for the command to be re-runnable after future Deemix downloads.

## Testing Decisions

- **Same single seam as the rest of the suite:** `main(argv, deezer=FakeDeezer, jellyfin=FakeJellyfin)` against a real temp library built with `tests/support.py`, observing files on disk, trash contents, report text, and fake-client state. No new seams. (This matches the seam documented in AGENTS.md — flagging it here for the maintainer's confirmation.)
- **Assertions observe outcomes, not internals:** rewritten files' tags are re-read with the real `tags.read_tags`; backups are asserted via `trashed()`/trash contents; plans are asserted via report text and `lib.files()` snapshots.
- **Prior art:** `tests/test_migrate_files.py` (Executor/report/manifest patterns, `lib.flac`/`lib.mp3` fixture builders, `run_tool`). The fixture FLAC/ID3 writers in `support.py` are already real minimal encodings, so the tag writer round-trips them in tests.
- **Coverage sketch:** ALBUM/ALBUMARTIST/ARTIST rewrites on FLAC and MP3 (v2.3 and v2.4); feat-artist `ALBUMARTIST` collapse; empty `ALBUMARTIST` filled on compilations; cosmetic-only diff → no write + report; substantive-any-field → all three written; Deezer-agrees-with-tag misplaced case → report, file unmoved; lookup failure → folder fallback, ARTIST kept, reported; barcode path preferred over ISRC; untouched fields/art preserved (bytes compared); original bytes in trash + rollback restores; dry-run changes nothing; idempotent second run; multi-artist round-trip.
- **`FakeDeezer` gains a `contributors` parameter** on `add`; `FakeJellyfin` needs nothing new (the command never calls it — a test asserts `jellyfin.mutations` stays empty).

## Out of Scope

- **Moving misplaced files** — report-only this pass; moving audio is the migrate command's job (it owns playlist-entry rewriting).
- **Cosmetic normalization** (case/punctuation/edition-spelling variants, artist-name aliases like `Ö`/`O`) — reported, not written. A future pass may normalize artist spelling globally once decided.
- **Stale Jellyfin artist links** (the ~103 album→artist links with no backing tag): they survive any tag fix because Jellyfin never recomputes them. Follow-up decision after `retag` + rescan: delete unbacked `MusicArtist` entities via the API vs living with aliases. Deliberately not in this spec.
- **Jellyfin metadata-provider configuration** (MusicBrainz album credits like `高中正義`, `The Doors`, `Antônio Carlos Jobim` come from provider IDs on album entities, not from our tags). Changing provider settings is a separate decision.
- **Any tag field besides `ARTIST`, `ALBUM`, `ALBUMARTIST`** — title, track/disc numbers, ISRC, barcode, date, genre, art are never touched.
- **New dependencies** — the writer is implemented in stdlib like the reader.

## Further Notes

- Expected scale from the audit: ~40 files with substantive `ALBUM`/artist mismatches, ~40 more cosmetic-only, plus the feat-artist `ALBUMARTIST` collapses. First live run is small; the value is repeatability.
- Accepted collateral: `PACIFIC` (a genuine Hosono/Suzuki/Yamashita co-leader album) collapses to `ALBUMARTIST = Haruomi Hosono`, matching the folder name. Co-artists remain visible per track via `ARTIST`.
- The bogus-artist files are where retag value is highest: `Janis Joplin - Pearl (Legacy Edition)/CD1/03 - Me and Bobby McGee.flac` (`album='Collections'`, four junk artists) is the canonical test case for the live run.
- Deezer itself occasionally serves garbage contributor data (`Zashawn`-style); the dry-run report is the checkpoint for catching it — canonical values are trusted only because the folder names (already Deezer-derived) overwhelmingly agree.
