# Library layout rules

The rules `~/Music/Deemix` (the library root) obeys. `union_library` mirrors
this tree into the union root, and `migrate` enforces them — so a file out of
place here ends up misplaced in what Jellyfin scans.

- **One folder = one album.** Every song lives in an album folder `<Album artist> - <Album>/` at the library root. Multi-disc albums get `CD<n>/` subfolders. Jellyfin makes an album out of every folder that holds audio, so nothing else may hold audio. ([ADR 0001](../explanation/adr/0001-songs-in-album-folders-jellyfin-owns-playlists.md))
- **Exact Deemix paths.** Files are named exactly as Deemix names them (`<NN> - <Title>.<ext>`), so Deemix recognises songs it already has. ([ADR 0002](../explanation/adr/0002-deemix-structure-playlist-mode-and-exact-deemix-paths.md))
- **Each song is stored once.** Duplicate copies go to `~/Music/Deemix-trash/`, which is never deleted automatically.
- **Playlists live in Jellyfin.** Playlist files appear at the root only briefly, after a Deemix download, until `import` moves them out.
- **Hidden data is dot-prefixed** so Jellyfin ignores it: `.playlists/` (exports, import references, `map.json`), `.artifacts/<playlist>/` (errors.txt, cover), `.inventory.tsv`, `.reorganize/` (tool state), and a text-only `.git`. ([ADR 0003](../explanation/adr/0003-no-git-for-audio-apfs-clone-and-text-only-git.md))
