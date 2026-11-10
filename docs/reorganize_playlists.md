# reorganize_playlists

A command-line tool that keeps the Deemix library in album folders and keeps the Jellyfin playlists in step with it. It uses only the Python standard library (Python ≥ 3.11). Terms follow [CONTEXT.md](../CONTEXT.md).

```bash
cd /Users/john/Docker/jellyfin
python3 -m reorganize_playlists [global options] <command> [options]
```

## Global options

| Option | Default | Meaning |
|---|---|---|
| `--root PATH` | `/Users/john/Music/Deemix` | Library root |
| `--trash PATH` | `<root>-trash` | Trash, which must be outside the root. Each run gets `<trash>/<run id>/`, and paths inside mirror the library |
| `--env PATH` | `<repo>/.env` | `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `JELLYFIN_USER`, `JELLYFIN_MEDIA_ROOT` (see `.env.example`) |
| `--deemix-config PATH` | `<repo>/deemix-config/config.json`, else `<root>/Config/config.json` | Templates, padding and replacer for the Deemix path |

## Commands

| Command | Needs Jellyfin API key | What it does |
|---|---|---|
| `migrate [--dry-run]` | no | **File phase.** Moves every song out of `Playlists/<Name>/` (and loose root tracks) to its Deemix path. Keeps one canonical copy per song and trashes the duplicate copies. Rewrites root playlist files to the new paths. Archives `cover.jpg`/`errors.txt` to `.artifacts/<Name>/`, trashes stale in-folder playlist files, stray logs and dedup_music leftovers, then removes the emptied folders. Refuses while Jellyfin is scanning and warns while it is running. |
| `migrate --phase playlists [--dry-run]` | yes | **Playlist phase.** Triggers a Jellyfin scan and waits for it, then creates one Jellyfin playlist per root playlist file, owned by `JELLYFIN_USER` and in file order, with the archived cover. Writes `.playlists/map.json`, moves each playlist file to `.playlists/imports/<Name>.m3u8` (trash keeps the original), then exports and commits. Refuses if any entry is not in Jellyfin. |
| `import [--dry-run]` | yes | **After every Deemix session.** Scans and waits, then does a three-way merge for each root `*.m3u8` (details below). Archives root `errors.txt`/`cover.jpg` to that playlist's artifacts and uploads the cover. Moves the playlist file to `.playlists/imports/`, then exports and commits. |
| `export` | yes | Writes `.playlists/jellyfin/<Name>.m3u8` for each of the user's playlists, plus `.inventory.tsv`, and commits. |
| `rollback <manifest.json>` | only to undo Jellyfin changes | Undoes a live run newest-first: moves files back, restores or deletes written files, recreates removed folders, deletes Jellyfin playlists the run created and removes entries it appended. The manifest is renamed `*.rolled-back.json`. |

Each run prints a report and saves it to `<root>/.reorganize/runs/<run id>/report.txt`. Live runs also write `manifest.json` there. Dry runs touch nothing in the library except that state folder and the Deezer cache.

## How songs are placed

- **Song identity.** ISRC first, then normalised artist + title. Different ISRCs are different recordings (for example, original vs remaster) and are kept apart.
- **Canonical copy.** A copy already in an album folder always wins, and album folders are never modified except to gain an adopted `.lrc`. Otherwise FLAC beats MP3, and then the larger file wins.
- **Deemix path.** `%artist% - %album%` uses the album's main artist from Deezer, looked up by `BARCODE` first and then by ISRC. `CD<n>/` is added only when the album has more than one disc. The track number is zero-padded to the digit length of the track total (minimum 2). `\0 / \ : * ? " < > |` become `_`, names are NFC-normalised, and components are cut to 200 UTF-16 units with trailing dots and spaces stripped. If Deezer doesn't know the song, the tags are used and the song is listed in the report.
- **Never overwrites.** If a different recording already occupies the Deemix path, the song stays where it is, its playlist entries still point at it, and it is listed under *Conflicts*.
- **New album folders** get `cover.jpg` from the canonical copy's embedded art. Existing folders are merged into, not touched.
- **`.lrc` sidecars** follow their audio. A duplicate copy's sidecar is adopted only if the canonical copy has none, and is trashed otherwise.
- **Self-check** after a live file phase: the set of unique songs is the same before and after, and every trashed audio file has a canonical copy of the same song.

## Import merge rules

For each playlist, given the previous reference (`.playlists/imports/<Name>.m3u8`), the new Deemix file and the current Jellyfin playlist:

- Songs that are in the new file but in neither the reference nor Jellyfin are **appended at the end**, in Deezer order.
- Songs removed in Jellyfin by hand are **not re-added**.
- The **order in Jellyfin is never changed**.
- Songs in the reference that are missing from the new file are **reported as dropped on Deezer**, not removed.
- If there is no mapping, or the mapped playlist was deleted, a **new playlist owned by the user** is created.
- Blank lines (failed Deemix downloads) are ignored. Entries Jellyfin doesn't know are reported and left out of the reference, so they are retried on the next import.

## Hidden library data

| Path | Tracked in library git | Content |
|---|---|---|
| `.playlists/imports/*.m3u8` | yes | Last imported Deezer list per playlist |
| `.playlists/jellyfin/*.m3u8` | yes | Exports of the Jellyfin playlists |
| `.playlists/map.json` | yes | `{ "<Deezer title>": "<Jellyfin playlist id>" }` |
| `.artifacts/<Name>/errors.txt` | yes | Failed-download log for retrying songs later |
| `.artifacts/<Name>/cover.jpg` | no | Playlist cover |
| `.inventory.tsv` | yes | Every audio file: path, ISRC, size, artist, album, title |
| `.reorganize/` | no | Deezer cache, run reports and manifests |

## Development

```bash
python3 -m unittest                         # full suite
python3 -m unittest tests.test_import       # one file
.venv/bin/mypy                              # strict typecheck (python3 -m venv .venv && .venv/bin/pip install mypy)
```

Tests drive `main(argv, deezer=FakeDeezer, jellyfin=FakeJellyfin)` against a real temporary library built by `tests/support.py`, which writes minimal valid FLAC/MP3 files. The real HTTP clients (`HttpDeezerClient`, `HttpJellyfinClient`) are thin and checked by hand: the runbook dry run exercises Deezer, and the playlist phase exercises Jellyfin.
