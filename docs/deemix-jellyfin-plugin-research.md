# Could a Jellyfin plugin replace `reorganize_playlists`?

Research date: 2026-11. Server source inspected at `jellyfin/jellyfin` tag
[`v12.4`](https://github.com/jellyfin/jellyfin/releases/tag/v12.4) (commit
[`83d0d0e`](https://github.com/jellyfin/jellyfin/commit/83d0d0e7f76e23e2e085c8ff67d28b772d35967d)),
which is the version pinned in `docker-compose.yml`. Deemix side inspected at
[`bambanah/deemix`](https://github.com/bambanah/deemix) `main` — the source of the pinned image
`ghcr.io/bambanah/deemix:v4.8.0` (release
[`deemix-webui@4.8.0`](https://github.com/bambanah/deemix/releases/tag/deemix-webui%404.8.0)).

> **TL;DR — no existing integration, feasible but not worth building.**
> There is **no Deemix↔Jellyfin plugin** anywhere (GitHub search, awesome-jellyfin, the deemix repo
> itself). A Jellyfin plugin is a .NET assembly that runs *inside* the server process and gets the
> same internal services the REST controllers use — `IPlaylistManager`, `ILibraryManager`,
> scheduled tasks, post-scan hooks, item events, custom API controllers — so it could technically
> reproduce everything `reorganize_playlists` does, including filesystem moves on `/media`.
> But the trigger problem is weak (filesystem watching through Docker Desktop bind mounts is
> unreliable), the merge/dedup/git logic would have to be re-implemented in C#, the internal
> interfaces are not a stable API across Jellyfin releases, and the repo deliberately keeps the
> tool stdlib-only and testable via fakes. **Recommendation: keep the Python tool.** If automation
> is wanted later, a thin trigger (official Webhook plugin's `TaskCompleted`, a deemix WebSocket
> listener, or `launchd` polling) is much smaller than a plugin.

---

## 1. Does a Deemix–Jellyfin integration already exist?

**No.** Checked the obvious places:

- GitHub repository search `jellyfin deemix` returns two repos, neither a plugin:
  [`omerbustun/deemix-discord-bot`](https://github.com/omerbustun/deemix-discord-bot) (discontinued
  Discord bot that shelled out to Python deemix) and
  [`djsiete/dms`](https://github.com/djsiete/dms) (a docker-compose stack).
  ([search](https://github.com/search?q=jellyfin+deemix&type=repositories))
- GitHub repository search `jellyfin-plugin deezer` returns two metadata plugins, neither related
  to downloads or playlists:
  [`Druidblack/Jellyfin.Plugin.Deezer`](https://github.com/Druidblack/Jellyfin.Plugin.Deezer)
  ("Metadata and images for music artists and albums from Deezer" — a metadata provider only) and
  [`OMGrant/jellyfin-plugin-chaperone`](https://github.com/OMGrant/jellyfin-plugin-chaperone)
  (parental-rating metadata).
  ([search](https://github.com/search?q=jellyfin-plugin+deezer&type=repositories))
- The curated [awesome-jellyfin](https://github.com/awesome-jellyfin/awesome-jellyfin) list has no
  Deemix or Deezer entry; its playlist-related tools are things like
  [`Viperinius/jellyfin-plugin-spotify-import`](https://github.com/Viperinius/jellyfin-plugin-spotify-import)
  (Spotify→Jellyfin playlist import) and [`Playlifin`](https://github.com/awesome-jellyfin/awesome-jellyfin)
  (YouTube Music→Jellyfin).
- The bambanah/deemix monorepo contains only `deezer-sdk`, `deemix` (download engine), `webui`
  (Vue.js + Express) and `gui` (Electron) — no media-server integration code.
  ([repo README](https://github.com/bambanah/deemix))

### The Deemix ecosystem's own integrations

The closest existing work is all on the *Plex/Lidarr* side, not Jellyfin:

- [`m8tec/Deezync`](https://github.com/m8tec/Deezync) — syncs Deezer playlists to **Plex** and uses
  Deemix to download missing tracks. Nearest architectural analogue to this stack, wrong server.
- [`ta264/Lidarr.Plugin.Deemix`](https://github.com/ta264/Lidarr.Plugin.Deemix) — Deemix as a
  Lidarr indexer/downloader (and the
  [`lidarr-on-steroids`](https://github.com/DrMxrcy/lidarr-on-steroids) image bundling the two).
- Deemix itself has **no post-download hook, webhook or notification mechanism** — its extension
  surface is its own HTTP/WebSocket API (§4).

## 2. What a Jellyfin plugin can actually do

Jellyfin plugins are .NET assemblies (the template targets `net9.0` with the `Jellyfin.Controller` /
`Jellyfin.Model` packages) dropped into the server's plugin directory, loaded into the server
process, with an XML-backed configuration page via `IHasWebPages`.
([jellyfin-plugin-template README](https://github.com/jellyfin/jellyfin-plugin-template/),
[jellyfin.org plugin docs](https://jellyfin.org/docs/general/server/plugins/))

Because the plugin runs in-process, it gets constructor-injected access to every internal service
the REST API itself uses. Verified at `v12.4`:

### Lifecycle and scheduling

- **`IPluginServiceRegistrator`** — `RegisterServices(IServiceCollection, IServerApplicationHost)`
  adds plugin classes to Jellyfin's own dependency-injection container.
  ([`MediaBrowser.Controller/Plugins/IPluginServiceRegistrator.cs`](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Plugins/IPluginServiceRegistrator.cs))
- **`IHostedService`** — background services start/stop with the server. The spotify-import plugin
  registers one via `serviceCollection.AddHostedService<ServerEntrypoint>()`.
  ([`PluginServiceRegistrator.cs`](https://github.com/Viperinius/jellyfin-plugin-spotify-import/blob/master/Viperinius.Plugin.SpotifyImport/PluginServiceRegistrator.cs))
- **`IScheduledTask`** (`MediaBrowser.Model.Tasks`) — `ExecuteAsync(progress, ct)` plus
  `GetDefaultTriggers()`; tasks show up under Dashboard → Scheduled Tasks with interval/cron/manual
  triggers. The server collects **every DI-registered** `IScheduledTask`:
  `Resolve<ITaskManager>().AddTasks(GetExports<IScheduledTask>(false))`.
  ([`IScheduledTask.cs`](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Model/Tasks/IScheduledTask.cs),
  [`ApplicationHost.cs` L424](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/ApplicationHost.cs#L424))
  The spotify-import task injects `IPlaylistManager`, `ILibraryManager`, `IUserManager` directly.
  ([`SpotifyImportTask.cs`](https://github.com/Viperinius/jellyfin-plugin-spotify-import/blob/master/Viperinius.Plugin.SpotifyImport/Tasks/SpotifyImportTask.cs))
- **`ILibraryPostScanTask`** — `Run(progress, ct)` executed after each media-library scan; the
  server passes all registered instances into the `LibraryManager`. This maps *exactly* onto the
  tool's "scan, wait, then import" sequence: the import step could be a post-scan task.
  ([`ILibraryPostScanTask.cs`](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Library/ILibraryPostScanTask.cs),
  [`ApplicationHost.cs` L735](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/ApplicationHost.cs#L735))
- **Custom REST controllers** — any plugin assembly containing `ControllerBase` subclasses is added
  as an API application part, so the plugin can expose its own endpoints (e.g. a "run import now"
  button or a webhook receiver).
  ([`ApplicationHost.cs` `GetApiPluginAssemblies` L1010-1022](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/ApplicationHost.cs#L1010-L1022),
  [`Startup.cs` L73](https://github.com/jellyfin/jellyfin/blob/v12.4/Jellyfin.Server/Startup.cs#L73))

### Library and playlist internals

- **`ILibraryManager`** exposes `ItemAdded` / `ItemUpdated` / `ItemRemoved` events,
  `IsScanRunning`, `FindByPath(path, isFolder)`, `GetItemList(InternalItemsQuery)`,
  `QueueLibraryScan()` and `ValidateMediaLibrary(progress, ct)` — i.e. item lookup by path and
  scan triggering without going through HTTP.
  ([`ILibraryManager.cs` L36-46, 54, 122, 168, 669, 828](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Library/ILibraryManager.cs))
- **`IPlaylistManager`** — everything the Python client does over REST is one interface:
  `CreatePlaylist(PlaylistCreationRequest)`, `AddItemToPlaylistAsync(playlistId, itemIds, position,
  userId)` (append at end = `position: null`), `RemoveItemFromPlaylistAsync(playlistId, entryIds)`,
  `GetPlaylistForUser`, `GetPlaylists(userId)`, `MoveItemAsync`, `SavePlaylistFile`.
  ([`IPlaylistManager.cs`](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Playlists/IPlaylistManager.cs))
- The REST `PlaylistsController` is a thin wrapper over exactly this interface
  (`POST /Playlists`, `POST/GET/DELETE /Playlists/{playlistId}/Items`,
  `POST /Playlists/{id}/Items/{itemId}/Move/{newIndex}`), so API-level and in-process playlist
  behaviour are identical.
  ([`PlaylistsController.cs`](https://github.com/jellyfin/jellyfin/blob/v12.4/Jellyfin.Api/Controllers/PlaylistsController.cs))
- The remaining endpoints the tool uses also exist at v12.4: `POST /Library/Refresh`
  ([`LibraryController.cs` L337](https://github.com/jellyfin/jellyfin/blob/v12.4/Jellyfin.Api/Controllers/LibraryController.cs#L337)),
  `GET /ScheduledTasks` for scan state
  ([`ScheduledTasksController.cs` L38](https://github.com/jellyfin/jellyfin/blob/v12.4/Jellyfin.Api/Controllers/ScheduledTasksController.cs#L38)),
  `POST /Items/{itemId}/Images/{imageType}` for cover upload
  ([`ImageController.cs` L352](https://github.com/jellyfin/jellyfin/blob/v12.4/Jellyfin.Api/Controllers/ImageController.cs#L352)),
  plus `GET /Items` and `GET /Users` (`ItemsController.cs`, `UserController.cs` in the same
  [controllers directory](https://github.com/jellyfin/jellyfin/tree/v12.4/Jellyfin.Api/Controllers)).
- Filesystem access is trivial — plugin code is ordinary .NET; `System.IO` plus `IFileSystem` cover
  all moves/copies on `/media`, and `FileSystemWatcher` is available in-process (but see §3 on
  reliability inside this container).

### Precedent: this architecture already exists and works

[`Viperinius/jellyfin-plugin-spotify-import`](https://github.com/Viperinius/jellyfin-plugin-spotify-import)
is essentially "the same tool for Spotify": a scheduled task (`Tasks/SpotifyImportTask.cs`), an
`IHostedService` entrypoint (`ServerEntrypoint.cs`), custom API controllers (`Api/*Controller.cs`),
a configuration page, and playlist create/update through `IPlaylistManager`/`ILibraryManager`
(`Sync/PlaylistSync.cs`, which also does ISRC-based matching). It demonstrates that the whole shape
of `reorganize_playlists import` fits inside the plugin model.

## 3. The trigger problem: how does the plugin know Deemix finished?

The tool's contract is "after a Deemix session, scan then import". Options for a plugin:

1. **`ILibraryPostScanTask` (best fit).** New audio files are useless until scanned anyway, so
   "after every library scan, look for root `*.m3u8` and import" exactly reproduces the current
   workflow with zero polling.
   ([`ILibraryPostScanTask.cs`](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Library/ILibraryPostScanTask.cs))
2. **Scheduled-task polling** (`IScheduledTask` on a short interval): poll `/media` for new
   `*.m3u8`, then `QueueLibraryScan()`. Simple, always works, adds latency.
3. **`ILibraryManager.ItemAdded` events** fire per resolved item during scans — could notice the
   `*.m3u8` arriving, but still needs the "scan finished" boundary that `ILibraryPostScanTask`
   provides.
   ([`ILibraryManager.cs` L36](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Library/ILibraryManager.cs#L36))
4. **`FileSystemWatcher` on `/media`: unreliable here.** Events must propagate through Docker
   Desktop's host↔VM filesystem sharing (VirtioFS/osxfs) — historically lossy: e.g. missing
   `DELETE` events under VirtioFS and other documented gaps.
   ([docker/for-mac#7246](https://github.com/docker/for-mac/issues/7246),
   [osxfs file-system-events doc](https://github.com/bseib/docker.github.io/blob/master/docker-for-mac/osxfs.md))
   Worse, the writes originate in a *different* container (deemix) sharing the same bind mount —
   inotify propagation for cross-container host-mount writes is not guaranteed. Polling or the
   post-scan hook are the dependable options.
5. **Listen to Deemix's own WebSocket** (§4) from a hosted service — event-driven, but adds a
   long-lived socket to a fragile edge; still needs the subsequent scan before items exist.

`/media` inside the container is sufficient for all of this — it is the same bind-mounted library
root the Python tool sees as `~/Music/Deemix`
([`docker-compose.yml`](../docker-compose.yml)).

## 4. The Deemix side

- The pinned image is the **webui** package of the bambanah/deemix monorepo — TypeScript/Node,
  **not** the original Python `deemix`/`deemix-pyweb`. The download engine is `packages/deemix`
  over a `deezer-sdk` (JS) Deezer wrapper.
  ([repo README](https://github.com/bambanah/deemix),
  [release tag `deemix-webui@4.8.0`](https://github.com/bambanah/deemix/releases/tag/deemix-webui%404.8.0))
- **REST API** mounted at `*/api/...` (any base path): `GET /api/getQueue` returns queue state,
  `POST /api/addToQueue` enqueues downloads, plus `saveSettings`, `removeFinishedDownloads`,
  `retryDownload`, `getSettings`, `getUserPlaylists`, search/analyze endpoints.
  ([`routes/api/register.ts`](https://github.com/bambanah/deemix/blob/main/packages/webui/src/server/routes/api/register.ts),
  [`get/getQueue.ts`](https://github.com/bambanah/deemix/blob/main/packages/webui/src/server/routes/api/get/getQueue.ts),
  [`post/addToQueue.ts`](https://github.com/bambanah/deemix/blob/main/packages/webui/src/server/routes/api/post/addToQueue.ts))
- **WebSocket** (`ws` package): every `listener.send(key, data)` in the queue/downloader is
  broadcast to all connected clients as `{key, data}` JSON. Emitted keys include `addedToQueue`,
  `startDownload`, **`finishDownload`**, `updateQueue`, `downloadWarn`, `currentItemCancelled`,
  `removedFromQueue`, `removedFinishedDownloads`. Queue entries carry `status` of
  `inQueue`/`downloading`/`completed`/`withErrors`/`failed`.
  ([`websocket/index.ts`](https://github.com/bambanah/deemix/blob/main/packages/webui/src/server/websocket/index.ts),
  [`main.ts` L47-57](https://github.com/bambanah/deemix/blob/main/packages/webui/src/server/main.ts),
  [`deemixApp.ts` L336-349](https://github.com/bambanah/deemix/blob/main/packages/webui/src/server/deemixApp.ts),
  [`downloader.ts` L146](https://github.com/bambanah/deemix/blob/main/packages/deemix/src/downloader.ts))
- **`DEEMIX_SINGLE_USER=true`** loads credentials at startup and is what the docker image expects;
  the multi-user path is express-session based.
  ([`main.ts` L34-44](https://github.com/bambanah/deemix/blob/main/packages/webui/src/server/main.ts),
  [README docker section](https://github.com/bambanah/deemix))
- The m3u8 playlist-file behaviour the tool relies on is a Deemix setting:
  `createM3U8File`, `playlistFilenameTemplate`, `createStructurePlaylist`, `createPlaylistFolder`,
  `playlistTracknameTemplate`, `savePlaylistAsCompilation` are all fields of
  [`packages/deemix/src/types/Settings.ts`](https://github.com/bambanah/deemix/blob/main/packages/deemix/src/types/Settings.ts).
- **No post-download hook/notification exists** — the WebSocket and queue API are the only
  signalling surface, and they are good enough (a `finishDownload` event plus `getQueue` polling).

## 5. Feasibility assessment

Everything `reorganize_playlists` does maps to something a plugin can do:

| Tool function | Plugin equivalent |
|---|---|
| Scan + wait (`/Library/Refresh`, `/ScheduledTasks`) | `QueueLibraryScan()` / `ValidateMediaLibrary()` / `ILibraryPostScanTask` / `IsScanRunning` |
| Parse `.m3u8`, match by path (`/Items?Fields=Path`) | `FindByPath` / `GetItemList(InternalItemsQuery)`; PlaylistsNET is already bundled in the server ([`PlaylistManager.cs`](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/Playlists/PlaylistManager.cs)) |
| Create/append/remove/list playlists | `IPlaylistManager` — same calls the REST controller makes |
| Cover upload | `IProviderManager`/internal image save (REST equivalent exists at [`ImageController.cs` L352](https://github.com/jellyfin/jellyfin/blob/v12.4/Jellyfin.Api/Controllers/ImageController.cs#L352)) |
| Filesystem ops, dedupe, `.artifacts`, `.playlists` | `System.IO` on `/media` |
| Exports + git commit | file writes are trivial; **but the runtime image has no `git`** — the final Docker stage is `debian-slim` + the `jellyfin-server` package + GPU/media libs; `git` is installed only in the web-build stage. A plugin would need a bundled LibGit2Sharp NuGet package instead of shelling out. ([`jellyfin-packaging/docker/Dockerfile`](https://github.com/jellyfin/jellyfin-packaging/blob/master/docker/Dockerfile)) |
| Deezer lookups for Deemix paths (migrate) | `HttpClient` to `api.deezer.com` — works, but the whole `deemix.py`/`deezer.py` template + cache logic must be re-implemented in C# |
| Trigger | `ILibraryPostScanTask` (best) or `IScheduledTask` polling; `FileSystemWatcher` unreliable through the Docker Desktop mount (§3) |

### Pros of a plugin

- **No HTTP round-trip, no API key** — internal services instead of `JELLYFIN_API_KEY`.
- **Automatic timing** — post-scan task removes the manual `python3 -m reorganize_playlists import`
  step entirely.
- Single deployment unit inside the already-pinned Jellyfin container.
- Proven shape — the spotify-import plugin does playlist import this way today.

### Cons

- **Rewrite everything in C#/.NET**: m3u8 parse + three-way merge, ISRC-first song identity and
  canonical-copy dedupe, tag parsing (the stdlib FLAC/MP3 readers in `tags.py`), Deemix-path
  templating + Deezer lookups, artifacts/exports/git (LibGit2Sharp), the manifest/rollback design.
- **The internal interfaces are not a stable API.** `IPlaylistManager`, `ILibraryManager`, the DI
  model, and even the playlist data model change between Jellyfin majors — the repo already pins
  the image and re-verifies internals per release (`README.md` upgrade notes,
  [`jellyfin-music-metadata-research.md`](jellyfin-music-metadata-research.md)). A plugin hard-codes
  those internals into a binary that can fail to load on upgrade; the Python client only touches
  the versioned HTTP API.
- **Distribution/runtime friction**: build a DLL per Jellyfin version (net9.0 + matching
  `Jellyfin.Controller` package), deploy into `config/plugins/`, restart the container. The tool
  today is stdlib-only Python that runs anywhere with `python3`.
- **Testability regresses**: the repo's seam is `main(argv, deezer=FakeDeezer,
  jellyfin=FakeJellyfin)` against a real temp library (AGENTS.md). A plugin's seams are Jellyfin's
  internal services — unit-testable in principle (mock `IPlaylistManager`), but the file+scan
  integration can no longer be exercised without a running server or heavy mocks.
- **Blast radius**: a bug in playlist/scan logic runs inside the media server process rather than
  in a disposable CLI. The tool's "dry run by default" discipline is easy to keep in a CLI and
  harder to expose in a scheduled task.
- The git-commit requirement forces a native dependency (LibGit2Sharp) into the plugin anyway —
  the image cannot run `git`
  ([Dockerfile](https://github.com/jellyfin/jellyfin-packaging/blob/master/docker/Dockerfile)).

### Alternatives that keep the Python tool

- **Official Webhook plugin** ([`jellyfin/jellyfin-plugin-webhook`](https://github.com/jellyfin/jellyfin-plugin-webhook))
  already emits `ItemAdded`, `ItemDeleted` and **`TaskCompleted`** notifications to generic HTTP
  endpoints — a `TaskCompleted` webhook on `RefreshLibrary` could POST to a tiny endpoint that
  runs the import on the host (the plugin runs inside the container; the Python tool runs on the
  host, so the trigger must be HTTP).
- **Deemix WebSocket listener**: a few lines of host-side code (or `websocat` + a script) watching
  for `finishDownload`/empty-queue on `ws://localhost:6595`, then invoking the CLI — event-driven
  with no Jellyfin changes at all.
- **`launchd`/cron polling** for new root `*.m3u8` — the dumb option that already matches how the
  library is used.
- **`docker exec deemix deemix <link>`** is documented for queueing downloads from the host —
  any automation could chain the download command with the import command.
  ([README docker section](https://github.com/bambanah/deemix))

## Verdict

**No existing Deemix–Jellyfin plugin exists** — the nearest analogues are Plex (Deezync), Lidarr
(Lidarr.Plugin.Deemix), and Spotify→Jellyfin (jellyfin-plugin-spotify-import).

**Building one is feasible** — `IPlaylistManager`, `ILibraryManager`, `IScheduledTask`,
`ILibraryPostScanTask`, DI service registration and plugin API controllers (all verified at
`v12.4`) cover every capability the tool needs, and `/media` inside the container is the same
library the tool manages. The playlist-import core even has a working open-source precedent
(jellyfin-plugin-spotify-import).

**It is not worth it for this stack.** The tool's value is in its merge/dedup/rollback/git logic
and its stdlib-only testability — all of which would be rewritten in C# against unstable internal
interfaces, version-locked to each Jellyfin release, deployed as a binary plugin, and run inside
the server process. The only real gain is removing the manual `import` step, and that gain is
achievable with far less code: a `finishDownload`/empty-queue listener on Deemix's WebSocket, a
Webhook-plugin `TaskCompleted` trigger, or plain polling on the host. If that automation ever gets
built, the Python tool stays the implementation — the trigger is the only new piece.
