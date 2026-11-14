# How to put the download services behind the VPN and reach the UIs over Tailscale

One-time cutover: gluetun (IPVanish, OpenVPN) carries prowlarr, slskd,
flaresolverr and transmission's traffic, and a tailscale sidecar serves every
web UI to your tailnet over HTTPS. The compose changes are already in
`docker-compose.yml` — this guide is the human-gated part: IPVanish/Tailscale
console work, `.env` secrets, `serve.json`, and one Prowlarr re-point.

Why it's built this way:
[../explanation/specs/0005-gluetun-vpn-tailscale.md](../explanation/specs/0005-gluetun-vpn-tailscale.md)
and
[../explanation/research/gluetun-vpn-tailscale-research.md](../explanation/research/gluetun-vpn-tailscale-research.md).
Service facts: [../reference/lidarr-stack.md](../reference/lidarr-stack.md).

## Prerequisites

- Docker Desktop running; `docker compose config` renders cleanly.
- An IPVanish account — you need the account **email and password** (the same
  credentials the IPVanish app uses).
- A Tailscale account and tailnet, with the devices you'll use remotely
  (phone/laptop) already joined to it.

## 1. Put the IPVanish credentials in `.env`

Set `OPENVPN_USER` to your IPVanish account email and `OPENVPN_PASSWORD` to the
account password. No config files are needed — gluetun embeds the IPVanish
profile. Optionally set `VPN_SERVER_COUNTRIES` (defaults to `Netherlands`).

## 2. Enable MagicDNS and HTTPS certificates on the tailnet

In the Tailscale admin console (https://login.tailscale.com/admin), one-time,
tailnet-wide:

- **DNS** page: enable **MagicDNS** (this also reveals your tailnet name, e.g.
  `tail12345.ts.net` or a custom name — note it for step 4).
- **DNS** page → **HTTPS Certificates** section: **Enable HTTPS**.

## 3. Create the tailnet tag and auth key

The node's key must not expire, so it runs under a tailnet **tag**:

1. Admin console → **Access controls (ACL)** / policy file: add the tag to
   `tagOwners` with your Tailscale login identity — the email shown on the
   **Users** page, e.g.
   `"tagOwners": { "tag:container": ["you@gmail.com"] }`, and save.
2. Admin console → **Settings** → **Keys** → **Generate auth key**: pick
   **Reusable**, allow **Ephemeral** devices, and assign the tag
   `tag:container`. Copy the `tskey-auth-…` value into `.env` as `TS_AUTHKEY`.

## 4. Create `tailscale/serve.json`

```sh
cp tailscale/serve.json.example tailscale/serve.json
```

Replace every `<TS_HOSTNAME>.<tailnet>.ts.net` placeholder with the node's real
FQDN — `<TS_HOSTNAME>` is `musicstack` (from `docker-compose.yml`) and
`<tailnet>` is the tailnet name from step 2, so e.g.
`musicstack.tail12345.ts.net`. The file maps tailnet ports to services: 443 →
Jellyfin, 8443 → slskd, 8444 → transmission, 8445 → prowlarr, 8446 → deemix,
8447 → lidarr, 8448 → soularr.

`serve.json` and `tailscale/state/` are git-ignored like the other app configs.

Editing `serve.json` later: the compose file mounts it as a single read-only
file, so tailscaled won't notice the change — run
`docker compose up -d --force-recreate tailscale` after edits. (Tailscale's
docs recommend directory-mounting `TS_SERVE_CONFIG` for live update
detection — mounting `./tailscale:/config:ro` is the alternative; see the
research doc §6.)

## 5. Bring the stack up

```sh
docker compose up -d
```

If a routed service fails to start because its old network namespace is stale,
force-recreate the routed group:

```sh
docker compose up -d --force-recreate gluetun prowlarr slskd flaresolverr transmission
```

Note for later: tunnel drops heal *inside* the container on their own
(`HEALTH_RESTART_VPN=on` default) — but restarting the gluetun **container**
tears down the shared netns, so recreate the whole group afterwards with the
same `--force-recreate` command. Any change to gluetun's published `ports:`
needs it too.

## 6. Re-point Prowlarr's FlareSolverr proxy

Inside the shared netns, routed services reach each other on `localhost`, so the
one app-side URL that changes is:

- Prowlarr UI (http://localhost:9696) → **Settings** → **Indexer Proxies** →
  edit the FlareSolverr entry → set **Host** to `http://localhost:8191`, save.

Everything else keeps working untouched: `slskd.internal`, `lidarr.internal`,
`transmission.internal` and `flaresolverr.internal` now resolve on gluetun's
network entry, so soularr's `config.ini` and Lidarr's download-client config
need no changes.

## Rollback

The change is config-only — no data migration. Check out the previous
`docker-compose.yml` revision (or `git revert` this change) and
`docker compose up -d`. If `tailscale/serve.json` was already created, the
`musicstack` machine entry may linger in the admin console — delete it under
**Machines**.

## Verify — smoke checklist

Run these in order; stop at the first failure.

1. **Tunnel up:**
   `docker inspect gluetun --format '{{.State.Health.Status}}'` → `healthy`.
   `docker logs tailscale` shows the node registering; the admin console's
   **Machines** page lists `musicstack` tagged `tag:container`.
2. **Egress is IPVanish:** `docker exec prowlarr curl -s ifconfig.me` returns a
   VPN address, not your real WAN IP. If prowlarr's image lacks curl, try
   another routed service or query gluetun's control server inside the shared
   netns: `docker exec prowlarr wget -qO- localhost:8000/v1/publicip/ip`.
3. **Kill switch:** `docker pause gluetun` (freezes openvpn — the tunnel's only
   route out dies), then `docker exec prowlarr curl -s --max-time 10
   ifconfig.me` must fail. `docker unpause gluetun` and wait for `healthy`
   again. Pause, not stop: stopping gluetun tears down the shared netns and the
   routed services stay dead until the whole group is recreated.
4. **UIs on the LAN:** `curl -o /dev/null -w '%{http_code}\n' localhost:9696`,
   `localhost:5030`, `localhost:9091`, `localhost:8191` all respond from the
   host as before.
5. **Wiring:** soularr reaches slskd (`docker exec soularr wget -qO- --timeout=10
   http://slskd.internal:5030 >/dev/null` or watch its log); in the Prowlarr UI,
   the Lidarr app sync still succeeds (exercises the `DNS_ADDRESS` override —
   "no such host" on `lidarr.internal` means check that first); the
   FlareSolverr proxy test at `localhost:8191` passes.
6. **Tailnet:** from a tailnet device, `https://musicstack.<tailnet>.ts.net`
   loads Jellyfin and each `serve.json` port (`:8443`–`:8448`) loads its UI.
   `docker exec tailscale tailscale serve status` shows the mount table.
