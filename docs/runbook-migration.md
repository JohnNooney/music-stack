# Runbook: one-off album-folder migration

Moves every song out of the legacy playlist folders into album folders and recreates the playlists as Jellyfin playlists owned by you. Background: [ADR 0001](adr/0001-songs-in-album-folders-jellyfin-owns-playlists.md), [ADR 0002](adr/0002-deemix-structure-playlist-mode-and-exact-deemix-paths.md), [ADR 0003](adr/0003-no-git-for-audio-apfs-clone-and-text-only-git.md). Tool usage: [reorganize_playlists.md](reorganize_playlists.md).

Run every command from `/Users/john/Docker/jellyfin`. Do the steps **in order**.

## Steps

1. **Back up with an APFS clone.** This is mandatory, because there is no other backup.
   ```bash
   docker compose stop deemix 2>/dev/null; docker compose stop jellyfin
   cp -c -R /Users/john/Music/Deemix /Users/john/Music/Deemix-backup-$(date +%Y%m%d)
   ```
   `-c` clones the files (copy-on-write), so this takes seconds and almost no space. The clone lives outside the library root.
2. **Keep Jellyfin stopped.** Real-time monitoring must not react to thousands of moves. The tool refuses to run while Jellyfin is scanning and warns while it is running. Without an API key it cannot check, so make sure yourself: `docker compose ps`.
3. **Dry run** (about 5–10 min the first time, while Deezer lookups are cached):
   ```bash
   python3 -m reorganize_playlists migrate --dry-run
   ```
4. **Review the report** (`~/Music/Deemix/.reorganize/runs/<id>/report.txt`). Look closely at:
   - *Deezer network errors*: must be absent. Otherwise fix the network or TLS problem and repeat step 3.
   - *Conflicts*: songs that stay in `Playlists/`, so that folder will remain.
   - *Deezer lookup failed*: paths built from tags, where Deemix parity is uncertain.
   - *Deezer metadata disagrees with tags* and *Album artist differs from track artist*: mis-tagged files. They are reported only, never retagged.
   - *Left in place*: unexpected files that keep their folder.
   - *Trashed duplicate copies*: each line names the canonical copy that replaces it.
5. **Live file phase:**
   ```bash
   python3 -m reorganize_playlists migrate
   ```
   The report must end with *Self-check passed*. Note the printed manifest path, which you need for a rollback.
6. **Start Jellyfin and refresh everything:**
   ```bash
   docker compose up -d jellyfin
   ```
   In Jellyfin, go to Dashboard → Libraries → *Music* → ⋯ → **Refresh metadata** → *Scan for new and updated files* + **Replace all metadata** (also replace images). Wait for it to finish. An ordinary rescan does not overwrite the stale album and artist values.
7. **Create the API key** (if you haven't yet): Dashboard → API Keys → +. Then `cp .env.example .env` and set `JELLYFIN_API_KEY` (and `JELLYFIN_USER` if it isn't `john`).
8. **Playlist phase:**
   ```bash
   python3 -m reorganize_playlists migrate --phase playlists --dry-run
   python3 -m reorganize_playlists migrate --phase playlists
   ```
   This scans and waits, then creates the playlists with their covers. It writes `.playlists/map.json` and `.playlists/imports/`, moves the root playlist files out of the library, exports and commits. If it refuses because entries are missing in Jellyfin, let the scan finish (or fix the listed paths) and re-run.
9. **Start Deemix** with the structure-playlist settings already applied in `deemix-config/config.json`:
   ```bash
   docker compose up -d deemix
   ```
10. **Verify** with the checklist below.

## Done checklist

- [ ] The file-phase report says *Self-check passed* (unique songs before = after; every trashed copy has a canonical copy).
- [ ] No audio outside album folders: `ls ~/Music/Deemix` shows no `Playlists/` (unless conflicts were reported) and no loose `.flac`/`.mp3`.
- [ ] Jellyfin shows no "Playlists" artist and none of the 37 pseudo-albums.
- [ ] 37 playlists, all editable (add, remove, reorder) and owned by you, with the original track counts. No duplicate "Untitled" or file-based copies.
- [ ] Every playlist entry resolves (the playlist phase report has no *Entries not found in Jellyfin*).
- [ ] Spot check: Cymande's artist page shows only "Dove", under its real album.
- [ ] Spot check: `The Roots - Things Fall Apart` has gained no extra tracks.
- [ ] Deemix check: re-download one small playlist you already own. Nothing new is downloaded, one `<Playlist>.m3u8` appears at the root, and `python3 -m reorganize_playlists import` adds nothing.
- [ ] `git -C ~/Music/Deemix log --stat` shows the migrate commits and tracks only text files.
- [ ] When satisfied, empty `~/Music/Deemix-trash/` and delete the APFS clone by hand.

## Rollback

Undo the newest run first:

```bash
python3 -m reorganize_playlists rollback ~/Music/Deemix/.reorganize/runs/<id>/manifest.json
```

Rolling back the playlist phase deletes the Jellyfin playlists it created, so it needs the API key. Rolling back the file phase should be done with Jellyfin stopped. If anything is beyond repair, restore from the APFS clone.

## After the migration: every Deemix session

Download playlists in Deemix (http://localhost:6595), then run:

```bash
python3 -m reorganize_playlists import --dry-run   # optional preview
python3 -m reorganize_playlists import
```
