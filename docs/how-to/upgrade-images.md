# How to upgrade the pinned images

The library layout depends on Jellyfin's folder→album rules and on Deemix's
path generation, so never use `latest`.

- **Deemix:** compare `packages/deemix/src/utils/pathtemplates.ts` (and `types/Album.ts` for `discTotal`) between the pinned tag and the new one against `reorganize_playlists/deemix.py`. Bump the tag in `docker-compose.yml`, then `docker compose pull deemix && docker compose up -d deemix`, and re-download one small owned playlist to confirm nothing is downloaded again.
- **Jellyfin:** check the release notes for changes to music library resolution (`MusicAlbumResolver`, `MusicArtistResolver`), playlist ownership and `.ignore`/dot-file handling (see [the research](../explanation/research/jellyfin-music-metadata-research.md)). Bump the tag, then pull, `up -d`, and spot-check an artist page and a playlist edit.
