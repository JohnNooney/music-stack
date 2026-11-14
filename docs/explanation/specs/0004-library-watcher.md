# Spec 0004: `library_watcher` — a compose sidecar that dedups, unions and imports on change

**Status:** ready-for-agent
**Labels:** `ready-for-agent`
**Glossary:** use the terms defined in `CONTEXT.md` at the repo root (library root, union root, union entry, source tree, playlist file, trash). New terms introduced by this spec:

- **Watcher**: the `library-watcher` compose service and its `library_watcher` stdlib package — a single-process poll loop living in this repo.
- **Fingerprint**: a cheap digest of the directory entries the watcher cares about (names + mtimes only, never file contents), recomputed each poll.
- **Quiet period**: the fingerprint must be unchanged for `QUIET_PERIOD_S` consecutive seconds before a run fires — downloads land progressively, so the trigger is *stability*, not the first changed byte.
- **Trigger set**: the input that justifies a job — the source-tree fingerprint for `union_library`, the Deemix-root `*.m3u8` name+mtime set for `import`. Its hash is what retry suppression remembers.

**Prior spec:** [0003](0003-union-library-for-deemix-and-lidarr.md) — this spec claims its deferred items "Scheduling/automation" and (partially) "Realtime Jellyfin refresh".
**Background research:** `docs/explanation/research/deemix-jellyfin-plugin-research.md` — enumerates the trigger options (Deemix WebSocket `finishDownload`/queue-empty, launchd `WatchPaths`, polling) and documents that Docker Desktop file-event propagation into containers is unreliable.

## Problem Statement

The union root (`~/Music/Jellyfin`, ADR 0004) only reflects the source trees when someone remembers to run the pipeline by hand, and Jellyfin only reflects the union when a scan runs. The routine today is `migrate` (file phase — dedup and place loose tracks) → `union_library` → `import` (scan → merge → export → git commit); skip a step and the union goes stale, or worse, unmigrated content reaches Jellyfin: Deemix singles land **loose at the library root** (`createSingleFolder: false`, `tracknameTemplate: "%artist% - %title%"`), re-downloads leave duplicate copies, and `union_library` mirrors every top-level Deemix entry verbatim — so running the union before `migrate` links loose tracks and dupes straight into the scanned tree.

Jellyfin's realtime monitor is enabled but documented-flaky through Docker Desktop bind mounts on macOS (`config/root/default/Music/options.xml` enables it; the research doc and ADR 0004 both assume scheduled scans). A host `launchd` watcher would get real FSEvents but lives outside the compose-managed stack this repo documents.

## Solution

A new **`library-watcher` service in `docker-compose.yml`**, running a new stdlib-only package `library_watcher/` from this repo. It polls the source trees every `WATCH_INTERVAL_S` (default 30 s), waits for the fingerprint to be stable for `QUIET_PERIOD_S` (default 60 s), then runs the tools as subprocesses on a single serialized worker, in the fixed order **`migrate` → `union_library` → `import`** — the same order as the manual routine:

1. **Migrate job.** A Deemix-tree change → `python3 -m reorganize_playlists migrate` (file phase, the default): moves loose tracks to their Deemix paths and trashes duplicate copies. It makes no Jellyfin calls for the file phase but *refuses while Jellyfin is scanning*, which is one reason it must run before the union's rescan nudge. Gated by `MIGRATE_MODE=auto|dry|off` (default `auto`). A Lidarr-only change skips it — `migrate` never touches the Lidarr tree.
2. **Union job.** After `migrate` (Deemix change) or directly (Lidarr-only change) → `python3 -m union_library` live. Once also at container start (unconditional reconcile — preceded by `migrate`, so the startup run also dedups first). If the run actually created or pruned links, the watcher `POST`s `/Library/Refresh` using the existing `HttpJellyfinClient`, so new downloads surface without waiting for the scheduled scan.
3. **Import job.** A new/changed Deemix-root `*.m3u8` that survives the quiet period → `python3 -m reorganize_playlists import`. `import` already chains the Jellyfin scan itself — and because it runs last, that single scan picks up the migrated, freshly-unioned tree *and* merges the playlists. Gated by `IMPORT_MODE=auto|dry|off` (default `auto`); `retag`, `rollback`, and `migrate --phase playlists` are never automated.

Failed runs are not retried every poll: the watcher records the trigger-set hash it attempted and re-fires only when the set changes or after `RETRY_COOLDOWN_S` (default 900 s), whichever comes first. Attempted trigger sets persist in `<deemix>/.reorganize/watcher-state.json` so a container restart doesn't re-fire `import` on old playlists.

## User Stories

1. As a listener, I want a Lidarr/Soularr download to appear in Jellyfin shortly after it finishes, without me running anything, so the library feels live.
2. As a listener, I want a Deemix download to appear the same way, so both pipelines behave identically.
3. As a listener, I want new Deemix playlist files imported into Jellyfin automatically, so playlists keep up with downloads.
4. As a listener, I want loose singles and duplicate copies deduplicated into album folders *before* Jellyfin ever sees them, so the library never shows stray or doubled tracks.
5. As the maintainer, I want the watcher to wait for a quiet period before running, so it never reacts to a half-written download.
6. As the maintainer, I want the same order as my manual routine — `migrate` → `union_library` → `import` — so dedup happens before linking, and `import`'s scan resolves against a migrated, freshly-unioned tree.
7. As the maintainer, I want only one job running at a time, so `migrate`'s and `import`'s real moves never race each other or a union rebuild.
8. As the maintainer, I want `migrate` and `import` each gated by `MIGRATE_MODE`/`IMPORT_MODE` (`auto`/`dry`/`off`), so I can downgrade either to report-only or disable it without touching code.
9. As the maintainer, I want a failed run retried only when its inputs change or after a cooldown, so logs aren't spammed by a persistently failing job.
10. As the maintainer, I want a container restart to converge the library immediately and *not* re-import already-processed playlists, so restarts are safe and boring.
11. As the maintainer, I want failures visible in `docker logs` with pointers to `.union/runs/` and `.reorganize/runs/` reports, so the audit trail is where the tools already put it.
12. As the maintainer, I want Jellyfin nudged via `POST /Library/Refresh` only after a union run that changed something, so idle polls cost zero API calls.
13. As the maintainer, I want `retag`, `rollback` and `migrate --phase playlists` to stay manual forever, so the watcher can never rewrite tags or undo runs on its own initiative.
13. As the maintainer, I want the watcher defined in `docker-compose.yml` like every other service, so `docker compose up -d` brings the automation up with the stack.
14. As the maintainer, I want the watcher stdlib-only, strict-mypy clean, and tested through `main(argv)` on real temp trees with injected fakes, matching repo conventions.

## Implementation Decisions

- **Package.** New `library_watcher/` package at repo root (`cli.py`, `__main__.py`), stdlib-only, `main(argv)` entry point matching the other tools' conventions. Runs the tools as **subprocesses** (`sys.executable -m reorganize_playlists migrate`, `sys.executable -m union_library`, `sys.executable -m reorganize_playlists import`) so their existing exit codes (0 clean, 1 failures, 2 misuse) and report files are reused untouched.
- **Polling, not events.** inotify/FSEvents do not propagate through Docker Desktop bind mounts on macOS — the research doc and spec 0003 both document this. The watcher computes a fingerprint each `WATCH_INTERVAL_S`: every non-dot entry under the Deemix and Lidarr music roots (relative path + mtime; directories by presence only), the Deemix-root `*.m3u8` set, plus the `union_library_overrides` file mtime. Names + mtimes only; file contents are never read. Dot entries are pruned at every level — `._*` AppleDouble sidecars and `.DS_Store` churn bump parent-dir mtimes on normal filesystems and must never read as a library change (the earlier shallow dir-mtime fingerprint had that false-positive on non-exFAT volumes). The union root itself is excluded — the watcher writes there, and watching it would self-trigger.
- **Quiet period.** A changed fingerprint starts a timer; the pipeline fires only when the fingerprint has been stable for `QUIET_PERIOD_S`. Same quiet period gates the `*.m3u8` import trigger.
- **Serialization and order.** One worker, fixed order `migrate` → `union_library` → `import`. Per-tree precision: the fingerprint keeps Deemix and Lidarr elements distinct, so a Lidarr-only change runs `union_library` alone — `migrate` tag-scans ~4,700 audio files and never touches the Lidarr tree, so it is skipped when it can't do anything. `import` runs only when its `*.m3u8` trigger is pending. Order matters beyond dedup: `migrate` refuses while Jellyfin is scanning, so it must precede the union's rescan nudge and `import`'s scan; and running `import` last lets its single scan cover both the union refresh and the playlist merge.
- **Startup.** One unconditional `migrate` + `union_library` run at container start (dedup before linking, same as the routine). Import does *not* need a special startup path: unprocessed `*.m3u8`s simply differ from the persisted trigger-set hash and fire on the first poll.
- **Retry suppression.** Per job, the SHA of the attempted trigger set is remembered. Re-attempt only when the set changes or `RETRY_COOLDOWN_S` has elapsed. Persistent state at `<deemix>/.reorganize/watcher-state.json` (a writable mount — the repo is mounted read-only).
- **Jellyfin nudge.** After a union run whose report shows link ops, `HttpJellyfinClient.start_library_scan()` (`POST /Library/Refresh`). `import` runs need no nudge — `importer` triggers and waits on its own scan.
- **Compose service `library-watcher`** modelled on the `jellyfin` service:
  - `build: docker/library-watcher` — a tiny Dockerfile, `FROM python:3.x-alpine` (pinned like the other images) + `RUN apk add --no-cache git`. Git is required: `import` commits playlist history via `git` (`history.py`), and its self-provided `user.name`/`user.email` fallback works in a bare container.
  - Repo mounted read-only at `/tools`; `PYTHONPATH=/tools`, `working_dir: /tools`. No code is baked in — edits take effect on restart.
  - `${MUSIC_DIR}:${MUSIC_ROOT:-/music}` (rw) — the host tree lands at `MUSIC_ROOT`, which the watcher uses as the base for its tree defaults (`<MUSIC_ROOT>/Jellyfin`, `/Deemix`, `/Lidarr/media/music`; `DEEMIX_ROOT`/`LIDARR_ROOT`/`UNION_ROOT` env vars override each individually). The sibling layout under `MUSIC_ROOT` is load-bearing — `union_library`'s relative symlinks must resolve the same way in-container, in Jellyfin's mounts, and on the host. The overrides file and `--env` defaults sit under the repo mount (`/tools`) and are unaffected; `*.m3u8` absolute entries are covered by `--root`-relative stripping and `playlist_file.CONTAINER_ROOTS` (`/media/`, `/downloads/`).
  - `user: "502:20"` (like `jellyfin`) so symlinks, reports and state files are owned by the host user.
  - `restart: unless-stopped`.
  - Env: `JELLYFIN_API_KEY`, `JELLYFIN_USER`, `JELLYFIN_MEDIA_ROOT`, `TZ` passed through from `.env`; **`JELLYFIN_URL=http://jellyfin:8096` overridden in the service** — `.env`'s `localhost:8096` resolves to the container itself. `MUSIC_ROOT=/music` locates the tree; `DEEMIX_ROOT`/`LIDARR_ROOT`/`UNION_ROOT` pass through as per-root overrides (empty = `MUSIC_ROOT`-derived default). Watcher knobs as env vars with defaults: `WATCH_INTERVAL_S=30`, `QUIET_PERIOD_S=60`, `RETRY_COOLDOWN_S=900`, `MIGRATE_MODE=auto`, `IMPORT_MODE=auto`.
- **Failure semantics.** A subprocess exiting 1 logs its report paths and the failure lines to stdout; exit 2 (misuse — e.g. malformed `union_library_overrides`) logs and suppresses the job until the trigger set changes. No alerting stack, no tight retry loop.
- **Sibling-safety check.** `union_library`'s check (`union.is_relative_to(source)`) is lexical on flag paths; the `MUSIC_ROOT` sibling layout satisfies it exactly as on the host.
- **Safety posture unchanged.** The watcher never writes to the source trees except `.reorganize/watcher-state.json` and the tools' own documented effects (`migrate`: moves to Deemix paths, trash, manifest; `import`: playlist-file moves, manifest, git commit — each dry-run-gated by its `*_MODE=dry`). `migrate`'s Deezer lookups need outbound network (public API, cached at `.reorganize/deezer-cache.json`) but no credentials.

## Testing Decisions

- **Same seam as the suite:** drive `main(argv)` against real temp `Deemix/`+`Lidarr/media/music/`+`Jellyfin/` trees, with injected fakes at the process boundary: a fake *runner* (records subprocess argv, returns scripted exit codes/report text) and a fake *clock/poller* (controls `WATCH_INTERVAL_S`/`QUIET_PERIOD_S` deterministically). A `FakeJellyfin` covers the rescan nudge.
- **Assertions observe outcomes:** which tool ran, in which order, with which argv; that quiet-period gating delays a run until stability; that a failed trigger set isn't retried before cooldown and is retried after it or after change; that `watcher-state.json` round-trips across a simulated restart; that `IMPORT_MODE=dry` passes `--dry-run` and `off` never invokes `import`.
- **Pipeline-order assertions:** a Deemix change produces `migrate` then `union_library` argv in that order; a Lidarr-only change produces `union_library` alone; a pending `*.m3u8` appends `import` last; `MIGRATE_MODE=dry`/`off` shapes or skips the migrate argv just like `IMPORT_MODE` does for import.
- **No real subprocesses in tests** beyond the tools' own suites; the watcher tests the *orchestration*, not the tools (already covered by `test_migrate_files.py`, `test_union_library.py`, `test_import.py`).

## Out of Scope

- **`retag`, `rollback`, and `migrate --phase playlists` automation** — tag rewriting, undo and the legacy playlist-creation phase stay permanently manual.
- **Deemix WebSocket trigger** (`ws://localhost:6595` `finishDownload`/queue-empty) — a cleaner boundary than polling, but there is no stdlib WebSocket client and the project is stdlib-only. Revisit only if the dep policy changes.
- **Real filesystem events** — impossible inside Docker Desktop bind mounts; polling is the accepted cost. A host `launchd` agent remains possible but is deliberately not built (keeps automation in the compose stack).
- **Alerting/notifications** — stdout + report files are the whole failure surface.
- **Watching the union root** — excluded by design; it is the tools' output, not an input.
- **Changes to `union_library` or `reorganize_playlists`** — the watcher orchestrates them as-is via subprocess; no new flags or seams are added to either tool.
- **Healthcheck endpoint / metrics** — `docker compose ps` + logs suffice for a homelab.

## Further Notes

- The fingerprint walk is the same `scandir` data `union_library` already touches — a few thousand entries, seconds; at 30 s cadence it's noise.
- `import` moves each root `*.m3u8` into `.playlists/imports/` — that mutation itself changes the fingerprint, so the *next* cycle's `union_library` automatically prunes the now-dangling union link. No special-casing needed.
- First-run caveat: on the very first container start the state file doesn't exist, so any pre-existing root `*.m3u8`s will trigger one `import` (after `migrate` + `union`). That is correct behaviour (catch-up), not a bug — `import` merges against `imports/*.m3u8` references and is safe to re-run.
- If a third source tree is ever added (ADR 0004 forbids it without re-reading), the fingerprint's walk list must grow with it.
- `docker compose config` + a `MIGRATE_MODE=dry IMPORT_MODE=dry` boot is the manual smoke check for the service itself; the HTTP client and subprocess boundary get no unit tests, per repo convention.
