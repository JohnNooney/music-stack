# How to wire the Lidarr stack

Per-service wiring for the Lidarr stack once `.env` is configured and
`docker compose up -d` has run (steps 1–2 of [setup.md](setup.md)). Do the
services in this order — Soularr and Prowlarr both need the Lidarr API key.

Service inventory, ports and data layout: [../reference/lidarr-stack.md](../reference/lidarr-stack.md).

## 1. Lidarr (http://localhost:8686)

- Settings > Media Management: add root folder `/data/media/music`.
- Settings > General: copy the API key (needed for Soularr and Prowlarr).
- Settings > Download Clients: add **Transmission** —
  host `transmission.internal`, port `9091`, directory `/data/torrents/music`,
  username/password if you set `USER`/`PASS` in the compose file.
- (Optional) Settings > Metadata Profiles: allow more release types than the
  Standard profile's Album/Studio/Official — see
  [add-music.md](add-music.md#mind-the-metadata-profile).
- If you enable "Tag Audio Files with Metadata" you can't use hardlinks without
  breaking torrent seeding — pick two of: hardlinks, metadata tagging, seeding.

## 2. Prowlarr (http://localhost:9696)

- Add your indexers.
- Settings > Apps: add Lidarr (host `lidarr.internal`, port `8686`, the API key
  from step 1). Prowlarr syncs indexers to Lidarr automatically.

## 3. Transmission (http://localhost:9091)

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

## 4. Slskd (http://localhost:5030)

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

`/deemix` is `$MUSIC_DIR/Deemix` mounted read-only — sharing real files
is important, since many Soulseek peers auto-reject users with an empty share.
Add `/downloads` too if you want completed grabs shared onward automatically.

## 5. Soularr

`cp soularr/config.ini.example soularr/config.ini` (already present on this
machine) and set:

- `Lidarr.api_key` — the Lidarr API key from step 1.
- `Slskd.api_key` — must equal `SLSKD_API_KEY` in `.env`.
- The `host_url`/`download_dir` values already match this compose file; only
  change them if you renamed services or paths.

Restart: `docker compose restart soularr`

The web UI (http://localhost:8265) shows live logs, failed imports, and
settings. It requires `log_to_file = True` in `config.ini` — already set here —
and `WEBUI_ENABLED=true` in the compose file.
