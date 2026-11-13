# Key settings and why

Settings in `deemix-config/config.json` and Jellyfin that the library layout
depends on. Changing the Deemix path templates breaks skip-if-exists, because
`migrate` reproduces these paths when placing downloads
([../reference/reorganize_playlists.md](reorganize_playlists.md)).

| Where | Setting | Why |
|---|---|---|
| Deemix | `createStructurePlaylist: true`, `createPlaylistFolder: false` | Playlist tracks go into album folders. Both are required: with the playlist folder on, tracks land in `Playlists/<Name>/Artist - Album/`. |
| Deemix | `playlistTracknameTemplate: "%tracknumber% - %title%"` | Deemix uses the playlist template for playlist tracks even in structure mode, so it must match `albumTracknameTemplate`. |
| Deemix | `createM3U8File: true`, `playlistFilenameTemplate: "%title%"` | Writes `<Title>.m3u8` at the root, with paths relative to the root, for `import`. |
| Deemix | `overwriteFile: 'l'`, `albumNameTemplate: "%artist% - %album%"`, `illegalCharacterReplacer: "_"`, padding | Unchanged. The migration reproduces paths from these, so changing them breaks skip-if-exists. |
| Jellyfin | MusicBrainz enabled for albums/artists | Kept. After bulk moves, run *Refresh metadata → Replace all metadata*, because ordinary rescans keep stale album/artist values. |
| Jellyfin | Custom tag delimiters off | Out of scope. Combined artist tags such as `Mack 10/Ice Cube` stay as one artist. |

The original Deemix config is kept as `deemix-config/config.json.before-structure-playlist`.
