# ADR 0003: No git for audio — APFS clone backup plus a text-only git repo

**Status:** accepted (2026-11-10) · **Spec:** [0001](../specs/0001-album-folder-migration-and-jellyfin-playlists.md)

## Context

The library is about 148 GB of FLAC/MP3, and before this work it had no backup at all (Time Machine is not configured). The migration moves thousands of files. The playlist definitions now live in Jellyfin's database. Putting audio in git (or git-annex/LFS) would double the disk usage, or add tooling, just to version files that never change.

## Decision

1. **Before the migration**, back up the whole library with an **APFS clone** (`cp -c -R`) to a folder outside the library root. Copy-on-write makes it nearly free, and it is a full, browsable restore point. This step is mandatory (runbook step 1).
2. The library holds a **text-only git repo** (`<library>/.git`). Its allow-list `.gitignore` (written by the tool) tracks only:
   - `.playlists/jellyfin/*.m3u8`: playlist exports
   - `.playlists/imports/*.m3u8`: the last imported Deezer list per playlist
   - `.playlists/map.json`: Deezer title → Jellyfin playlist ID
   - `.inventory.tsv`: path, ISRC, size, artist, album and title of every audio file
   - `.artifacts/*/errors.txt`: failed-download logs per playlist

   Everything else is ignored: audio, images, tool state.
3. Every live run regenerates the inventory and exports and **commits automatically** with a summary message. It **never pushes**, and the repo has no remote.
4. Everything is dot-prefixed so Jellyfin's `**/.*` ignore rule keeps it out of the scanned library.
5. Duplicate copies and stale files go to a **trash outside the library** (`<library>-trash/<run>/`) and are never deleted. Every live run writes a manifest so `rollback` can undo it exactly.

## Consequences

- Layout changes and playlist edits are reviewable as text diffs (`git -C ~/Music/Deemix log -p`).
- Audio has no history beyond the APFS clone and the trash. Empty the trash by hand only after verifying a run.
- Do not add a remote or start tracking audio. The allow-list is rewritten on every run.
