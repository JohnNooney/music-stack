# union_library

`union_library` builds and maintains the **union root** `$MUSIC_DIR/Jellyfin/` — one relative symlink per album pointing into whichever source tree holds the canonical copy — the only directory Jellyfin scans. Deemix-sourced entries keep the Deemix album folder's name verbatim, so every existing Jellyfin item keeps its path and its ID ([ADR 0004](../explanation/adr/0004-union-library-over-deemix-and-lidarr.md)).

Stdlib-only, no API calls; the only filesystem effects are `symlink`/`unlink` inside the union root. Neither source tree is ever modified.

**Tasks:** [cut Jellyfin over to the union root](../how-to/cut-over-union-root.md).

```bash
python3 -m union_library --dry-run   # show the whole plan first
python3 -m union_library             # apply it
```

| Flag | Default | Purpose |
|---|---|---|
| `--union` | env `UNION_ROOT`, else `$MUSIC_ROOT/Jellyfin` | union root (created on the first live run) |
| `--deemix` | env `DEEMIX_ROOT`, else `$MUSIC_ROOT/Deemix` | Deemix library root |
| `--lidarr` | env `LIDARR_ROOT`, else `$MUSIC_ROOT/Lidarr/media/music` | Lidarr music root |
| `--overrides` | `union_library_overrides` (repo root) | overrides file (absent = no overrides) |
| `--exclude NAME` | — | extra Deemix root entries never mirrored (repeatable) |
| `--dry-run` | off | report only, no filesystem changes |

`MUSIC_ROOT` itself defaults to `/Volumes/512GB SSD/Music` (the compose `MUSIC_DIR` source). Flags beat env vars, env vars beat the default.

Each run prints a report (and saves it under `<union>/.union/runs/<run>/report.txt`) with, in order: **Linked (new)**, **Relinked (Deemix → Lidarr)**, **Ambiguous matches (kept Deemix)**, **Overridden**, **Loose-root items mirrored**, **Excluded**, **Foreign entries (untouched)**, **Pruned dangling links**, **Non-disc subfolders (Jellyfin will split these)**, **Failed actions**, and a reminder to rescan. Re-running on an unchanged world produces an empty plan.

## How entries are chosen

- **Deemix album folders** (`<Album artist> - <Album>`) are linked verbatim.
- **Overlap.** Match keys are normalised artist + album (NFC, case-folded, punctuation stripped, whitespace collapsed, trailing `(YYYY)` removed). One confident match → the entry keeps the Deemix name but targets the **Lidarr** copy. More than one candidate (e.g. two year editions) → **ambiguous**: reported, Deemix kept.
- **Lidarr-only albums** get constructed `<Artist> - <Album> (<Year>)` names. A name already taken in the union root is skipped and reported, never overwritten.
- **Loose Deemix root items** (`.m3u8`, `.txt`, `.gitignore`, stray dirs) are mirrored verbatim — except macOS volume noise (`._*` AppleDouble sidecars, `.DS_Store`), which is never mirrored. Tooling dirs (`Config`, `.git`, `.reorganize`, `.artifacts`, `.playlists`, `_duplicates_trash`, `Deemix-trash`) are excluded and reported.
- **Pruning.** A union link whose target vanished is removed and reported; so is a union-created link to volume noise from before the carve-out existed. Entries the tool did not create are foreign: reported, untouched.
- **Split-album detection.** Album folders whose audio lives in subfolders that aren't Jellyfin disc names (`cd`, `disc`, `disk`, `vol`, `volume`, `part`, `act` + number — `AlbumParser.IsMultiPart` at v12.4) get split into separate albums by the scanner, e.g. a `12 Vinyl 01`/`12 Vinyl 02` download. They are reported under *Non-disc subfolders*; fix them at the source by renaming to e.g. `CD 1`/`CD 2` (and let Lidarr rescan if the album is Lidarr-managed). The tool reports only — it never renames in a source tree.

## Overrides

`union_library_overrides` (repo root) settles matches the normaliser can't, one directive per line (`#` comments allowed):

```
match Eek-A-Mouse - The Mouse And The Man = Eek‐A‐Mouse/The Mouse & The Man (1983)
prefer-deemix <deemix-name> = <lidarr-artist>/<lidarr-album>
keep-both <deemix-name> = <lidarr-artist>/<lidarr-album>
```

`match` forces the dedupe (Lidarr target), `prefer-deemix` forces the match but keeps the Deemix copy, `keep-both` suppresses the dedupe and emits both entries. Names are literal folder names; directives that name nothing on disk are reported as unused, and malformed lines abort the run.

## Routine use

After Deemix or Lidarr/Soularr downloads land: `python3 -m union_library`, then let the scheduled Jellyfin scan pick it up (or trigger one). The run is idempotent and safe to repeat.
