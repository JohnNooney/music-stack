# Cloudflare bypass proxy for Prowlarr — research

Research date: 2026-11-13. Sources: the official FlareSolverr repo (README, CHANGELOG,
Dockerfile, compose file, issues/discussions), the official Byparr repo (README, source,
releases, publish workflow), Prowlarr's own source code on `develop` and the Servarr
wiki, and the Docker Hub registry API.

> **TL;DR — Run the real FlareSolverr; keep Byparr as the fallback.** FlareSolverr is
> *not* dead — after a maintenance lull through 2024 it resumed regular releases and is
> at v3.5.2 (2026-09-12), which actively solves Cloudflare Turnstile challenges
> (§1). Its image publishes amd64+arm64 manifests; this Mac is Intel, so the amd64
> image runs natively — no Rosetta either way (§4).
> **Byparr** (`ghcr.io/thephaseless/byparr`) is the best-maintained alternative: it
> speaks the same `POST /v1` API Prowlarr expects, ships arm64 too, but only performs
> GET requests — indexers whose definitions POST through the proxy are out of scope for
> it (§2). Wire-up is one indexer proxy in Prowlarr: Settings → Indexers → "+",
> Host `http://flaresolverr.internal:8191`, and a **tag is mandatory** — a tag-less
> proxy is disabled in Prowlarr's code (`Enable => Tags.Any()`), and indexers without
> matching tags never touch it (§3). Caveats: Prowlarr re-fetches the page itself with
> the returned cookies+User-Agent, so the solver must share Prowlarr's egress IP; and
> none of FlareSolverr's CAPTCHA solver adapters currently work (§6).

---

## 1. FlareSolverr — current status: alive and releasing

**Repo:** https://github.com/FlareSolverr/FlareSolverr — 16.2k stars, MIT license,
not archived. "Proxy server to bypass Cloudflare protection."

- **It went quiet, then recovered.** There was a real maintenance gap: v3.3.21
  (2024-06-26) sat as the latest release for ~11 months while Cloudflare changed its
  challenge, prompting the "Still active?" discussion
  (https://github.com/FlareSolverr/FlareSolverr/discussions/1429, Jan 2025). Jackett
  maintainer `garfield69` noted on a Prowlarr issue in Mar 2025 that upstream was
  "falling behind" and pointed at community forks
  (https://github.com/Prowlarr/Prowlarr/issues/2358).
- **Releases resumed and continue.** Changelog
  (https://github.com/FlareSolverr/FlareSolverr/blob/master/CHANGELOG.md):
  v3.3.22–v3.3.25 in Jun 2025, v3.4.x through late 2025, then **v3.5.0 (2026-05-26)
  "Resolve turnstile captcha"** and **v3.5.2 (2026-09-12)** — latest release. Master
  branch has commits through 2026-10-24, including "Add small random jitter to
  turnstile key press timings" (#1797).
- **How it works** (README): Selenium + undetected-chromedriver launches Chrome per
  request, waits out the challenge, returns HTML + cookies + User-Agent.
  https://github.com/FlareSolverr/FlareSolverr/blob/master/README.md
- **API:** `POST {host}/v1` with `{"cmd": "request.get", "url": …, "maxTimeout": ms}`;
  also `request.post`, `sessions.create/list/destroy`. (README, Usage section.)
- **Env vars** (README, Environment variables): `LOG_LEVEL` (default `info`),
  `LOG_HTML`, `LOG_FILE`, `CAPTCHA_SOLVER` (none work — see §6), `TZ`, `LANG`,
  `HEADLESS`, `DISABLE_MEDIA`, `PROXY_URL`/`PROXY_USERNAME`/`PROXY_PASSWORD`,
  `PORT` (8191), `HOST`, `TEST_URL`, `PROMETHEUS_*`. **No `PUID`/`PGID`** — the image
  runs as a fixed `flaresolverr` user (`USER flaresolverr`, Dockerfile:54).
- **The 2024–25-era forks are stale now.** `21hsmw/flaresolverr:nodriver` (recommended
  by garfield69 in Mar 2025) last pushed 2025-03-04; `alexfozor/flaresolverr` was a PR
  test build. Both predate upstream's recovery — no reason to prefer them today.

## 2. Alternatives

### Byparr — `ghcr.io/thephaseless/byparr` (the credible one)

**Repo:** https://github.com/ThePhaseless/Byparr — 2.1k stars, GPL-3.0.

- **Actively maintained:** latest release **v3.1.1, 2026-11-05**; commits through
  2026-11-09. 707 commits total. (Releases page; `git` API `commits?per_page=3`.)
- **Engine:** v3 uses `invisible-playwright` + Playwright + `playwright-captcha`
  (`pyproject.toml` deps); the older v2 line used Camoufox. A different engine from
  FlareSolverr's undetected-chromedriver — a genuine fallback when one fails a site.
- **Speaks the FlareSolverr API:** `POST /v1` is served by `src/endpoints.py:59`;
  `src/models.py` documents `cmd` as "purely for compatibility with FlareSolverr",
  accepts `maxTimeout` in milliseconds "matching FlareSolverr's maxTimeout
  parameter", plus `blockMedia` / `returnOnlyCookies`. Response shape mirrors
  FlareSolverr (`solution{status,url,cookies,userAgent,headers,response}`).
- **GET only.** The model's own docstring: "currently only supports GET requests" —
  `/v1` always does `page.goto` (`endpoints.py:131`). Prowlarr issues
  `cmd: request.post` for form-urlencoded indexer requests (§3), so those indexers
  won't work through Byparr.
- **Env vars** (README): `HOST`, `PORT` (8191), `PROXY_SERVER`/`PROXY_USERNAME`/
  `PROXY_PASSWORD`, `BROWSER_LOCALE`, `BROWSER_TIMEZONE`, `OWUI_API_KEY`. No
  `PUID`/`PGID` (`USER 1000`, Dockerfile:59).
- **Runtime needs:** README recommends `shm_size: "1gb"` and
  `tmpfs: /tmp:exec,mode=1777,size=1G` — it "performs a *lot* of R/W operations on
  your disk". **Do not** tmpfs over `/cache` (holds the baked-in browser).
- **Startup quirk:** downloads a GeoIP database from GitHub before opening the port;
  the port staying closed means it isn't ready yet. If GitHub is unreachable this can
  take ~1 min. (README, Browser timezone section.)
- **Honest disclaimer in its own README:** "This software does not **guarantee**
  (only greatly increases the chance) that any challenge will be bypassed."

### Solverr — `ghcr.io/unseensnick/solverr` (emerging, tiny)

https://github.com/unseensnick/Solverr — 18 stars, GPL-3.0. Fuses FlareSolverr's
Chromium engine with Byparr's Camoufox engine, auto-falling back per site and
remembering which engine works per domain; same `/v1` API on 8191; suggests
`shm_size: 512mb`. Interesting idea, essentially unproven at this size — listed for
completeness, not recommended.

### FlareSolverr forks (`21hsmw`, `alexfozor`)

Workarounds from the 2024–25 upstream lull (§1); both stale. Superseded by upstream
v3.5.x.

## 3. How Prowlarr consumes it — verified in source

Sources: `Prowlarr/Prowlarr@develop`:
`src/NzbDrone.Core/IndexerProxies/FlareSolverr/FlareSolverr.cs`,
`FlareSolverrSettings.cs`, `IndexerProxyDefinition.cs`,
`src/NzbDrone.Core/Indexers/IndexerHttpClient.cs`, and
https://wiki.servarr.com/prowlarr/settings (Indexer Proxies section).

- **API shape:** Prowlarr POSTs `{Host}/v1` with `cmd: request.get` +
  `maxTimeout` (`FlareSolverr.cs`, `GenerateFlareSolverrRequest`). For POST indexer
  requests it sends `cmd: request.post` — but only for
  `application/x-www-form-urlencoded`; multipart/text-html POSTs throw
  "Unimplemented POST Content-Type". So *any* drop-in must implement `request.get`
  and ideally `request.post` + the `solution.cookies`/`solution.userAgent` response.
- **Lazy invocation:** the FlareSolverr proxy is only invoked *if and only if*
  Prowlarr's `CloudFlareDetectionService.IsCloudflareProtected(response)` trips on
  the normal response (`FlareSolverr.cs`, `PostResponse`; same claim on the wiki).
  Non-blocked indexers never touch it.
- **Session reuse:** after a solve, Prowlarr re-executes the request **itself** with
  the returned cookies and the returned `solution.userAgent` (cached per host and
  injected into later requests — `PostResponse`). The solver therefore has to share
  Prowlarr's egress IP; cf_clearance-type cookies are bound to IP + UA. Consequence:
  run the solver in this same compose network, and if Prowlarr ever goes through a
  VPN, the solver must egress through it too.
- **Settings:** `Host` (default `http://localhost:8191/`, required) and advanced
  `Request Timeout` (default **60 s**, valid 1–180 — passed as `maxTimeout` ms;
  `FlareSolverrSettings.cs`).
- **Tags are required, not optional.** `IndexerProxyDefinition.Enable =>
  Tags.Any()` — a proxy with no tags is disabled outright
  (`IndexerProxyDefinition.cs`). `IndexerHttpClient.GetProxies`: indexers with no
  tags skip proxies entirely; selection is `indexer.Tags ∩ proxy.Tags` non-empty;
  FlareSolverr sorts **last** so an HTTP/SOCKS proxy wins if both match
  (`IndexerHttpClient.cs:55-77`). Wiki agrees: "Proxies apply to all matching
  (same tag) indexers. If blank this proxy is disabled."
- **UI steps** (wiki, Indexer Proxies): Settings → Indexer Proxies → "+" → pick
  FlareSolverr → Name, Host (full URL incl. `http://` and port), Tags → save. Then
  edit each Cloudflare-blocked indexer and add the same tag.

## 4. Container requirements on this host (Docker Desktop, macOS x86_64 — Intel i9-9880H)

Verified 2026-11-13: `docker compose up` pulled the `linux/amd64` manifest natively
(`docker image inspect` → `linux/amd64`; `uname -m` in-container → `x86_64`); the
GHCR `:latest` index also carries `linux/arm64` for ARM machines.

| | FlareSolverr | Byparr |
|---|---|---|
| Image | `ghcr.io/flaresolverr/flaresolverr:latest` (Docker Hub mirror `flaresolverr/flaresolverr`) | `ghcr.io/thephaseless/byparr:latest` |
| Port | 8191 (+8192 opt. Prometheus) | 8191 |
| arm64? | **Yes** — README arch table lists `linux/arm64`; Docker Hub `latest` manifest has amd64/arm64/386/arm-v7 | **Yes** — publish workflow builds `linux/amd64,linux/arm64` matrix (`.github/workflows/docker-publish.yml:87`). README caveat: ARM support is lightly tested (author only has an Ampere VM) |
| User | fixed `flaresolverr` user | fixed uid 1000 |
| RAM/disk notes | browser per request = high memory churn; upstream recommends `tmpfs: /tmp:size=256M,mode=1777` to spare SSDs | `shm_size: "1gb"` + `tmpfs: /tmp … 1G` recommended for the same reason |
| Config dir | none needed (stateless; `/config` volume in upstream example is only for optional `LOG_FILE`) | none (stateless; `/cache` holds browser — leave it on the image) |
| Network needs | outbound to the indexers being solved | outbound to indexers **plus GitHub at startup** (GeoIP DB) — see §2 |

Neither image uses `PUID`/`PGID`/`UMASK` — that convention doesn't apply here.
Neither should ever be exposed to the internet (FlareSolverr README: "DO NOT expose
FlareSolverr to the internet, as it can be abused"); on the internal compose network
they're fine.

## 5. Recommended compose block

Matches this repo's conventions (`container_name`, `hostname:` + `*.internal`
network alias, `restart: unless-stopped`, `logging: json-file`, `${TZ}`). The solver
is stateless, so no `./flaresolverr:/config` volume — unlike the other apps it has no
config to persist. No `PUID`/`PGID` (§4). Add to `docker-compose.yml` after
`prowlarr`:

```yaml
  # FlareSolverr: solves Cloudflare challenges for Prowlarr indexers tagged to use it
  # (see docs/flaresolverr-research.md). Stateless — no config volume.
  # The image runs as a fixed flaresolverr user; PUID/PGID are not supported.
  flaresolverr:
    container_name: flaresolverr
    hostname: flaresolverr.internal
    networks:
      default:
        aliases:
          - flaresolverr.internal
    image: ghcr.io/flaresolverr/flaresolverr:latest
    restart: unless-stopped
    logging:
      driver: json-file
    ports:
      - "8191:8191"
    environment:
      - LOG_LEVEL=info   # set to debug when troubleshooting solves
      - TZ=${TZ}
    # Browser profiles are written per-request; RAM-backing spares the SSD.
    tmpfs:
      - /tmp:size=256M,mode=1777
```

Alternative (swap in if FlareSolverr can't clear a given indexer — different engine,
same API, same port; can't run both on host port 8191 without remapping, e.g.
`"8192:8191"` for a second one and a second Prowlarr proxy with its own tag):

```yaml
  byparr:
    container_name: byparr
    hostname: byparr.internal
    networks:
      default:
        aliases:
          - byparr.internal
    image: ghcr.io/thephaseless/byparr:latest
    restart: unless-stopped
    logging:
      driver: json-file
    ports:
      - "8191:8191"
    environment:
      - TZ=${TZ}
    shm_size: "1gb"
    tmpfs:
      - /tmp:exec,mode=1777,size=1G
    # /cache stays on the image — it holds the baked-in browser.
```

### Wiring it into Prowlarr (§3 for the why)

1. `docker compose up -d flaresolverr`; confirm `docker logs flaresolverr` shows it
   serving on 8191.
2. Prowlarr (http://localhost:9696) → **Settings → Indexers** → scroll to
   **Indexer Proxies** → "+" → **FlareSolverr**.
3. Name: `FlareSolverr`. **Host: `http://flaresolverr.internal:8191`**.
   **Tags: `flaresolverr`** (any string — but blank disables the proxy entirely).
   Leave Request Timeout at 60 s unless solves time out.
4. Save (disk icon). Then edit each Cloudflare-failing indexer → add tag
   `flaresolverr` → save. Untouched indexers never route through it.
5. Re-test a failing indexer; `docker logs -f flaresolverr` should show the solve.
   If `Test` inside the proxy settings passes, the URL is right — failures after
   that are per-indexer challenge problems, not wiring.

## 6. Caveats (all source-backed)

- **Cloudflare is a moving target.** v3.5.2 has open regressions on the tracker
  right now: a geolocation-permission alert breaking solves with HTTP 500
  (issue filed 2026-10-24), a `PermissionError` terminating the service process
  (2026-11-10), and a flagged old Chromium with KEV CVEs (2026-11-03) —
  https://github.com/FlareSolverr/FlareSolverr/issues. History shows solves break
  and get re-fixed release to release; the 2024 gap is the extreme example.
- **CAPTCHAs are not solved.** FlareSolverr's own README: "At this time none of the
  captcha solvers work." Sites that escalate to an interactive hCaptcha-style
  challenge will fail regardless of solver choice.
- **IP binding.** Prowlarr re-issues requests itself with the returned
  cookies+User-Agent (§3) — the solver must share Prowlarr's egress IP and the UA
  must match. Running it in this compose network satisfies that; routing Prowlarr
  through a VPN later means the solver must egress through the same VPN.
- **Tags gate everything.** Forget the tag on either side and the proxy silently
  does nothing (`Enable => Tags.Any()`; `IndexerHttpClient` skips tag-less
  indexers).
- **Some indexers just won't work.** Even with a working solver, Prowlarr
  maintainers treat persistently dead indexers as removal candidates
  (https://github.com/Prowlarr/Prowlarr/issues/2358) — solving Cloudflare doesn't
  fix a dead site.
- **Byparr-specific:** GET-only `/v1` (no `request.post`), light ARM testing,
  startup blocked on a GitHub download, and its README disclaims any guarantee.
- **Resource cost.** A browser is launched per challenged request — expect real CPU
  and RAM spikes on the Mac while indexers sync. The tmpfs/`shm_size` lines in §5
  are upstream-recommended mitigations, not optional tuning.

## Sources

- FlareSolverr repo: https://github.com/FlareSolverr/FlareSolverr
  - README: https://github.com/FlareSolverr/FlareSolverr/blob/master/README.md
  - CHANGELOG: https://github.com/FlareSolverr/FlareSolverr/blob/master/CHANGELOG.md
  - Dockerfile: https://github.com/FlareSolverr/FlareSolverr/blob/master/Dockerfile
  - compose: https://github.com/FlareSolverr/FlareSolverr/blob/master/docker-compose.yml
  - Releases: https://github.com/FlareSolverr/FlareSolverr/releases
  - "Still active?" discussion: https://github.com/FlareSolverr/FlareSolverr/discussions/1429
  - Issues: https://github.com/FlareSolverr/FlareSolverr/issues
  - Docker Hub tags API: https://hub.docker.com/v2/repositories/flaresolverr/flaresolverr/tags/latest
- Byparr repo: https://github.com/ThePhaseless/Byparr
  - README, `compose.yaml`, `pyproject.toml`, `src/endpoints.py`, `src/models.py`,
    `.github/workflows/docker-publish.yml`, Releases — all under that URL.
- Solverr: https://github.com/unseensnick/Solverr
- 21hsmw fork (stale): https://github.com/21hsmw/FlareSolverr
- Prowlarr source (`develop`):
  - `src/NzbDrone.Core/IndexerProxies/FlareSolverr/FlareSolverr.cs`
  - `src/NzbDrone.Core/IndexerProxies/FlareSolverr/FlareSolverrSettings.cs`
  - `src/NzbDrone.Core/IndexerProxies/IndexerProxyDefinition.cs`
  - `src/NzbDrone.Core/Indexers/IndexerHttpClient.cs`
- Servarr wiki: https://wiki.servarr.com/prowlarr/settings (Indexer Proxies)
- Prowlarr issue (indexer removal / FlareSolverr ecosystem comment):
  https://github.com/Prowlarr/Prowlarr/issues/2358
- This repo: `docker-compose.yml` (conventions), `docs/lidarr-stack.md`.
