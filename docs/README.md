# Documentation

Organised along the [Diátaxis](https://diataxis.fr/) quadrants: **how-to
guides** get a real-world task done, **reference** is what you consult while
working, **explanation** is the why behind the design. There are no tutorials
yet — [setup](how-to/setup.md) is the closest thing to a first-run
walkthrough.

## How-to guides

| Guide | Task |
|---|---|
| [setup.md](how-to/setup.md) | Fresh clone → running stack, end to end |
| [wire-lidarr-stack.md](how-to/wire-lidarr-stack.md) | Per-service wiring for Lidarr, Prowlarr, Transmission, Slskd, Soularr |
| [add-music.md](how-to/add-music.md) | Get an artist downloaded through the Soulseek/torrent pipeline |
| [cut-over-union-root.md](how-to/cut-over-union-root.md) | Point Jellyfin at the union root for the first time |
| [migrate-library.md](how-to/migrate-library.md) | One-off move out of legacy playlist folders, with the done checklist |
| [upgrade-images.md](how-to/upgrade-images.md) | Bump the pinned Jellyfin/Deemix images safely |

## Reference

| Doc | Contents |
|---|---|
| [library-layout.md](reference/library-layout.md) | The rules `$MUSIC_DIR/Deemix` obeys |
| [settings.md](reference/settings.md) | The Deemix/Jellyfin settings the layout depends on |
| [reorganize_playlists.md](reference/reorganize_playlists.md) | `reorganize_playlists` commands, options, merge rules |
| [union_library.md](reference/union_library.md) | `union_library` flags, matching, overrides |
| [lidarr-stack.md](reference/lidarr-stack.md) | Service ports, data layout, secrets layout, networking |

Root files that are also reference: [../CONTEXT.md](../CONTEXT.md) (vocabulary)
and [../AGENTS.md](../AGENTS.md) (agent instructions).

## Explanation

| Doc | Question it answers |
|---|---|
| [architecture.md](explanation/architecture.md) | How the pieces fit together and why |
| [adr/](explanation/adr/) | The five decisions not to undo without reading |
| [specs/](explanation/specs/) | Design specs the tools were built from |
| [research/](explanation/research/) | Primary-source investigations behind the ADRs |
| [dedup_music.md](explanation/dedup_music.md) | The retired tool, kept for history |
