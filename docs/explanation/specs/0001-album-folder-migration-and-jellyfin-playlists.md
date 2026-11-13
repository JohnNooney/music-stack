# Spec 0001: Album-folder migration and Jellyfin-owned playlists

**Status:** ready-for-agent
**Labels:** `ready-for-agent`
**Glossary:** use the terms defined in `CONTEXT.md` at the repo root (album folder, pseudo-album, song, canonical copy, duplicate copy, playlist, playlist file, playlist import, playlist export, legacy playlist folder, playlist artifacts, migration, Deemix path, trash, inventory).
**Background research:** `docs/explanation/research/jellyfin-music-metadata-research.md` (why Jellyfin turns each legacy playlist folder into a pseudo-album).

## Problem Statement

Browsing my music in Jellyfin by artist or album is broken. Every legacy playlist folder (`Playlists/<Name>/`, 37 of them, ~2,400 files) shows up in Jellyfin as one pseudo-album named after a random track's album, and that pseudo-album is linked to every artist who appears in it. So when I open an artist page I get a "album" containing dozens of other artists' songs, and there's a bogus artist called "Playlists". Jellyfin groups albums strictly by folder (one folder = one album), so the tags on the files being correct doesn't help.

On top of that:
- The same song is often stored several times: in more than one legacy playlist folder (258 songs, ~9 GB of extra copies) and/or also in a real album folder (326 songs, ~12.4 GB).
- My playlists exist only as `.m3u` files that Jellyfin imported with no owner, so I can play them but cannot edit them in the Jellyfin UI (every edit returns 403).
- Deemix keeps downloading new playlists into new legacy playlist folders, so the problem recreates itself.
- Deemix runs from an ad-hoc `docker run`, its config (including credentials) lives inside the music library, and nothing documents how the stack fits together.
- There is no backup of the library.

## Solution

Every song lives in exactly one album folder, laid out exactly as Deemix itself would lay it out, so Jellyfin shows real albums and artist pages only list that artist's songs. Playlists stop being folders: they become Jellyfin playlists owned by me, which I edit in the Jellyfin UI, backed up as exported playlist files in a text-only git repo inside the library.

A one-off **migration** moves every song out of the legacy playlist folders into album folders, keeps a single canonical copy of each song (duplicate copies go to the trash, never deleted), recreates the 37 playlists in Jellyfin with their order and covers, and removes the legacy playlist folders. It is previewable (dry run), fully logged, and reversible (rollback).

Going forward, Deemix is configured to download playlist tracks straight into album folders and write a playlist file at the library root. After a Deemix session I run one **import** command that scans Jellyfin, merges new Deezer songs into the matching Jellyfin playlist without undoing my edits, tidies the library root, exports the playlists and commits them.

Deemix joins Jellyfin in this repo's compose file with pinned images and its config moved out of the library, and the repo documents the whole stack.

## User Stories

### Browsing
1. As a listener, I want each artist page to list only albums and songs by that artist, so that browsing by artist is trustworthy.
2. As a listener, I want each album in Jellyfin to contain only songs from that album, so that opening an album never shows unrelated tracks.
3. As a listener, I want songs that came from playlists to appear under their real album (even if I only own one track of it), so that I can find any song by artist → album.
4. As a listener, I want the bogus "Playlists" artist and all 37 pseudo-albums to disappear, so that the library looks like a normal music library.
5. As a listener, I want a song whose track artist differs from its album artist (e.g. a compilation track) to still appear on its track artist's page, so that I can find it either way.
6. As a listener, I want compilation tracks filed under a `Various Artists - <Album>` album folder when that is what the album artist tag says, so that compilations stay together as one album.
7. As a listener, I want every new album folder to show cover art, so that migrated albums look like the ones Deemix downloaded.
8. As a listener, I want synced lyrics to keep working for migrated songs, so that nothing I had is lost.

### Duplicates
9. As a library owner, I want each song stored exactly once, so that I don't waste ~20 GB and don't see the same song twice in an album.
10. As a library owner, I want songs identified by ISRC (falling back to artist + title), so that renamed copies of the same recording are recognised and different recordings (e.g. an original vs a remaster) are kept apart.
11. As a library owner, I want the copy already in an album folder to win over a playlist copy, so that existing albums are untouched.
12. As a library owner, I want FLAC to beat MP3 and then the larger file to win when choosing among playlist copies, so that I keep the best quality.
13. As a library owner, I want duplicate copies moved to a trash outside the library rather than deleted, so that I can recover anything until I empty it by hand.
14. As a library owner, I want every trashed file to be reported alongside the canonical copy that replaced it, so that I can verify nothing unique was thrown away.

### Paths and naming
15. As a library owner, I want migrated songs placed at their exact Deemix path (album folder name, `CD<n>` subfolder only for multi-disc albums, zero-padded track number width, illegal-character replacement), so that future Deemix downloads recognise them as already present instead of re-downloading them.
16. As a library owner, I want the album artist, album title, track count and disc count looked up from Deezer by ISRC, so that the path matches what Deemix would generate even when tags are missing that information.
17. As a library owner, I want tags used as a fallback when a Deezer lookup fails, and every such case listed in the report, so that the migration never blocks on the network but I can see where parity is uncertain.
18. As a library owner, I want Deezer lookups cached, so that re-running the dry run is fast and doesn't hammer the API.
19. As a library owner, I want songs whose target album folder already exists to be merged into it, so that partial albums I already own grow instead of being duplicated.
20. As a library owner, I want the migration to never overwrite an existing file; if a different recording already occupies the target path, I want the song left in place, its playlist reference kept valid, and the clash listed as a conflict, so that no data is lost silently.
21. As a library owner, I want the dry-run report to list every song whose Deezer metadata disagrees with its tags on album or album artist, so that I can spot mis-tagged files.
22. As a library owner, I want the dry-run report to list every song whose album artist differs from its track artist, so that I can spot genuinely wrong album-artist tags.

### Safety and reversibility
23. As a library owner, I want a dry-run mode that reports every planned move, trash, merge, conflict and playlist change without touching anything, so that I can review the plan first.
24. As a library owner, I want every live run to write a manifest of every change it made, so that the run can be undone exactly.
25. As a library owner, I want a rollback command that restores moved files, restores playlist files, deletes Jellyfin playlists the run created and removes songs an import added to existing playlists, so that I can return to the previous state.
26. As a library owner, I want the runbook to start with an APFS clone of the library outside the library root, so that I have a near-zero-cost full backup before anything moves.
27. As a library owner, I want the tool to verify after a live run that song counts reconcile (unique songs before = unique songs after) and that every trashed file has an identical-song canonical copy, so that the run is self-checking.
28. As a library owner, I want the tool to refuse to run a live migration while Jellyfin is reachable and scanning, or at least warn me to stop it, so that real-time monitoring doesn't react to thousands of moves mid-run.

### Playlists in Jellyfin
29. As a listener, I want my 37 playlists recreated as Jellyfin playlists owned by me, in their current order, so that I can play and edit them in the Jellyfin UI.
30. As a listener, I want each recreated playlist to keep its current cover image, so that playlists look the same as before.
31. As a listener, I want the old file-based playlists (including the ~37 duplicate "Untitled" ones) gone from Jellyfin, so that I only see one, editable copy of each playlist.
32. As a listener, I want to add, remove and reorder songs in my playlists from the Jellyfin UI, so that I can curate them where I listen.
33. As a library owner, I want each Jellyfin playlist linked to its Deezer playlist by Jellyfin playlist ID (not name), so that renaming a playlist in Jellyfin doesn't create a duplicate on the next import.

### Ongoing imports
34. As a library owner, I want Deemix to download playlist tracks straight into album folders at their Deemix path, so that legacy playlist folders are never recreated.
35. As a library owner, I want Deemix to write a playlist file at the library root for each playlist download, so that the import step knows what the playlist contains.
36. As a library owner, I want one import command to run after a Deemix session, so that bringing new downloads into Jellyfin is a single step.
37. As a library owner, I want the import command to trigger a Jellyfin library scan and wait for it to finish before touching playlists, so that newly downloaded songs exist in Jellyfin when they are added.
38. As a listener, I want songs that are new on Deezer since the last import appended to the end of my Jellyfin playlist, so that I pick up additions without losing my curation.
39. As a listener, I want songs I removed by hand to stay removed even though Deezer still lists them, so that re-downloading a playlist never undoes my edits.
40. As a listener, I want my manual ordering left untouched by imports, so that my curation is respected.
41. As a listener, I want songs Deezer dropped from a playlist reported but not removed from my Jellyfin playlist, so that I decide what to remove.
42. As a library owner, I want a brand-new Deezer playlist (no mapping yet) to be created as a new Jellyfin playlist owned by me, so that new playlists work without extra steps.
43. As a library owner, I want the import to strip blank entries Deemix writes for failed tracks, so that playlists don't contain dead references.
44. As a library owner, I want the `errors.txt` and `cover.jpg` that Deemix leaves at the library root after a playlist download moved into that playlist's artifacts folder, and the cover uploaded as the Jellyfin playlist image, so that the root stays clean and the playlist has art.
45. As a library owner, I want the imported playlist file moved out of the scanned library (kept as the reference for the next three-way comparison), so that Jellyfin never shows an uneditable duplicate playlist.

### History and backup
46. As a library owner, I want every Jellyfin playlist exported as a playlist file (paths relative to the library root) on each migration and import run, so that my playlists are backed up outside Jellyfin's database.
47. As a library owner, I want an inventory of every audio file (path, ISRC, size, artist, album, title) regenerated on each run, so that layout changes are reviewable as a text diff.
48. As a library owner, I want the exports, import references, mapping, inventory and failed-download logs tracked in a git repo inside the library that ignores all audio and images, so that I get history without duplicating 148 GB of audio.
49. As a library owner, I want each run to commit automatically with a summary message (e.g. "import: Bussin +3 songs; 2 dropped on Deezer"), and never push, so that history actually accumulates.
50. As a library owner, I want all of this hidden library data in dot-folders/dot-files, so that Jellyfin never scans it.
51. As a library owner, I want failed-download logs kept per playlist and version-controlled, so that I can retry those songs later.

### Stack and configuration
52. As the operator, I want Deemix defined as a service in this repo's compose file next to Jellyfin, so that the whole stack lives in one place.
53. As the operator, I want both images pinned (Jellyfin 12.4, Deemix v4.8.0), so that an image pull can't silently change folder grouping or path generation that the migration depends on.
54. As the operator, I want Deemix's config moved out of the music library into this repo (git-ignored), so that credentials and queue/log clutter are never in the scanned library.
55. As the operator, I want the Deemix settings that make playlists download into album folders applied and documented, so that I know why they are set.
56. As the operator, I want a committed `.env.example` and a git-ignored `.env` holding the Jellyfin URL and API key, so that I can set the key whenever I'm ready without committing it.
57. As the operator, I want commands that need Jellyfin to fail with a clear message pointing at `.env` when the key is missing, while dry runs and file moves still work without it, so that I can start before creating the key.
58. As the operator, I want the old stopped `Deemix` container removed (after explicit confirmation), so that only the compose-managed service remains.
59. As the operator, I want the root README to explain the stack (services, ports, volumes, library layout rules, download → import workflow, key settings and why, how to upgrade pinned images), so that future me can operate it.
60. As the operator, I want a migration runbook with the exact step order and the "done" checklist, so that the one-off migration is repeatable and verifiable.
61. As the operator, I want ADRs recording the hard-to-reverse decisions, so that nobody "fixes" them later without knowing why.
62. As the operator, I want `dedup_music.py` retired (removed from the repo, its library copy, log and old run records moved to the trash, its docs kept and marked retired), so that two tools never write playlists in conflicting ways.

## Implementation Decisions

### Modules
A single new Python command-line tool (working name `reorganize_playlists`), standard library only, living in this repo and operating on a library root passed by flag (default: the Deemix library). Internally it should be organised as a few deep modules behind small interfaces:

- **Tag reader** — given an audio file path, returns the song's tags (title, artist(s), album, album artist(s), track number, disc number, ISRC, date) and whether it has embedded art; can extract embedded art bytes. Supports FLAC (Vorbis comments, PICTURE block) and MP3 (ID3v2 text frames, APIC). Multi-value tags are preserved as lists. No tag writing.
- **Library scanner** — walks the library root (skipping dot-entries and the Deemix config if still present), produces songs grouped by location kind: album folder track, legacy playlist folder track, loose root track.
- **Song identity & duplicate resolver** — groups files into songs (ISRC first, normalised artist + title fallback, NFC-normalised); picks the canonical copy (album-folder copy wins; else FLAC > MP3; else larger file).
- **Deemix path generator** — given a song's Deezer-derived (or tag-fallback) metadata and the Deemix settings, returns the exact relative path Deemix would write. Must replicate Deemix's behaviour: album folder template `%artist% - %album%` using the album's main artist; `fixName` replacement of `\0 / \ : * ? " < > |` with the configured replacer and NFC normalisation; track number zero-padded to the digit length of the album track total (minimum 2 when padding single digits); `CD<discnumber>` subfolder only when disc total > 1; the album-track filename template `%tracknumber% - %title%`. Reads padding/replacer/template values from the Deemix config so it stays in step with it.
- **Deezer client (port)** — `lookup_track_by_isrc(isrc)` and `get_album(album_id)` returning the fields the path generator needs (album main artist name, album title, track total, disc total). Real implementation uses Deezer's public unauthenticated API, respects ~50 requests / 5 s, and caches responses to a JSON file. Failures return "unknown" so callers fall back to tags.
- **Migration planner** — pure function from (scanned library, Deezer metadata, existing filesystem state) to a plan: moves, merges into existing album folders, trashes, conflicts, cover extractions, sidecar moves, playlist file rewrites, artifact moves, and report sections. Dry run prints the plan; live run executes it.
- **Executor + manifest** — applies a plan, recording every action (file move, file create, playlist file write, Jellyfin playlist create/add) to a JSON manifest; rollback replays it in reverse. Never overwrites; trash lives outside the library root under a per-run folder.
- **Playlist file codec** — reads playlist files written by Deemix, Jellyfin, `dedup_music.py` or legacy in-folder files (encoding fallback UTF-8 → Latin-1, CRLF tolerant, blank-line tolerant), writes extended M3U8 in UTF-8 with paths relative to the library root.
- **Jellyfin client (port)** — `start_library_scan()`, `wait_for_scan()`, `find_items_by_paths(paths) -> ids`, `create_playlist(name, item_ids, user_id) -> playlist_id`, `get_playlist_items(playlist_id)`, `append_to_playlist(playlist_id, item_ids)`, `remove_from_playlist(playlist_id, entry_ids)` (rollback only), `delete_playlist(playlist_id)` (rollback only), `upload_playlist_image(playlist_id, image_bytes)`, `get_user_id(username)`. Real implementation uses `urllib` with the API key from `.env`.
- **Playlist importer** — three-way merge per playlist: inputs are the previous import reference (last Deezer list), the new Deemix playlist file, and the current Jellyfin playlist; output is songs to append (in Deezer order, appended at the end) and songs dropped on Deezer (report only). Never removes or reorders.
- **History writer** — writes playlist exports, the inventory, the mapping file, and commits to the library's text-only git repo with a summary message. Never pushes.

### Commands
- `migrate [--dry-run]` — one-off migration (below).
- `import [--dry-run]` — ongoing playlist import (below).
- `export` — export Jellyfin playlists + inventory and commit (also run at the end of `migrate`/`import`).
- `rollback <manifest>` — undo a live run, including Jellyfin-side changes.
- Global: `--root <library root>`, `--env <path to .env>`.

### Migration behaviour
- Order the runbook enforces: APFS clone → stop Jellyfin → `migrate --dry-run` → review → `migrate` (file phase) → start Jellyfin → scan + "Replace all metadata" refresh → `migrate` playlist phase (create Jellyfin playlists once songs are scanned) → verify checklist. The tool may split file and playlist phases into separate invocations or detect Jellyfin readiness; either way the playlist phase must not run before songs are scanned.
- Source of truth for the 37 playlists' contents and order: the root-level playlist files (UTF-8, accurate). Legacy in-folder playlist files (`Untitled.m3u` etc., stale and mis-encoded) are trashed, not used.
- After the playlist phase, root playlist files are rewritten to the new album-folder paths and moved into the hidden imports folder, where they become the first import reference for each playlist; the Deezer-title → Jellyfin-playlist-ID mapping is written.
- Each legacy playlist folder's `cover.jpg` is uploaded as the playlist image and archived, with its `errors.txt`, into that playlist's artifacts folder. The empty `Satyricon - Volcano` folder's `errors.txt` is archived the same way and the folder removed. The stray `dedup_music.log` inside a playlist folder is trashed. Empty legacy playlist folders and then the `Playlists` folder are removed.
- The loose root single (`A$AP Ferg - Work.flac` + `.lrc`) is migrated like any other song.
- New album folders get a `cover.jpg` extracted from the canonical copy's embedded art (no network).
- `.lrc` sidecars follow their audio file; a sidecar of a trashed duplicate copy is kept only if the canonical copy has none.
- Album folder decision follows the album-artist tag / Deezer album main artist as-is (`Various Artists` compilations included); missing album artist falls back to Deezer's album main artist, then the track artist.

### Hidden library data (all dot-prefixed so Jellyfin's `**/.*` ignore rule skips them)
- `.playlists/imports/<Deezer title>.m3u8` — last imported Deezer list per playlist (three-way reference).
- `.playlists/jellyfin/<Jellyfin name>.m3u8` — playlist exports.
- `.playlists/map.json` — `{ "<Deezer playlist title>": "<Jellyfin playlist id>" }`.
- `.artifacts/<playlist>/` — `errors.txt`, cover image.
- `.inventory.tsv` — path, ISRC, size, artist, album, title per audio file.
- `.git` + `.gitignore` — tracks only the above text files (ignores audio, images, everything else).
- Deezer lookup cache and run manifests/logs: stored where they don't pollute the library git history (manifests next to the trash or in a git-ignored dot-folder).

### Deemix configuration (applied to Deemix's config while the container is stopped)
- `createStructurePlaylist: true`, `createPlaylistFolder: false` (both required; with the playlist folder on, tracks land in `Playlists/<Name>/Artist - Album/`).
- `playlistTracknameTemplate: "%tracknumber% - %title%"` (Deemix always uses the playlist template for playlist tracks, even in structure mode).
- `createM3U8File: true`, `playlistFilenameTemplate: "%title%"` → `<Title>.m3u8` at the library root with entries relative to the root (Deemix sets the extras path before appending album folders when the playlist folder is off).
- Everything else unchanged (`overwriteFile: 'l'`, `albumNameTemplate: "%artist% - %album%"`, `illegalCharacterReplacer: "_"`, padding settings).
- Known Deemix side effects the importer handles: `errors.txt` and playlist `cover.jpg` written at the library root and overwritten per download; blank lines for failed tracks.

### Stack
- Compose gains a `deemix` service: image `ghcr.io/bambanah/deemix:v4.8.0`, container name `deemix`, `PUID`/`PGID` 501, port 6595, library bind-mounted at `/downloads`, config bind-mounted from a git-ignored folder in this repo at `/config`, restart `unless-stopped`. Other env vars from the old `docker run` are image defaults and omitted.
- Jellyfin image pinned to `jellyfin/jellyfin:12.4`.
- Deemix config (`config.json`, `queue/`, `logs/`, `spotify/`) moved from the library into the repo's git-ignored Deemix config folder.
- `.env.example` (committed) with `JELLYFIN_URL=http://localhost:8096` and empty `JELLYFIN_API_KEY=`; `.env` git-ignored. The tool parses `.env` itself (no dependency).
- `.gitignore` additionally covers `.env`, the Deemix config folder and `__pycache__/`.
- Removing the old `Deemix` container requires explicit user confirmation at execution time.

### Jellyfin settings
- MusicBrainz stays enabled for albums/artists; after the file phase a full refresh with "Replace all metadata" is required (ordinary rescans don't overwrite stale album/artist values).
- Custom tag delimiters stay off (out of scope).

### Documentation
- `README.md` becomes the stack overview.
- `CONTEXT.md` glossary already exists; update it if new terms crystallise.
- `docs/explanation/adr/` with three ADRs: (1) songs live only in album folders and Jellyfin owns playlists (chosen over `.ignore`-ing the playlist folder, which would hide the songs, and over file-owned playlists, which Jellyfin won't let the user edit); (2) Deemix structure-playlist mode with migrated songs at their exact Deemix path via Deezer lookup; (3) no git for audio — APFS clone backup + text-only git.
- `docs/reference/reorganize_playlists.md` (usage), `docs/how-to/migrate-library.md` (step order + done checklist), `docs/explanation/dedup_music.md` (current README content, marked retired), research doc gets a pointer to the ADRs.
- `dedup_music.py` removed from the repo.

## Testing Decisions

### What makes a good test
Tests exercise the tool only through its public command entry point and observe external effects: the resulting files and folders in a temporary library, the report/manifest it writes, and the calls recorded by fake Deezer/Jellyfin clients. No tests of private helpers, internal data structures or call order inside the tool. A test should still pass after any internal refactor that preserves behaviour.

### Seams
One seam, at the top: the command entry point, invoked in-process as `main(argv, deezer=<client>, jellyfin=<client>)`, against a **real temporary filesystem**. The only substituted dependencies are the two network ports (Deezer client, Jellyfin client), each with an in-memory fake that records calls and holds state (Jellyfin fake keeps playlists and item IDs keyed by path; Deezer fake returns canned track/album metadata or "unknown"). Git commits run for real in the temp library. The real HTTP clients are thin and covered by a manual smoke check rather than unit tests.

*(These seams were proposed without a final confirmation from the user; confirm before starting if anything looks off.)*

### Fixtures
A fixture builder generates a tiny library on disk: minimal valid FLAC files (STREAMINFO + VORBIS_COMMENT + optional PICTURE) and MP3 files (ID3v2.3/2.4 frames + optional APIC), album folders, legacy playlist folders, root playlist files (UTF-8), stale Latin-1/CRLF in-folder playlist files, `cover.jpg`, `errors.txt`, `.lrc` sidecars, and a Deemix config with the real padding/replacer settings.

### Behaviours to cover (test-first)
- Songs from legacy playlist folders end up at the exact Deemix path; multi-disc → `CD<n>`; >99-track album → 3-digit padding; illegal characters replaced; NFC/NFD names handled.
- Deezer unknown → tag fallback, listed in the report.
- Canonical copy selection: album copy beats playlist copy; FLAC beats MP3; larger wins; differing ISRCs kept apart; artist+title fallback without ISRC.
- Duplicate copies moved to trash with relative structure; sidecar rules.
- Merge into existing album folder; conflict when a different recording occupies the target path (no overwrite, reported, playlist reference still valid).
- Cover extraction for new album folders only.
- Legacy folders, stale in-folder playlist files, stray log, empty album folder handled; `Playlists` removed.
- Dry run changes nothing on disk and makes no Jellyfin mutations.
- Playlist phase creates Jellyfin playlists owned by the configured user, in order, with cover upload; mapping and import references written; root playlist files leave the scanned library.
- Import three-way merge: new Deezer songs appended at end; hand-removed songs not re-added; order untouched; Deezer-dropped songs reported only; new playlist created when unmapped; renamed Jellyfin playlist still matched by ID; blank entries ignored; root `errors.txt`/`cover.jpg` archived and uploaded.
- Import waits for scan completion before playlist changes.
- Missing API key: Jellyfin-dependent commands fail with a clear message; dry run and file phase succeed.
- Rollback restores files, playlist files, deletes created playlists and removes appended entries.
- Post-run self-check: unique-song counts reconcile; every trashed file has a canonical copy.
- Exports, inventory and automatic commit with summary message; nothing outside the allow-listed text files is tracked.

### Prior art
None in the repo (no existing tests). `dedup_music.py` is the prior art for conventions: `--dry-run`, JSON manifest of every change, `--rollback`, NFC normalisation, UTF-8/Latin-1 playlist reading. Use the standard library `unittest`.

### Acceptance (manual, on the real library)
- Dry-run report reviewed by the user before any live run.
- After the live run and Jellyfin refresh: every playlist entry resolves; no audio outside album folders; no "Playlists" artist or pseudo-albums; 37 playlists editable with original track counts; spot checks — Cymande's artist page shows only "Dove" under its real album; `The Roots - Things Fall Apart` gains no extra tracks.
- Deemix check: re-download one small already-owned playlist → nothing new downloaded, one root `.m3u8` written, `import` adds nothing.

## Out of Scope
- Splitting combined artist tags (`Mack 10/Ice Cube`, `feat.` credits) via Jellyfin custom delimiters.
- Retagging files (including filling missing album-artist tags or correcting suspicious ones) — only reported.
- Downloading higher-resolution cover art.
- Automatic import triggers (Deemix `executeCommand`, launchd, file watchers).
- Two-way sync between playlist files and Jellyfin.
- Git or git-annex for audio files; any remote for the library git repo.
- Changing Jellyfin's MusicBrainz/TheAudioDB fetcher configuration.

## Further Notes
- Measured state at spec time: 213 album folders (all tags consistent with folder names), 2,396 legacy playlist files = 2,102 unique songs; 326 songs already in album folders; 258 songs in ≥2 playlist folders; ~1,504 resulting album groups (1,189 single-track; 119 merge into existing album folders); 131 files missing album artist, 67 "Various Artists". Every playlist file has ISRC, track number, disc number, album and embedded art, but no track/disc totals — hence the Deezer lookup.
- Jellyfin facts relied on (v12.4): album = folder; file-imported playlists have no owner and reject edits with 403; dot-entries are ignored by the scanner; ordinary rescans don't overwrite album/artist values.
- Deemix facts relied on (bambanah fork, path code unchanged v4.5.2 → v4.8.0): structure-playlist path logic, playlist template always used for playlist tracks, extras path = download root when the playlist folder is off, skip-if-exists by exact path.
- No backup existed before this work and Time Machine is not configured; the APFS clone step is mandatory, not optional.
- The volume is APFS with ~629 GiB free; the legacy playlist folders total ~67 GB.
- Deliver as a few logical local commits in this repo (stack/config, tool + tests, docs); never push; show the commit list to the user before committing.
