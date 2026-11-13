# ADR 0002: Deemix structure-playlist mode; migrated songs at their exact Deemix path

**Status:** accepted (2026-11-10) · **Spec:** [0001](../specs/0001-album-folder-migration-and-jellyfin-playlists.md)

## Context

Deemix skips a track only when a file already exists at the **exact path** it would write (`overwriteFile: 'l'`). If migrated songs sat anywhere else, every later playlist download would download them again into a second album folder. Deemix computes that path from Deezer album data that the files' tags do not carry, namely the album's track total (for padding the track number) and disc total (for `CD<n>` folders).

## Decision

1. Deemix runs in **structure-playlist mode**: `createStructurePlaylist: true`, `createPlaylistFolder: false`, `playlistTracknameTemplate: "%tracknumber% - %title%"`, `createM3U8File: true`, `playlistFilenameTemplate: "%title%"`. Playlist tracks land at `<Album artist> - <Album>/[CD<n>/]<NN> - <Title>.<ext>`, and one `<Playlist>.m3u8` is written at the library root.
2. The migration places every song at that **exact Deemix path**. `reorganize_playlists/deemix.py` ports `fixName`, `fixLongName`, `antiDot`, `pad` and the CD-folder rule from `bambanah/deemix` `utils/pathtemplates.ts`, and reads the templates, padding and replacer from Deemix's `config.json`.
3. The album title, album main artist, track total and disc total come from **Deezer's public API**:
   - First by the file's `BARCODE` tag (`album/upc:<barcode>`). This is the exact release Deemix downloaded the track from.
   - Then by ISRC (`track/isrc:<isrc>` → `album/<id>`). An ISRC lookup can return a compilation rather than the original release; for example, *Bohemian Rhapsody* resolves to a "Songs You Need To Listen To…" compilation. That is why the barcode comes first. This is a refinement of the spec, which names ISRC only.
   - The disc total is the highest `disk_number` in the album's track list, because the public album endpoint has no `nb_disk`. Deemix gets it from the private gateway API.
   - Lookups are cached in `<library>/.reorganize/deezer-cache.json`. If a lookup fails, the tags are used instead and the song is listed in the report.
4. The images are **pinned** (`ghcr.io/bambanah/deemix:v4.8.0`, `jellyfin/jellyfin:12.4`). The path code is unchanged from v4.5.2 to v4.8.0, and Jellyfin's folder→album rules were verified at 12.4.

## Consequences

- Before upgrading Deemix, diff `pathtemplates.ts` against the port in `deemix.py`. Any change to path generation breaks skip-if-exists.
- Changing `albumNameTemplate`, `albumTracknameTemplate`/`playlistTracknameTemplate`, the padding settings or `illegalCharacterReplacer` has the same effect. The tool warns when the two track templates differ or structure mode is off.
- Songs where Deezer and the tags disagree on album or album artist are reported, never retagged.
