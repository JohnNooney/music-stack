# How to cut Jellyfin over to the union root

One-off cutover from scanning `~/Music/Deemix` directly to scanning the union
root `~/Music/Jellyfin` built by `union_library`
([../reference/union_library.md](../reference/union_library.md)).

The point of the exercise is that Jellyfin item IDs survive (`MD5(type +
path)`; Deemix names kept verbatim at the same `/media` mount). Prove it once:

1. `python3 -m union_library --dry-run` — read the plan, then `python3 -m union_library`.
2. `docker compose up -d jellyfin` with the new mounts (`~/Music/Jellyfin` → `/media`, `~/Music/Deemix` → `/Deemix:ro`, `~/Music/Lidarr` → `/Lidarr:ro`).
3. Trigger a library scan (Dashboard → Libraries → Scan).
4. Confirm: (a) album/song counts are unchanged apart from the new Lidarr-only albums, (b) `Head Hunters`, `Tiempo pa' matar` and `The Mouse & The Man` each appear once, (c) a few playlists still resolve their entries. If IDs were somehow lost, everything still works — it is one clean rescan, not a corruption.
