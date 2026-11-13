# Lidarr stack

Docker Compose services for automated music downloads: **Lidarr** + **Prowlarr** +
**Soularr** + **Slskd** + **Transmission**. They live in this repo's
`docker-compose.yml` alongside `jellyfin` and `deemix` (imported from the old
`../lidarr-stack` repo — see [lidarr-stack-merge-research.md](../explanation/research/lidarr-stack-merge-research.md)).

Based on https://codeberg.org/coegho/lidarr-docker-compose-example, with a
Transmission torrent client added, the Soularr web UI enabled, and paths/secrets
moved into `.env`.

**Tasks:** [set up the whole stack](../how-to/setup.md) ·
[wire these services](../how-to/wire-lidarr-stack.md) ·
[add music](../how-to/add-music.md).
**Why it's built this way:** [../explanation/architecture.md](../explanation/architecture.md).

## Services

| Service      | Port(s)            | Purpose                                        |
|--------------|--------------------|------------------------------------------------|
| Lidarr       | 8686               | Music library management / wanted albums       |
| Prowlarr     | 9696               | Indexer manager, syncs indexers to Lidarr      |
| Soularr      | 8265               | Bridges Lidarr wanted albums to Slskd          |
| Slskd        | 5030, 5031, 50300  | Soulseek client (web UI, http, listen port)    |
| Transmission | 9091, 51413 (t/u)  | Torrent client (web UI + peer port)            |
| FlareSolverr | 8191               | Solves Cloudflare challenges for tagged indexers (see [flaresolverr-research.md](../explanation/research/flaresolverr-research.md)) |

Each service's config dir (`lidarr/`, `prowlarr/`, `slskd/`, `soularr/`,
`transmission/`) is git-ignored — it holds runtime state and secrets. The only
tracked files are the templates `soularr/config.ini.example` and
`slskd/slskd.yml.example`.

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
