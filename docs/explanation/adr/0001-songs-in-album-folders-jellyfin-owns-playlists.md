# ADR 0001: Songs live only in album folders; Jellyfin owns playlists

**Status:** accepted (2026-11-10) · **Spec:** [0001](../specs/0001-album-folder-migration-and-jellyfin-playlists.md)

## Context

Jellyfin builds albums purely from folders: any folder that directly contains audio is one `MusicAlbum`. It is named after the first track's `ALBUM` tag and linked to the union of every track's album artists (see the [research](../research/jellyfin-music-metadata-research.md)). So each legacy playlist folder (`Playlists/<Name>/`) became a pseudo-album that appeared on dozens of artist pages, and `Playlists/` itself became an artist. Correct tags cannot fix this.

Playlists imported from `.m3u` files have no owner in Jellyfin. They can be played but not edited (every edit returns 403).

## Decision

1. **Every song lives in exactly one album folder** (`<Album artist> - <Album>/`) at the library root. No audio goes anywhere else, and legacy playlist folders are never recreated.
2. **Playlists are Jellyfin playlists owned by the user** and edited in the Jellyfin UI. Playlist files are only an import source (Deemix output) or an export (backup). They never live in the scanned part of the library.
3. Each Jellyfin playlist is linked to its Deezer playlist by **Jellyfin playlist ID**, stored in `.playlists/map.json`. A rename in Jellyfin therefore never creates a duplicate on the next import.
4. Imports never remove or reorder songs. Songs new on Deezer are appended, songs removed by hand stay removed, and songs Deezer dropped are only reported.

## Alternatives rejected

- **`.ignore` the `Playlists/` folder.** This hides the pseudo-albums, but it also hides the songs, so they could no longer be found by artist or album.
- **File-owned playlists** (keeping playlists as `.m3u` files that Jellyfin imports). Jellyfin will not let the user edit them, and every playlist would show up twice.
- **Grouping by tags instead of folders.** Jellyfin does not support it.

## Consequences

- A one-off migration was needed (`reorganize_playlists migrate`), along with an `import` step after every Deemix session.
- Do not "fix" playlists by re-adding playlist files to the library root and leaving them there. Jellyfin would import them as uneditable duplicates.
- The playlist definitions live in Jellyfin's database. Exports in the library's git repo are the backup.
