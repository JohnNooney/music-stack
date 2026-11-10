# Home music stack

Deemix downloads music into one library on disk. Jellyfin serves that library, laid out so every song can be browsed by its real artist and album. Playlists are Jellyfin playlists you edit in the Jellyfin UI. Vocabulary: [CONTEXT.md](CONTEXT.md).

## Services (`docker-compose.yml`)

| Service | Image (pinned) | Port | Volumes |
|---|---|---|---|
| `jellyfin` | `jellyfin/jellyfin:12.4` | 8096/tcp (web), 7359/udp (discovery) | `./config` → `/config`, `./cache` → `/cache`, `~/Music/Deemix` → `/media` |
| `deemix` | `ghcr.io/bambanah/deemix:v4.8.0` | 6595 (web) | `~/Music/Deemix` → `/downloads`, `./deemix-config` → `/config` |

Both run as uid/gid 501. `config/`, `cache/`, `deemix-config/` and `.env` are git-ignored. `deemix-config/` holds Deemix's credentials, queue and logs, which used to live in the music library.

```bash
docker compose up -d                  # start both
docker compose stop jellyfin          # e.g. before moving files
docker compose logs -f deemix
```

## Library layout rules (`/Users/john/Music/Deemix`)

- **One folder = one album.** Every song lives in an album folder `<Album artist> - <Album>/` at the library root. Multi-disc albums get `CD<n>/` subfolders. Jellyfin makes an album out of every folder that holds audio, so nothing else may hold audio. ([ADR 0001](docs/adr/0001-songs-in-album-folders-jellyfin-owns-playlists.md))
- **Exact Deemix paths.** Files are named exactly as Deemix names them (`<NN> - <Title>.<ext>`), so Deemix recognises songs it already has. ([ADR 0002](docs/adr/0002-deemix-structure-playlist-mode-and-exact-deemix-paths.md))
- **Each song is stored once.** Duplicate copies go to `~/Music/Deemix-trash/`, which is never deleted automatically.
- **Playlists live in Jellyfin.** Playlist files appear at the root only briefly, after a Deemix download, until `import` moves them out.
- **Hidden data is dot-prefixed** so Jellyfin ignores it: `.playlists/` (exports, import references, `map.json`), `.artifacts/<playlist>/` (errors.txt, cover), `.inventory.tsv`, `.reorganize/` (tool state), and a text-only `.git`. ([ADR 0003](docs/adr/0003-no-git-for-audio-apfs-clone-and-text-only-git.md))

## Workflow: download → import

1. Open Deemix at http://localhost:6595 and download playlists. Tracks land straight in album folders, and one `<Playlist>.m3u8` is written at the library root.
2. Run the import:
   ```bash
   python3 -m reorganize_playlists import
   ```
   This scans Jellyfin and waits for the scan to finish. It appends songs that are new on Deezer to the matching Jellyfin playlist without undoing your edits, and reports songs Deezer dropped. It archives `errors.txt`/`cover.jpg` and uploads the cover, moves the playlist file out of the library, exports all playlists and the inventory, and commits to the library's git repo (never pushed).

Setup: `cp .env.example .env` and set `JELLYFIN_API_KEY` (Jellyfin → Dashboard → API Keys). Full tool reference: [docs/reorganize_playlists.md](docs/reorganize_playlists.md). The one-off migration from the old `Playlists/<Name>/` layout: [docs/runbook-migration.md](docs/runbook-migration.md).

## Key settings and why

| Where | Setting | Why |
|---|---|---|
| Deemix | `createStructurePlaylist: true`, `createPlaylistFolder: false` | Playlist tracks go into album folders. Both are required: with the playlist folder on, tracks land in `Playlists/<Name>/Artist - Album/`. |
| Deemix | `playlistTracknameTemplate: "%tracknumber% - %title%"` | Deemix uses the playlist template for playlist tracks even in structure mode, so it must match `albumTracknameTemplate`. |
| Deemix | `createM3U8File: true`, `playlistFilenameTemplate: "%title%"` | Writes `<Title>.m3u8` at the root, with paths relative to the root, for `import`. |
| Deemix | `overwriteFile: 'l'`, `albumNameTemplate: "%artist% - %album%"`, `illegalCharacterReplacer: "_"`, padding | Unchanged. The migration reproduces paths from these, so changing them breaks skip-if-exists. |
| Jellyfin | MusicBrainz enabled for albums/artists | Kept. After bulk moves, run *Refresh metadata → Replace all metadata*, because ordinary rescans keep stale album/artist values. |
| Jellyfin | Custom tag delimiters off | Out of scope. Combined artist tags such as `Mack 10/Ice Cube` stay as one artist. |

The original Deemix config is kept as `deemix-config/config.json.before-structure-playlist`.

## Upgrading the pinned images

The library layout depends on Jellyfin's folder→album rules and on Deemix's path generation, so never use `latest`.

- **Deemix:** compare `packages/deemix/src/utils/pathtemplates.ts` (and `types/Album.ts` for `discTotal`) between the pinned tag and the new one against `reorganize_playlists/deemix.py`. Bump the tag in `docker-compose.yml`, then `docker compose pull deemix && docker compose up -d deemix`, and re-download one small owned playlist to confirm nothing is downloaded again.
- **Jellyfin:** check the release notes for changes to music library resolution (`MusicAlbumResolver`, `MusicArtistResolver`), playlist ownership and `.ignore`/dot-file handling (see [the research](docs/jellyfin-music-metadata-research.md)). Bump the tag, then pull, `up -d`, and spot-check an artist page and a playlist edit.

## Docs

- [docs/reorganize_playlists.md](docs/reorganize_playlists.md): tool usage
- [docs/runbook-migration.md](docs/runbook-migration.md): one-off migration, with the done checklist
- [docs/adr/](docs/adr/): decisions you should not undo without reading them first
- [docs/jellyfin-music-metadata-research.md](docs/jellyfin-music-metadata-research.md): why Jellyfin made pseudo-albums
- [docs/specs/](docs/specs/): specs
- [docs/dedup_music.md](docs/dedup_music.md): the retired `dedup_music.py`
