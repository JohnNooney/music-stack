> **Retired.** `dedup_music.py` was replaced by `reorganize_playlists` (see [reorganize_playlists.md](reorganize_playlists.md) and [ADR 0001](adr/0001-songs-in-album-folders-jellyfin-owns-playlists.md)). Songs no longer live in `Playlists/<Name>/` folders and playlists are owned by Jellyfin, so this script would now write playlists in a conflicting way. It was removed from the repo; its library copy, log and run manifests were moved to `/Users/john/Music/Deemix-trash/retire-dedup_music/`. This page is kept for history only.

# dedup_music.py

Remove duplicate audio files (FLAC > MP3) from a Deemix music library and keep M3U playlists in sync.

## What the script does

- Walks the music tree, excluding `Config/` and `_duplicates_trash/`, and groups `.flac` and `.mp3` duplicates within each folder using fuzzy filename matching.
- Keeps the best copy: FLAC wins over MP3; if the same format, the larger file wins.
- Moves loser audio files to `_duplicates_trash/`, preserving their path relative to the music root.
- Handles `.lrc` sidecars: a loser's sidecar is moved to trash if the winner already has one; otherwise it is renamed to use the winner's filename.
- Removes entries for moved files from `.m3u` and `.m3u8` files in the affected folder and at the music root.
- Creates a root-level `<playlist>.m3u` for every immediate audio-containing subfolder of `Playlists/`:
  e.g. `Playlists/Что cлучилось/<songs>` becomes `Что cлучилось.m3u` at the music root.
- Refreshes generated root-level playlists when their entries no longer match their source folder.
- Writes a JSON manifest for every live run that changes files or playlists, so the run can be rolled back.
- Writes a `dedup_music.log` file at the music root.

## Usage

The default music root is `/Users/john/Music/Deemix`.

### Options

- `--root PATH`: Set the music-library root.
- `--dry-run`: Report every planned move and playlist edit without changing files.
- `--threshold VALUE`: Set the cross-format filename similarity threshold from `0.0` to `1.0`; the default is `0.90`.
- `--refresh-playlists`: Force regeneration of managed root-level playlists, even when their entries appear synchronized.
- `--rollback MANIFEST`: Undo the moves and playlist edits recorded by a previous live-run manifest. This mode does not perform deduplication.

### Common commands

Preview a normal deduplication run:

```bash
python3 dedup_music.py --dry-run --root /Users/john/Music/Deemix
```

Apply deduplication and normal playlist synchronization:

```bash
python3 dedup_music.py --root /Users/john/Music/Deemix
```

Use a lower cross-format matching threshold:

```bash
python3 dedup_music.py --root /Users/john/Music/Deemix --threshold 0.85
```

Preview a forced rebuild of generated playlists while also previewing deduplication:

```bash
python3 dedup_music.py --root /Users/john/Music/Deemix --refresh-playlists --dry-run
```

Apply deduplication and force-recreate every generated playlist:

```bash
python3 dedup_music.py --root /Users/john/Music/Deemix --refresh-playlists
```

Rollback a live run:

```bash
python3 dedup_music.py --rollback /Users/john/Music/Deemix/dedup_manifest_<timestamp>.json
```

## Matching and playlist behavior

- Cross-format pairs (`.flac` versus `.mp3`) use `--threshold`.
- Same-format pairs use a fixed `0.98` threshold to avoid merging tracks with similar names, such as `Song Pt. 1` and `Song Pt. 2`.
- Filename comparisons are case-insensitive after punctuation and repeated whitespace are removed.
- Generated playlists contain `#EXTM3U` followed by relative POSIX paths in the form `Playlists/<folder>/<filename>`.
- A normal run preserves an existing generated playlist when its set of audio filenames matches the source folder. `--refresh-playlists` overwrites it regardless, so manually edited generated playlists are replaced.
- `--refresh-playlists` is not a refresh-only mode: it still performs the normal duplicate scan and moves unless used with `--dry-run`.

## Problem fixed

Deemix downloaded non-Latin filenames (Cyrillic, Arabic, etc.) correctly on disk, but the generated M3U files either:

- contained `?` placeholders for non-Latin characters, or
- were encoded in Latin-1 while the script only read UTF-8.

This caused `dedup_music.py` to miss playlist entries and fail to create/refresh playlists for folders like `Playlists/Что cлучилось/`.

### Fix

- All filename comparisons are now Unicode NFC-normalized so decomposed (NFD) filesystem names match precomposed (NFC) playlist entries and vice versa.
- M3U files are read with an encoding fallback (UTF-8 first, then latin-1) and rewritten as clean UTF-8.
- After deduplication, the script ensures a root-level `<playlist>.m3u` exists for each immediate subfolder of `Playlists/`, containing relative POSIX paths to the current audio files. Existing playlists are rewritten when the set of entries does not match, or whenever `--refresh-playlists` is supplied.

## Safety

- Live runs write `dedup_manifest_<timestamp>.json` in the root only when they make changes.
- Use `--dry-run` first, especially before changing `--threshold` or using `--refresh-playlists`.
- `--refresh-playlists` overwrites generated root-level playlist content; use it only when that is intended.
- Use `--rollback <manifest>` to restore moved files and playlist content. A successful rollback deletes its manifest.
- `_duplicates_trash/` is not deleted automatically; inspect it before deleting it manually.
