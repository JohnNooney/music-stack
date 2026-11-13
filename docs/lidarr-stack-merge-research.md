# Merging `lidarr-stack` into this repo without leaking secrets — research

Research date: 2026-11-13. Sources: the two working trees (`/Users/john/Docker/jellyfin`,
published at `github.com/JohnNooney/music-stack`; `/Users/john/Docker/lidarr-stack`, local-only,
3 commits, no remote), the Docker Compose spec docs, and official docs for Lidarr/Prowlarr
(hotio images), slskd, Soularr and linuxserver Transmission. Secret values are **never**
reproduced below — secrets are described by file, key name and line only.

> **TL;DR — Bring files over fresh; do not merge git history.** `lidarr-stack` committed
> `soularr/config.ini` in its initial commit with **live API keys inside** (§1.1): the real
> Lidarr `ApiKey` and the slskd API key that still match the values in the untracked
> `lidarr/config.xml` and `slskd/slskd.yml` on disk. The repo was never pushed, so nothing is
> exposed yet — but merging history into this public repo would publish them permanently.
> Everything else is in good shape: all other secret-bearing files in lidarr-stack are already
> gitignored, and this repo's own history is clean (§2). Recommended shape: **one
> `docker-compose.yml`** with all seven services (§5), **one `.env`** at the root serving both
> the tools and compose interpolation (§6), gitignore every app config dir and publish
> `*.example` templates for `soularr/config.ini` and `slskd/slskd.yml` (§7).

---

## 1. Secrets inventory — `lidarr-stack`

Tracked files (`git ls-files`): `.gitignore`, `README.md`, `docker-compose.yaml`,
`soularr/config.ini`. Everything else (`lidarr/`, `prowlarr/`, `slskd/`, `transmission/`,
`soularr/*` except `config.ini`, `.env`, `data/`) is gitignored
(`lidarr-stack/.gitignore:1-7`).

### 1.1 Committed secrets (in HEAD *and* history)

`git log --all --oneline -- soularr/config.ini` shows it was added once, in `acfca62`
("Initial commit"), and never modified since. The committed file contains:

- `soularr/config.ini:2` — `[Lidarr] api_key`. The committed value **is identical to the live
  key** in `lidarr/config.xml:7` (`<ApiKey>`). Confirmed via `git log --all -p` (diff line
  `+api_key = …`) — the same 32-hex-char value appears in both places.
- `soularr/config.ini:7` — `[Slskd] api_key`. Identical to the live key in
  `slskd/slskd.yml:144` (`web.api_keys.my_api_key.key`).
- Non-secret-but-local values in the same file: `host_url` (`:3`, `:8`) and `download_dir`
  (`:5`, `:10`) for both sections — fine to publish.

Working tree is clean (`git status`), so the keys sit in HEAD, not just history. `git log
--all -p` found **no other secret values** in history — the README diffs mention key *names*
only (`README.md` setup steps), and the Soulseek/Prowlarr/web-UI credentials below never
entered the repo because their files were gitignored from the start.

### 1.2 Untracked secrets on disk (gitignored — safe, but must stay ignored)

| File | Secret | Location |
|---|---|---|
| `lidarr/config.xml` | `<ApiKey>` (runtime-generated) | line 7 |
| `lidarr/lidarr.db` | SQLite: download-client creds, notification connections, root config | binary |
| `lidarr/asp/key-*.xml` | ASP.NET Data Protection key ring (encrypts secrets stored in the db) | `lidarr/asp/` |
| `prowlarr/config.xml` | `<ApiKey>` (runtime-generated) | line 7 |
| `prowlarr/prowlarr.db` | SQLite: indexer credentials, synced app (Lidarr) API key | binary |
| `prowlarr/asp/key-*.xml` | Data Protection key ring | `prowlarr/asp/` |
| `slskd/slskd.yml` | `web.authentication.username`/`password` (**plaintext**) | lines 135–138 |
| `slskd/slskd.yml` | `web.api_keys.my_api_key.key` | lines 142–144 |
| `slskd/slskd.yml` | `soulseek.username`/`password` (**plaintext Soulseek account**) | lines 183–187 |
| `slskd/slskd.yml.bak` | backup copy of the same file | whole file |
| `transmission/settings.json` | `rpc-password` — stored **hashed** (`{…}`, 49 chars); `rpc-username` is empty and `rpc-authentication-required` is `false` | `transmission/settings.json` |
| `.env` | nothing secret — only `DATA_DIR`, `PUID`, `PGID`, `TZ` | whole file |
| `soularr/*.log*`, `failed_imports.json` | runtime state; logs may echo config | `soularr/` |

`docker-compose.yaml` itself is clean: all per-host values come from `${DATA_DIR}`,
`${PUID}`, `${PGID}`, `${TZ}` (`docker-compose.yaml:16-19,22,38-41,44,62-64,70,86-89,93-94,112,116,119-121`).
One hardcoded host path: `/Users/john/Music/Deemix:/deemix:ro` (`docker-compose.yaml:122`) —
a path, not a secret, but still user-specific; it matches this repo's existing `/Lidarr` and
`/Deemix` bind-mount style (`docker-compose.yml:20-27`).

## 2. Secrets inventory — `jellyfin` (this repo)

Already clean; the merge only needs to extend the pattern.

- `.env` is untracked; only `.env.example` is committed (`git ls-files`). `.env` keys:
  `JELLYFIN_URL`, `JELLYFIN_API_KEY`, `JELLYFIN_USER`, `JELLYFIN_MEDIA_ROOT` — same set as
  `.env.example` with the API key left blank there.
- `.gitignore` ignores `.env`, `cache/`, `/config/*` (whitelisting `config/config/`,
  `config/root/`, `config/plugins/configurations/`) and `/deemix-config/*` (whitelisting
  `config.json` and `config.json.before-structure-playlist`) — `.gitignore:1-11`.
- `deemix-config/login.json` holds the Deezer `arl` (single key in the file) — untracked,
  confirmed by `git check-ignore`. `deemix-config/config.json` is tracked and contains only
  path/name templates — no credential fields exist in it.
- Tracked Jellyfin XMLs contain empty credential placeholders only:
  `config/config/network.xml:6-7` (`CertificatePath`, `CertificatePassword` — both empty) and
  `config/plugins/configurations/Jellyfin.Plugin.Tmdb.xml:3` (`TmdbApiKey` — empty).
- `git log --all -p` over this repo found no secret values; `.env` and `login.json` were
  never tracked.
- `docker-compose.yml` uses **no** `${VAR}` interpolation today — `user: 501:501` and
  `PUID=501/PGID=501` are hardcoded (`docker-compose.yml:8,42-43`), and the `.env` is read by
  `reorganize_playlists`, not by compose.

## 3. Compose mechanics (official docs)

Facts that constrain the merge shape:

- **`.env` at the project directory is auto-loaded for `${VAR}` interpolation** in the
  Compose file. When `--env-file` is not passed, Compose loads a `.env` from the project
  directory (the dir of the first `-f` file, or `--project-directory`, or PWD).
  https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/
- **One `.env` serves a whole project** — so a single root `.env` can feed interpolation for
  all services of a merged compose file, while *also* being the file `reorganize_playlists`
  reads. No conflict: key names don't overlap (`JELLYFIN_*` vs `DATA_DIR`/`PUID`/`PGID`/`TZ`).
- **`env_file:` per-service** injects vars into containers at run time (different mechanism
  from interpolation). It takes a list, is processed top-down, and supports a mapping form
  with `required:` — "The `required` attribute defaults to `true`. When `required` is set to
  `false` and the `.env` file is missing, Compose silently ignores the entry." Relative
  `env_file` paths resolve from the Compose file's parent folder.
  https://docs.docker.com/reference/compose-file/services/#env_file
- **`-f` merge**: relative paths (volumes, `env_file`, build contexts) in *all* files resolve
  relative to the **base** file (first `-f`). "If you need each Compose file's paths to
  resolve relative to its own location, use the `include` … mechanism."
  https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/
- **`include:`**: each included file "loads as an individual Compose application model, with
  its own project directory, in order to resolve relative paths", and all resources are then
  copied into the current model — so `./lidarr:/config` inside an included file still means
  "next to that file". Conflicting resource names across files are an error.
  https://docs.docker.com/compose/how-tos/multiple-compose-files/include/

## 4. Per-app secret surface and env-var support

| App (image in `lidarr-stack/docker-compose.yaml`) | Where secrets live | Env-var config? | Source |
|---|---|---|---|
| **Lidarr** (`ghcr.io/hotio/lidarr:latest`, :31) | `config.xml` `<ApiKey>` generated on first run; creds for download clients/indexers in `lidarr.db` | hotio image exposes only `PUID`/`PGID`/`UMASK`/`TZ`/`WEBUI_PORTS` — no app-config env vars | https://hotio.dev/containers/lidarr/ |
| **Prowlarr** (`ghcr.io/hotio/prowlarr:latest`, :9) | same pattern: `config.xml` `<ApiKey>`, indexer creds in `prowlarr.db` | same — no env config | https://hotio.dev/containers/prowlarr/ |
| **slskd** (`slskd/slskd`, :104) | `slskd.yml`: soulseek creds, web UI creds, API keys (§1.2) | **Yes.** Config hierarchy `Defaults < Env vars < YAML < CLI < runtime overlay`; every env var is `SLSKD_`-prefixed: `SLSKD_SLSK_USERNAME`/`SLSKD_SLSK_PASSWORD` (soulseek), `SLSKD_USERNAME`/`SLSKD_PASSWORD` (web UI), `SLSKD_API_KEY` (primary API key), `SLSKD_JWT_KEY` | https://github.com/slskd/slskd/blob/master/docs/config.md |
| **Soularr** (`mrusse08/soularr:latest`, :79) | `config.ini` `[Lidarr].api_key`, `[Slskd].api_key` — mounted at `/data` | **No** for API keys — the only documented env vars are `SCRIPT_INTERVAL`, `WEBUI_ENABLED`, `WEBUI_PORT`; config file must be at `/data` | https://github.com/mrusse/soularr |
| **Transmission** (`lscr.io/linuxserver/transmission:latest`, :53) | `settings.json` `rpc-username`/`rpc-password` (hash); currently auth disabled | Partial: `USER`, `PASS`, `WHITELIST`, `HOST_WHITELIST`, `PEERPORT` env vars; image docs warn *not* to edit user/pass in `settings.json` directly | https://docs.linuxserver.io/images/docker-transmission/ |

Implication: "all secrets via `.env`" is achievable **only for slskd and Transmission**.
Soularr has no env support, so its `config.ini` must remain a real untracked file (a tracked
`config.ini.example` documents the shape). Lidarr/Prowlarr API keys are runtime-generated
inside ignored config dirs — they never enter `.env`; Soularr's copy of them lives in the
untracked `config.ini` as today (the bug is only that it was *tracked*).

Note: `SLSKD_REMOTE_CONFIGURATION=true` (`docker-compose.yaml:115`) means slskd's web UI can
read/edit the full YAML — including any secrets in it. Keeping soulseek creds out of
`slskd.yml` and in env vars reduces what remote config exposes, but env values are still
readable via the options API; the existing README warning stands.

## 5. Recommended merge shape

**Bring files over fresh — do not merge `lidarr-stack` history** (see §8), then:

### Recommended: Option A — one `docker-compose.yml`, config dirs at repo root

Append the five services from `lidarr-stack/docker-compose.yaml` into this repo's
`docker-compose.yml`, unchanged except:

- keep the `./lidarr`, `./prowlarr`, `./slskd`, `./soularr`, `./transmission` bind mounts
  verbatim (paths still resolve — same dir);
- optionally switch `user: 501:501` / `PUID=501` of jellyfin+deemix to `${PUID}`/`${PGID}`
  for one source of truth (jellyfin repo `.env` currently lacks them);
- optionally move the two hardcoded host binds (`/Users/john/Music/Deemix`,
  `…/Lidarr`, `…/Jellyfin`) into `${VARS}` — nice-to-have, not required.

Why one file: the repo's README presents one `docker compose up -d` stack; all services
share one default network so `*.internal` aliases keep working; no port collisions (8096,
7359/udp, 6595 vs 8686, 9696, 9091, 51413, 8265, 5030/5031/50300); per-stack control is still
available via `docker compose up -d lidarr prowlarr …` or `profiles:` if ever wanted.

### Alternative: Option B — `include:` a second file

`docker-compose.yml` gains `include: [lidarr.compose.yaml]` (kept at root or under a
subdir). Each file keeps its own project dir for relative paths (§3). *Tradeoff:* a second
file to discover; `include` rejects same-named resources, so accidental name overlap errors
out; no real isolation gained since one `.env` and one project serve both anyway.

### Alternative: Option C — two files + `-f` merge

`docker compose -f docker-compose.yml -f lidarr.compose.yaml up -d`. *Rejected:* every
command needs flags or `COMPOSE_FILE`; relative paths all re-root to the base file (§3) —
strictly worse than `include` here.

### Alternative: Option D — keep two projects

Violates the stated goal (one folder/repo, one stack). Rejected.

## 6. `.env` / `.env.example` strategy

One `.env` at repo root (already ignored, already read by `reorganize_playlists`). Merged
key set:

```dotenv
# existing — tools
JELLYFIN_URL=…            JELLYFIN_API_KEY=…
JELLYFIN_USER=…           JELLYFIN_MEDIA_ROOT=…
# new — compose interpolation (from lidarr-stack/.env)
DATA_DIR=/path/to/media-root    # currently ~/Music/Lidarr on this host
PUID=…                    PGID=…                  TZ=…
# new — slskd secrets via env (slskd reads SLSKD_* directly)
SLSKD_SLSK_USERNAME=…     SLSKD_SLSK_PASSWORD=…
SLSKD_USERNAME=…          SLSKD_PASSWORD=…
SLSKD_API_KEY=…
# optional — transmission RPC auth (currently disabled; USER/PASS commented out)
TRANSMISSION_USER=…       TRANSMISSION_PASS=…
```

`.env.example` gets the same keys with empty/placeholder values and comments (matching the
existing style of header-comment + key). The slskd service's `environment:` block then lists
`- SLSKD_SLSK_USERNAME=${SLSKD_SLSK_USERNAME}` etc., and `transmission` can uncomment
`- USER=${TRANSMISSION_USER}` / `- PASS=${TRANSMISSION_PASS}` when auth is wanted.

`env_file: .env` per-service is *not* needed — `environment:` + interpolation covers it, and
`env_file` would inject the Jellyfin API key into every container unnecessarily. If it is
ever used, the `required: false` form (§3) avoids hard failures on fresh clones.

Caveat to document: `SLSKD_API_KEY` set via env defines the *primary* API key; the existing
named key in `slskd.yml` (`web.api_keys.my_api_key`) is what Soularr's `config.ini` uses —
keep them in sync or point Soularr at the env-defined one.

## 7. `.gitignore` plan

Add to this repo's `.gitignore`, following the existing ignore-everything/whitelist-templates
convention (`.gitignore:1-11`):

```gitignore
# Lidarr stack app configs: runtime state + secrets; only *.example templates tracked
/lidarr/*
/prowlarr/*
/slskd/*
/transmission/*
/soularr/*
!/soularr/config.ini.example
!/slskd/slskd.yml.example
!/transmission/settings.json.example   # optional; currently carries a leftover rpc-password hash
```

Critical change vs lidarr-stack's `.gitignore:7` (`!soularr/config.ini`): **do not
reinstate that whitelist** — it is what let live keys be committed.

Publishable templates:

- `soularr/config.ini.example` — current `config.ini` with `api_key`/`host_url` placeholders
  (`api_key = ` empty, `host_url = http://lidarr.internal:8686` etc. are non-secret).
- `slskd/slskd.yml.example` — non-secret sections only (directories, shares, transfer
  limits); `web.authentication` and `soulseek` creds left for env vars (§4). Note slskd
  copies `/config/slskd.example.yml` itself on first run if absent (slskd config docs), so
  the template is documentation, not required.
- Optionally a committed `config.xml` template for lidarr/prowlarr is *not* useful — the app
  generates it with its own ApiKey.

README: port `lidarr-stack/README.md` §Setup steps 3–7 into this repo's README (or
`docs/lidarr-stack.md`), updating paths (`../lidarr-stack` → same repo) and noting the
`config.ini` copy step.

## 8. Git-history risk assessment

- `lidarr-stack` is local-only (no remote, `git remote -v` empty), 3 commits. The only
  secret material in its history is the `soularr/config.ini` blob from `acfca62` (§1.1):
  Lidarr API key + slskd API key, both still live.
- Any history-preserving merge (`git subtree`, `git merge --allow-unrelated-histories`,
  rebase-and-push) would carry that blob into the **public** repo — GitHub keeps it
  reachable by commit SHA even if a later commit deletes the file.
- **Recommendation: copy files fresh** (one "Import lidarr-stack services" commit). Nothing
  of value is lost: 3 commits of README/compose/gitignore history.
- Key rotation is **optional hardening**, not strictly required — the keys never left this
  machine (local loopback API keys). If history is ever merged or the machine is shared,
  rotate the Lidarr and slskd API keys first.

## 9. Open questions

1. Keep `transmission`+`prowlarr`? The README itself notes they're removable
   (`lidarr-stack/README.md:199-200`) — the Soulseek path doesn't need them. Merge cost is
   low either way; decide before writing the README section.
2. Rename config dirs (`lidarr/` → `lidarr-config/` etc.) for consistency with
   `deemix-config/`? Keeps names meaningful vs. extra churn on the compose/README text.
3. Move jellyfin/deemix's hardcoded uid (`501:501`) and host binds onto `${PUID}`/`DATA_DIR`
   style vars, unifying all seven services under the same env scheme?
4. slskd `SLSKD_REMOTE_CONFIGURATION=true` — keep once secrets move to env, or drop to
   `false` (README already recommends `false` before internet exposure)?
5. Should the merged repo's `.env.example` document the rotation procedure for the API keys
   Soularr duplicates (Lidarr key + slskd key), since they live in two places
   (`config.xml`/`slskd.yml` + `soularr/config.ini`)?

## Sources

- This repo: `docker-compose.yml`, `.env`, `.env.example`, `.gitignore`, `deemix-config/`,
  `config/`, `README.md`, `docs/adr/0004-…`, `docs/specs/0003-…` — all `file:line` cites above.
- `lidarr-stack/`: `docker-compose.yaml`, `.gitignore`, `soularr/config.ini`,
  `lidarr/config.xml`, `prowlarr/config.xml`, `slskd/slskd.yml`,
  `transmission/settings.json`, `README.md` + `git log --all -p` — `file:line` cites above.
- Compose spec/docs:
  - https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/
  - https://docs.docker.com/reference/compose-file/services/#env_file
  - https://docs.docker.com/compose/how-tos/multiple-compose-files/include/
  - https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/
- App/image docs:
  - https://github.com/slskd/slskd/blob/master/docs/config.md
  - https://github.com/mrusse/soularr
  - https://hotio.dev/containers/lidarr/ and https://hotio.dev/containers/prowlarr/
  - https://docs.linuxserver.io/images/docker-transmission/
