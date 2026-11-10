# AGENTS.md

Home music stack: Jellyfin + Deemix (`docker-compose.yml`) and the `reorganize_playlists` tool. Vocabulary is in `CONTEXT.md`. Read `docs/adr/` before changing the library layout, the Deemix settings or the pinned images.

## Verify

- Tests: `python3 -m unittest` (full suite, about 20 s because of real git commits) or `python3 -m unittest tests.test_import` (one file).
- Typecheck: `.venv/bin/mypy` (strict; create it with `python3 -m venv .venv && .venv/bin/pip install mypy`).
- The tool itself is stdlib-only; keep it that way.

## Testing seam

Test only through `main(argv, deezer=FakeDeezer, jellyfin=FakeJellyfin)` against a real temp library built with `tests/support.py`, observing files, reports and fake-client state. The HTTP clients get a manual smoke check, not unit tests.

## Gotchas

- macOS volumes are case- and normalisation-insensitive: `Deemix/` and `deemix/` collide in a temp dir, and NFC/NFD names refer to the same file.
- python.org Python on macOS has no CA bundle; `deezer.py` falls back to `/etc/ssl/cert.pem`.
- `/Users/john/Music/Deemix` is the real library. Live runs move real files, so dry-run first.
