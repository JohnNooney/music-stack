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
| Gluetun      | publishes 9696, 5030, 5031, 50300, 9091, 51413 (t/u), 8191 | IPVanish OpenVPN tunnel + kill switch the routed services share (spec 0005) |
| Lidarr       | 8686               | Music library management / wanted albums       |
| Prowlarr     | 9696               | Indexer manager, syncs indexers to Lidarr (routed) |
| Soularr      | 8265               | Bridges Lidarr wanted albums to Slskd          |
| Slskd        | 5030, 5031, 50300  | Soulseek client (web UI http/https, listen port; routed) |
| Transmission | 9091, 51413 (t/u)  | Torrent client (web UI + peer port; routed)    |
| FlareSolverr | 8191               | Solves Cloudflare challenges for tagged indexers (routed; see [flaresolverr-research.md](../explanation/research/flaresolverr-research.md)) |
| Tailscale    | tailnet 443, 8443–8448 | Serves every web UI to the tailnet over HTTPS (see `tailscale/serve.json`) |

Each service's config dir (`lidarr/`, `prowlarr/`, `slskd/`, `soularr/`,
`transmission/`, `tailscale/`) is git-ignored — it holds runtime state and
secrets. The only tracked files are the templates `soularr/config.ini.example`,
`slskd/slskd.yml.example` and `tailscale/serve.json.example`.

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
- `.env` also holds the VPN/remote-access secrets: `OPENVPN_USER` +
  `OPENVPN_PASSWORD` (the IPVanish account email and password, interpolated
  into gluetun under its own env names) and `TS_AUTHKEY` (the tailscale
  sidecar's auth key). `VPN_SERVER_COUNTRIES` is an optional override.
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

- **Networking:** the stack is split into **routed** and **non-routed**
  services (spec 0005 — see
  [gluetun-vpn-tailscale-research.md](../explanation/research/gluetun-vpn-tailscale-research.md)).
  **Routed:** prowlarr, slskd, flaresolverr and transmission share gluetun's
  network namespace (`network_mode: "service:gluetun"`) — all their traffic
  egresses through the IPVanish tunnel, gluetun's firewall is the kill switch,
  and they reach each other on `localhost` inside the netns (Prowlarr →
  FlareSolverr is `http://localhost:8191`). **Non-routed:** jellyfin, deemix,
  library-watcher, lidarr, soularr and tailscale keep their own netns and
  direct egress.
  - All routed ports are published on **gluetun**, so `localhost:<port>` on
    the Mac keeps working. A routed service can't carry `ports:`/`networks:`/
    `hostname:` — their `*.internal` aliases (`prowlarr.internal`,
    `slskd.internal`, `transmission.internal`, `flaresolverr.internal`) live on
    gluetun's `networks:` entry, so existing URLs (`soularr/config.ini`'s
    `host_url`, Lidarr's download client) still resolve to where the app
    listens.
  - Non-routed services get their own `*.internal` alias (`lidarr.internal`,
    `soularr.internal`). Plain service names (`lidarr`, `slskd`) resolve too —
    use whichever you like when wiring apps together. The `hostname:` field
    alone does *not* create a DNS name; the aliases are what make these
    addresses work.
  - Routed apps resolve non-routed service names (Prowlarr pushes indexers to
    `lidarr.internal:8686`) only because gluetun uses Docker's embedded DNS
    (`DNS_ADDRESS=127.0.0.11`) instead of its own Unbound/DoT resolver —
    "no such host" on `*.internal` means check that first.
  - The tailscale sidecar serves the web UIs to the tailnet on
    `https://<hostname>.<tailnet>.ts.net` (+ ports 8443–8448) per
    `tailscale/serve.json` — tailnet-only, ACL-gated, never public (funnel is
    not used). It stays off gluetun's netns so tailnet paths stay direct.
- Remove `transmission` or `prowlarr` if you don't want torrents — the Soulseek
  path (Lidarr + Soularr + Slskd) doesn't need them.
- `SCRIPT_INTERVAL=300` makes Soularr check Lidarr for wanted albums every 5
  minutes.
- Set `SLSKD_REMOTE_CONFIGURATION=false` before exposing Slskd to the internet —
  remote config can read the merged configuration, including env-injected
  secrets.
- **VPN note:** the routed services' traffic egresses through IPVanish, and
  IPVanish has no port forwarding, so slskd's listen port (50300) and
  Transmission's peer port (51413) accept nothing inbound through the tunnel —
  they're still published on gluetun for LAN reach, purely for uniformity.
  Soulseek still works — connections are made outbound against peers with open
  ports — but firewalled-to-firewalled transfers will fail. For full inbound
  connectivity you'd need a provider with port forwarding (AirVPN gives static
  ports; PIA/Proton assign dynamic ones via `VPN_PORT_FORWARDING`) and to set
  `soulseek.listen_port` in `slskd.yml` to match.
