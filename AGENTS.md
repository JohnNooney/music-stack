# AGENTS.md

Home music stack: Jellyfin + Deemix + the Lidarr stack (Lidarr, Prowlarr, Soularr, Slskd, Transmission — all in `docker-compose.yml`, see `docs/reference/lidarr-stack.md`) and three stdlib-only tools: `reorganize_playlists` (imports/migration inside the Deemix library), `union_library` (the `~/Music/Jellyfin` symlink union Jellyfin scans — see `docs/reference/union_library.md`, ADR 0004) and `library_watcher` (the compose sidecar that polls the source trees and runs migrate → union → import on change — spec 0004, ADR 0005). Vocabulary is in `CONTEXT.md`. Read `docs/explanation/adr/` before changing the library layout, the Deemix settings or the pinned images. Secrets live only in `.env` and the git-ignored app config dirs — never whitelist `soularr/config.ini` in `.gitignore`.

Docs follow [Diátaxis](https://diataxis.fr/): `docs/how-to/` (task guides), `docs/reference/` (facts — tool usage, layouts, settings), `docs/explanation/` (why — `adr/`, `specs/`, `research/`). Index at `docs/README.md`. Put new docs in the matching quadrant and don't mix types in one page — link out instead. No `tutorials/` yet; don't create empty scaffolding.

## Verify

- Tests: `python3 -m unittest` (full suite, about 20 s because of real git commits) or `python3 -m unittest tests.test_import` (one file).
- Typecheck: `.venv/bin/mypy` (strict; `.venv` is a symlink to `~/.venvs/jellyfin` — the workspace volume is exFAT, so a venv created in-tree dies on `._*.pth` AppleDouble files at interpreter startup).
- The tool itself is stdlib-only; keep it that way.

## Testing seam

Test only through `main(argv, deezer=FakeDeezer, jellyfin=FakeJellyfin)` (`reorganize_playlists`), `main(argv)` (`union_library`, no fakes — it makes no API calls) or `main(argv, runner=..., clock=..., jellyfin=FakeJellyfin)` (`library_watcher` — the runner records subprocess argv and returns scripted exits; the clock scripts poll-by-poll filesystem changes) against real temp trees, observing files, reports and fake-client state. The HTTP clients get a manual smoke check, not unit tests.

## Gotchas

- macOS volumes are case- and normalisation-insensitive: `Deemix/` and `deemix/` collide in a temp dir, and NFC/NFD names refer to the same file.
- python.org Python on macOS has no CA bundle; `deezer.py` falls back to `/etc/ssl/cert.pem`.
- `/Volumes/512GB SSD/Music` is the real music tree (compose's `MUSIC_DIR`). Every tool's path defaults come from `MUSIC_ROOT`/`DEEMIX_ROOT`/`LIDARR_ROOT`/`UNION_ROOT` env vars — flags override. Live runs move real files, so dry-run first.
