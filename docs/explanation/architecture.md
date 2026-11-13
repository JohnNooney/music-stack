# How the stack fits together

Two download paths feed one library. **Deemix** downloads from Deezer into
`~/Music/Deemix`; the **Lidarr stack** downloads from Soulseek and torrent
indexers into `~/Music/Lidarr/media/music`. `union_library` merges the two
source trees into `~/Music/Jellyfin` — a directory of relative symlinks, one
per album — and that union root is the only directory Jellyfin scans. The
`library-watcher` compose sidecar keeps it all current without anyone running
anything by hand.

```
 Deemix (Deezer)                          Lidarr stack (Soulseek / torrents)
      │                                          │
      ▼                                          ▼
 ~/Music/Deemix                     ~/Music/Lidarr/media/music
 (library root)                     (Lidarr source tree)
      │                                          │
      └────────────── union_library ─────────────┘
                     │ one symlink per album
                     ▼
              ~/Music/Jellyfin  (union root)
                     │ scanned by
                     ▼
                  Jellyfin
```

## The maintenance pipeline

Changes in the source trees are turned into Jellyfin-visible state in a fixed
order — the same order whether `library-watcher` runs it automatically or a
human runs it by hand:

1. **`migrate`** (`reorganize_playlists`) — moves loose tracks into their
   Deemix paths, trashes duplicate copies, refuses to run while Jellyfin is
   scanning. Only ever touches the Deemix tree.
2. **`union_library`** — rebuilds the union root's links to match the source
   trees, and nudges a Jellyfin rescan if anything changed.
3. **`import`** (`reorganize_playlists`) — waits for a Jellyfin scan of the
   refreshed union, then merges each new Deemix `*.m3u8` into the matching
   Jellyfin playlist, exports all playlists and commits to the library's
   text-only git.

The order matters: unmigrated content must never reach the union, because the
union mirrors every top-level Deemix entry verbatim and Jellyfin turns any
folder holding audio into an album
([spec 0004](specs/0004-library-watcher.md), [ADR 0005](adr/0005-library-watcher-sidecar.md)).

## Why a union root instead of two libraries

Jellyfin deduplicates poorly across multiple libraries and builds albums
purely from folders, so one scanned root with one entry per album is what
keeps every song browsable by its real artist and album. Deemix album-folder
names are kept verbatim so the `MD5(type + path)` item IDs Jellyfin already
has stay valid across the cutover
([ADR 0004](adr/0004-union-library-over-deemix-and-lidarr.md),
[research](research/jellyfin-multilibrary-dedup-research.md)).

## Why album folders and Jellyfin-owned playlists

Every folder that directly holds audio becomes one Jellyfin `MusicAlbum`, so
the old `Playlists/<Name>/` layout produced a pseudo-album per playlist that
leaked onto dozens of artist pages — a defect tags cannot fix, because
Jellyfin ignores the `ALBUM` tag when grouping. File-based playlists can't be
edited in the UI (every edit returns 403), so playlists are owned by Jellyfin
and `.m3u8` files exist only as import sources and exports
([ADR 0001](adr/0001-songs-in-album-folders-jellyfin-owns-playlists.md),
[research](research/jellyfin-music-metadata-research.md)).

## The Lidarr download path

```
You add an artist in Lidarr
        │
        ▼
Lidarr pulls MusicBrainz metadata → albums become "wanted/missing"
        │
        ├──► (torrent path) Lidarr searches Prowlarr indexers → sends
        │    torrents to Transmission → imports finished files
        │
        └──► (soulseek path) Soularr polls Lidarr's wanted list every
             300s → searches Slskd → peers send files → Soularr tells
             Lidarr to import
        │
        ▼
Files land in DATA_DIR/media/music → union_library symlinks them into the
union root → Jellyfin serves them
```

## Automation: why a polling sidecar

The watcher polls the source trees on an interval and waits for a quiet
period before running the pipeline, because Docker Desktop file-event
propagation into containers is unreliable and downloads land progressively —
stability, not the first changed byte, is the trigger. A `launchd` watcher
would get real FSEvents but lives outside the compose-managed stack
([ADR 0005](adr/0005-library-watcher-sidecar.md), [trigger-options
research](research/deemix-jellyfin-plugin-research.md)).

## Decision trail

- [ADRs](adr/) — the decisions not to undo without reading first.
- [Specs](specs/) — the design documents the tools were built from.
- [Research notes](research/) — the primary-source investigations behind the
  ADRs.
