# Lidarr stack

Docker Compose services for automated music downloads: **Lidarr** + **Prowlarr** +
**Soularr** + **Slskd** + **Transmission**. They live in this repo's
`docker-compose.yml` alongside `jellyfin` and `deemix` (imported from the old
`../lidarr-stack` repo — see [lidarr-stack-merge-research.md](lidarr-stack-merge-research.md)).

Based on https://codeberg.org/coegho/lidarr-docker-compose-example, with a
Transmission torrent client added, the Soularr web UI enabled, and paths/secrets
moved into `.env`.

## Services

| Service      | Port(s)            | Purpose                                        |
|--------------|--------------------|------------------------------------------------|
| Lidarr       | 8686               | Music library management / wanted albums       |
| Prowlarr     | 9696               | Indexer manager, syncs indexers to Lidarr      |
| Soularr      | 8265               | Bridges Lidarr wanted albums to Slskd          |
| Slskd        | 5030, 5031, 50300  | Soulseek client (web UI, http, listen port)    |
| Transmission | 9091, 51413 (t/u)  | Torrent client (web UI + peer port)            |

Each service's config dir (`lidarr/`, `prowlarr/`, `slskd/`, `soularr/`,
`transmission/`) is git-ignored — it holds runtime state and secrets. The only
tracked files are the templates `soularr/config.ini.example` and
`slskd/slskd.yml.example`.

## How it works

```
You add an artist in Lidarr
        │
        ▼
Lidarr pulls MusicBrainz metadata → albums become "wanted/missing"
        │
        ├──► (torrent path) Lidarr searches Prowlarr indexers → sends
        │    torrents to Transmission → imports finished files
        │
        └──► (soulseek path) Soularr polls Lidarr's wanted list every
             300s → searches Slskd → peers send files → Soularr tells
             Lidarr to import
        │
        ▼
Files land in DATA_DIR/media/music → union_library symlinks them into the
union root (ADR 0004) → Jellyfin serves them
```

### Adding music — the workflow

1. **Add an artist** in Lidarr (http://localhost:8686 → Artists → Add New).
   Make sure both the artist and the albums you want are **monitored** — that's
   what makes them "wanted". Unmonitored albums are never downloaded.
2. **Mind the Metadata Profile.** This is the #1 gotcha: the default
   *Standard* profile only allows primary type **Album**, secondary type
   **Studio**, status **Official**. Artists whose MusicBrainz discography is
   only singles, EPs, compilations, or bootlegs end up with **0 albums** and
   nothing is ever wanted. Fix: Settings → Metadata Profiles → enable more
   release types (e.g. EP, Single, Compilation), save, then refresh the
   artist.
3. Lidarr now lists the albums under **Wanted → Missing** (also queryable at
   `/api/v1/wanted/missing`). Soulseek and torrents both draw from this list.
4. **Soulseek:** nothing to trigger manually — Soularr checks every
   `SCRIPT_INTERVAL` seconds (300). Watch http://localhost:8265 or
   `soularr/soularr.log` for grabs, and slskd's Downloads tab
   (http://localhost:5030) for transfer progress.
5. **Torrents:** Prowlarr pushes indexers to Lidarr; Lidarr sends matches to
   Transmission (http://localhost:9091) and imports finished files.
6. When a folder completes, Lidarr imports it into `/data/media/music`
   (= `DATA_DIR/media/music`) and Jellyfin picks it up via the union library
   on its next scan.

### What "failure" looks like (it's usually fine)

- `Download error. Requeue file` / `reported as failed by the remote user`
  in Soularr/slskd logs = an individual **peer** rejected or dropped the
  transfer. Normal on Soulseek. Soularr requeues and tries other sources.
- `Failed to grab` for an album = that search result was a dead end; Soularr
  moves to the next result next cycle.
- `No releases wanted` = the wanted list is empty — either everything's
  downloaded, or albums aren't monitored (see step 2 above).
- `stalled_timeout = 3600` in `config.ini` controls how long Soularr waits on
  a stalled album before giving up on it.

## Data layout

`DATA_DIR` (set in `.env`) should look like this. Docker will create missing
folders on first `up`, or create them yourself:

```
DATA_DIR/
├── media/
│   └── music          # your library (Lidarr manages, slskd shares)
├── slskd/
│   ├── downloads      # finished Soulseek downloads
│   └── incomplete     # in-progress Soulseek downloads
└── torrents/
    ├── music          # finished torrents
    ├── incomplete     # in-progress torrents
    └── torrent-files  # watch dir for .torrent files
```

All Lidarr-stack containers see `DATA_DIR` as `/data`, so paths are identical
across services — no remote path mapping needed in Lidarr.

## Secrets layout

Everything secret lives in the git-ignored `.env` or in git-ignored app config:

- `.env` holds `SLSKD_*` (Soulseek account, web UI login, primary API key) and
  is injected into the slskd container by `docker-compose.yml`. slskd YAML keys
  override env vars when both are set, so `slskd.yml` deliberately leaves those
  keys unset — see `slskd/slskd.yml.example`.
- `soularr/config.ini` (untracked, real file — Soularr has no env-var support)
  holds the Lidarr and slskd API keys. `SLSKD_API_KEY` and `[Slskd] api_key`
  must match. `soularr/config.ini.example` documents the shape.
- `lidarr/config.xml`, `prowlarr/config.xml` and their `*.db` files hold
  runtime-generated API keys/indexer credentials — all inside git-ignored dirs.
- `transmission/settings.json` is generated on first run; RPC auth is off by
  default (`USER`/`PASS` env vars in the compose file enable it).
- `.gitignore` must never whitelist `soularr/config.ini` — that is how live keys
  were committed once in the old repo.

## Setup

### 1. Configure `.env`

- `DATA_DIR` — root of the data layout above.
- `PUID`/`PGID` — uid/gid the arr containers run as (`id -u` / `id -g`). Note
  `jellyfin`/`deemix` run as `501:501` regardless — that is intentional.
- `TZ` — your timezone.
- `SLSKD_SLSK_USERNAME`/`SLSKD_SLSK_PASSWORD` — Soulseek account.
- `SLSKD_USERNAME`/`SLSKD_PASSWORD` — slskd web UI login.
- `SLSKD_API_KEY` — primary slskd API key (16–255 chars) used by Soularr.
- Leave `UMASK=002` alone.

### 2. Start the stack

```
docker compose up -d
```

### 3. Lidarr (http://localhost:8686)

- Settings > Media Management: add root folder `/data/media/music`.
- Settings > General: copy the API key (needed for Soularr and Prowlarr).
- Settings > Download Clients: add **Transmission** —
  host `transmission.internal`, port `9091`, directory `/data/torrents/music`,
  username/password if you set `USER`/`PASS` in the compose file.
- (Optional) Settings > Metadata Profiles: allow more release types than the
  Standard profile's Album/Studio/Official — see "Adding music" above.
- If you enable "Tag Audio Files with Metadata" you can't use hardlinks without
  breaking torrent seeding — pick two of: hardlinks, metadata tagging, seeding.

### 4. Prowlarr (http://localhost:9696)

- Add your indexers.
- Settings > Apps: add Lidarr (host `lidarr.internal`, port `8686`, the API key
  from step 3). Prowlarr syncs indexers to Lidarr automatically.

### 5. Transmission (http://localhost:9091)

The config file `./transmission/settings.json` is generated on first start.
Stop the container, edit it, then restart:

```
docker compose stop transmission
```

```json
"download-dir": "/data/torrents/music",
"incomplete-dir": "/data/torrents/incomplete",
"incomplete-dir-enabled": true,
"watch-dir": "/data/torrents/torrent-files",
"watch-dir-enabled": true,
"rpc-whitelist-enabled": false
```

Also set `rpc-username`/`rpc-password` here (or via `USER`/`PASS` env in the
compose file), then `docker compose up -d transmission`.

### 6. Slskd (http://localhost:5030)

Log in with the `SLSKD_USERNAME`/`SLSKD_PASSWORD` from `.env`. Shares and
transfer limits are in `slskd/slskd.yml` (see `slskd.yml.example`); the key
bits:

```yaml
directories:
  incomplete: /incomplete
  downloads: /downloads
shares:
  directories:
    - /data/music
    - /deemix
```

`/deemix` is `/Users/john/Music/Deemix` mounted read-only — sharing real files
is important, since many Soulseek peers auto-reject users with an empty share.
Add `/downloads` too if you want completed grabs shared onward automatically.

### 7. Soularr

`cp soularr/config.ini.example soularr/config.ini` (already present on this
machine) and set:

- `Lidarr.api_key` — the Lidarr API key from step 3.
- `Slskd.api_key` — must equal `SLSKD_API_KEY` in `.env`.
- The `host_url`/`download_dir` values already match this compose file; only
  change them if you renamed services or paths.

Restart: `docker compose restart soularr`

The web UI (http://localhost:8265) shows live logs, failed imports, and
settings. It requires `log_to_file = True` in `config.ini` — already set here —
and `WEBUI_ENABLED=true` in the compose file.

## Notes

- **Networking:** each service gets a `*.internal` network alias
  (`lidarr.internal`, `slskd.internal`, `transmission.internal`, …). Plain
  service names (`lidarr`, `slskd`) resolve too — use whichever you like when
  wiring apps together. The `hostname:` field alone does *not* create a DNS
  name; the aliases are what make these addresses work.
- Remove `transmission` or `prowlarr` if you don't want torrents — the Soulseek
  path (Lidarr + Soularr + Slskd) doesn't need them.
- `SCRIPT_INTERVAL=300` makes Soularr check Lidarr for wanted albums every 5
  minutes.
- Set `SLSKD_REMOTE_CONFIGURATION=false` before exposing Slskd to the internet —
  remote config can read the merged configuration, including env-injected
  secrets.
- **VPN note:** IPVanish has no port forwarding, so slskd's listen port (50300)
  can never accept inbound connections. Soulseek still works — connections are
  made outbound against peers with open ports — but firewalled-to-firewalled
  transfers will fail. For full inbound connectivity you'd need a provider
  with port forwarding (AirVPN gives static ports; PIA/Proton assign dynamic
  ones) and to set `soulseek.listen_port` in `slskd.yml` to match. Keep
  Transmission behind the VPN regardless.
- Verify Soulseek connectivity: slskd UI should show *Connected* to
  `vps.slsknet.org`, and `docker logs soularr` should show grabs rather than
  `NameResolutionError` or 401/403 (401 = wrong API key).
