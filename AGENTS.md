# AGENTS.md

Home music stack: Jellyfin + Deemix + the Lidarr stack (Lidarr, Prowlarr, Soularr, Slskd, Transmission — all in `docker-compose.yml`, see `docs/lidarr-stack.md`) and two stdlib-only tools: `reorganize_playlists` (imports/migration inside the Deemix library) and `union_library` (the `~/Music/Jellyfin` symlink union Jellyfin scans — see `docs/union_library.md`, ADR 0004). Vocabulary is in `CONTEXT.md`. Read `docs/adr/` before changing the library layout, the Deemix settings or the pinned images. Secrets live only in `.env` and the git-ignored app config dirs — never whitelist `soularr/config.ini` in `.gitignore`.

## Verify

- Tests: `python3 -m unittest` (full suite, about 20 s because of real git commits) or `python3 -m unittest tests.test_import` (one file).
- Typecheck: `.venv/bin/mypy` (strict; create it with `python3 -m venv .venv && .venv/bin/pip install mypy`).
- The tool itself is stdlib-only; keep it that way.

## Testing seam

Test only through `main(argv, deezer=FakeDeezer, jellyfin=FakeJellyfin)` (`reorganize_playlists`) or `main(argv)` (`union_library`, no fakes — it makes no API calls) against real temp trees, observing files, reports and fake-client state. The HTTP clients get a manual smoke check, not unit tests.

## Gotchas

- macOS volumes are case- and normalisation-insensitive: `Deemix/` and `deemix/` collide in a temp dir, and NFC/NFD names refer to the same file.
- python.org Python on macOS has no CA bundle; `deezer.py` falls back to `/etc/ssl/cert.pem`.
- `/Users/john/Music/Deemix` is the real library. Live runs move real files, so dry-run first.
