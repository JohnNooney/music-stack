# Spec 0005: Gluetun (IPVanish) VPN egress for the download services + Tailscale access to the web UIs

**Status:** ready-for-agent
**Labels:** `ready-for-agent`
**Glossary:** use the terms defined in `CONTEXT.md` at the repo root plus the lidarr-stack service names from `docs/reference/lidarr-stack.md`. New terms introduced by this spec:

- **Routed service**: a compose service that shares gluetun's network namespace via `network_mode: "service:gluetun"` — prowlarr, slskd, flaresolverr, transmission. All its traffic egresses through the VPN tunnel; its ports are published on the `gluetun` service, not on itself.
- **Non-routed service**: everything else in the compose file (jellyfin, deemix, library-watcher, lidarr, soularr, tailscale). Keeps its own netns and direct egress.
- **Shared netns**: the single Linux network namespace owned by the gluetun container that the routed services join. Inside it, routed services reach each other on `localhost`.
- **Serve config**: the `serve.json` read by the tailscale container (`TS_SERVE_CONFIG`), declaring which tailnet HTTPS ports proxy to which `service:port` backends.

**Background research:** `docs/explanation/research/gluetun-vpn-tailscale-research.md` — all claims below about gluetun env vars, Docker networking semantics, IPVanish capabilities and Tailscale options are sourced there; this spec records decisions, the research records citations.
**Prior spec:** none — first spec to touch `docker-compose.yml` networking rather than the stdlib tools.

## Problem Statement

Four services in the Lidarr stack talk to the internet — Prowlarr queries indexers, FlareSolverr fetches challenge-gated indexer pages, Slskd connects to the Soulseek network, Transmission connects to public torrent swarms — and today all of that traffic egresses on the host's real IP. The user wants that traffic behind their IPVanish subscription, and wants to reach the stack's web UIs — jellyfin and deemix included — from personal devices when away from the LAN via Tailscale, without installing anything else on the host: the whole remote-access story must live inside the compose file.

The constraint that shapes the VPN half: **IPVanish has no port forwarding and gluetun can't do WireGuard with it** — the provider list for `VPN_TYPE=wireguard` doesn't include `ipvanish`, and IPVanish's own docs confirm a NAT firewall that forwards nothing inbound. So the design is OpenVPN-only, outbound-only, and the peer-facing ports (slskd 50300, transmission 51413) remain published for LAN reach but accept nothing inbound through the tunnel.

## Solution

Add one **`gluetun` service** to `docker-compose.yml` — the `qmcgaw/gluetun` container running an IPVanish OpenVPN client — and make the four download/indexer services **routed**: each drops its `ports:` and `networks:` blocks and joins the shared netns with `network_mode: "service:gluetun"`. Every port they used to publish (prowlarr 9696, slskd 5030/5031/50300, transmission 9091/51413 tcp+udp, flaresolverr 8191) is published on `gluetun` instead, so `localhost:<port>` on the Mac keeps working for debugging.

Add one **`tailscale` service** — the `tailscale/tailscale` container — on the same compose network with its **own** netns (never gluetun's). Its `TS_SERVE_CONFIG` proxies each web UI by service name to tailnet HTTPS ports: `https://<host>.<tailnet>.ts.net` serves Jellyfin, and sibling ports serve deemix, lidarr, prowlarr, slskd, transmission and soularr. Because the sidecar sits on the compose network, it reaches routed apps through gluetun's DNS name (`gluetun:5030`) and non-routed apps directly (`jellyfin:8096`) — no published host port needed for the tailnet path at all.

Existing addresses keep working because the four `*.internal` network aliases move onto gluetun's own `networks:` entry — `slskd.internal:5030` from soularr resolves to gluetun's IP where slskd now listens. Inside the shared netns, routed services reach each other on `localhost` (Prowlarr → FlareSolverr becomes `http://localhost:8191`). Routed services can still resolve *non-routed* service names (lidarr.internal for Prowlarr's app sync) because gluetun is pointed at Docker's embedded DNS (`DNS_ADDRESS=127.0.0.11`) instead of its own Unbound/DoT resolver.

Secrets stay in `.env` per repo convention: three new keys — `OPENVPN_USER`, `OPENVPN_PASSWORD` (gluetun's own env names) and `TS_AUTHKEY`.

Per repo docs conventions, implementation ships a **runbook**: a new `docs/how-to/` task guide covering the one-time manual steps (IPVanish + Tailscale admin-console work, `serve.json` cutover, the Prowlarr UI re-point) and the smoke checklist — so the cutover is repeatable and the spec isn't the only place the procedure lives.

## User Stories

1. As the maintainer, I want prowlarr, slskd, flaresolverr and transmission's outbound traffic to egress through my IPVanish VPN, so my real IP never touches indexers, Soulseek or torrent swarms.
2. As the maintainer, I want a kill switch, so if the tunnel drops the routed services can't leak onto my real connection.
3. As the maintainer, I want the routed services to wait for the tunnel to be healthy before starting, so they never race VPN establishment.
4. As the maintainer, I want `localhost:9696`, `localhost:5030`, `localhost:9091` etc. on the Mac to keep working after the change, so my browser bookmarks and muscle memory survive.
5. As the maintainer, I want the existing `*.internal` URLs in soularr's `config.ini` and Lidarr's download-client config to keep resolving, so no app config has to be re-pointed.
6. As the maintainer, I want Prowlarr to reach FlareSolverr inside the shared netns, so Cloudflare-solving keeps working — and since they now share an egress IP, the solver's IP-bound cookies are replayed correctly.
7. As the maintainer, I want routed Prowlarr to still push indexers to non-routed Lidarr by service name, so indexer sync isn't broken by the VPN boundary.
8. As the maintainer, I want VPN credentials in `.env` only, matching the stack's secrets convention, so nothing sensitive lands in the compose file or git.
9. As the maintainer, I want the gluetun service pinned to a stable tag line (`:v3`), so upgrades are deliberate like the rest of the stack's pinned images.
10. As a user, I want to open Jellyfin, Deemix, Lidarr, Prowlarr, Slskd, Transmission and Soularr's UIs from my phone/laptop over Tailscale when I'm away, so the whole stack is reachable remotely — not just the download services.
11. As a user, I want those remote URLs to be HTTPS on my tailnet name with tailnet ACLs, so nothing is exposed to the public internet.
12. As the maintainer, I want Tailscale to run as a compose service like everything else, so the remote-access story lives in one file and nothing extra gets installed on the host.
13. As the maintainer, I want the tailscale container on its **own** netns, not gluetun's, so tailscaled's traffic isn't forced through IPVanish and direct tailnet paths still form.
14. As the maintainer, I want the tailscale node's state persisted across container recreates, so it doesn't re-register a new machine every `docker compose up`.
15. As the maintainer, I want the tailscale node tagged (non-expiring key) and authenticated via `TS_AUTHKEY` from `.env`, so restarts are unattended.
16. As the maintainer, I want the serve mapping declared in a versionable `serve.json` file, so "which service is on which tailnet port" is documented next to the compose file, not in a hidden CLI state.
17. As the maintainer, I want jellyfin, deemix, lidarr, soularr and library-watcher untouched by the VPN, so the media-serving path keeps its current latency and LAN behaviour.
18. As the maintainer, I want a documented smoke checklist (tunnel up, egress IP is IPVanish's, UIs reachable, Prowlarr→Lidarr sync, tailscale serving) so I can verify the cutover in one pass.
19. As the maintainer, I want the slskd and transmission peer ports still published on gluetun for LAN reach, even though IPVanish accepts nothing inbound, so behaviour is uniform and documented rather than silently absent.
20. As the maintainer, I want the steps only I can do — admin-console key generation, `.env` secrets, the `serve.json` FQDN, the Prowlarr UI re-point — called out as a runbook, so nothing human-gated hides inside prose.
21. As the maintainer, I want the how-to doc to end with the verification pass, so "is it working" is a checklist, not archaeology.

## Implementation Decisions

- **One `gluetun` service**, modelled on the Lidarr-stack service shape (`container_name`, `restart: unless-stopped`, `logging: json-file`, `${VAR}` interpolation from `.env`). Image `qmcgaw/gluetun:v3` — the rolling stable line, per the gluetun wiki's advice that `:latest` tracks a dev edge. Requires `cap_add: NET_ADMIN` and `devices: /dev/net/tun` (works under Docker Desktop's Linux VM on this host).
- **Provider env vars**: `VPN_SERVICE_PROVIDER=ipvanish`, `VPN_TYPE=openvpn` (default, set explicitly), `OPENVPN_USER=${OPENVPN_USER}`, `OPENVPN_PASSWORD=${OPENVPN_PASSWORD}`, `SERVER_COUNTRIES=${VPN_SERVER_COUNTRIES:-Netherlands}`, `TZ=${TZ}`, `DNS_ADDRESS=127.0.0.11`. `DNS_ADDRESS` is a deliberate trade-off: it restores Docker service-name resolution for routed containers at the cost of bypassing gluetun's Unbound/DoT and blocklists. `DNS_KEEP_NAMESERVER=on` is rejected — the wiki flags it as a leak risk. `UPDATER_PERIOD` and `FIREWALL_OUTBOUND_SUBNETS` stay commented-out options (the compose network needs no firewall override; gluetun auto-allows its attached Docker subnets).
- **Ports move to gluetun**: `"9696:9696"`, `"5030:5030"`, `"5031:5031"`, `"50300:50300"`, `"9091:9091"`, `"51413:51413"`, `"51413:51413/udp"`, `"8191:8191"`. The gluetun control-server port 8000 stays commented out — nothing in the stack consumes it.
- **Aliases move to gluetun**: `prowlarr.internal`, `slskd.internal`, `transmission.internal`, `flaresolverr.internal` are listed as aliases on gluetun's `networks.default` entry (plus `gluetun.internal`). A routed service cannot carry network aliases, and moving them means `soularr/config.ini`'s `host_url = http://slskd.internal:5030` and Lidarr's `transmission.internal:9091` download client keep working unmodified.
- **Per-service edits** — each routed service gets `network_mode: "service:gluetun"` and `depends_on: { gluetun: { condition: service_healthy } }`, and loses `ports:`, `networks:` and `hostname:` (`hostname` is meaningless in the shared netns). Gluetun ships a built-in `HEALTHCHECK`, so `service_healthy` waits for the tunnel, not just container start. Nothing else changes — images, env, volumes, `user:` on slskd, tmpfs on flaresolverr all stay.
- **One UI re-point**: Prowlarr's FlareSolverr proxy Host becomes `http://localhost:8191` (routed↔routed is localhost inside the netns). Everything else that references `*.internal` names keeps working via the moved aliases.
- **One `tailscale` service** — `tailscale/tailscale`, its own netns on the default network (`network_mode: service:gluetun` is explicitly rejected: it would force tailscaled's control/DERP/peer traffic through IPVanish, killing direct tailnet paths). Env: `TS_AUTHKEY=${TS_AUTHKEY}`, `TS_STATE_DIR=/var/lib/tailscale`, `TS_HOSTNAME` (e.g. `musicstack`), `TS_SERVE_CONFIG=/config/serve.json`, `TS_EXTRA_ARGS=--advertise-tags=tag:container` (tagged nodes don't expire — an untagged node's key dies on the tailnet key-expiry schedule and the stack silently goes dark). `TS_USERSPACE` stays at its `true` default — userspace netstack needs no `/dev/net/tun`. Volumes: a persistent state dir (mandatory — without it the node re-registers every recreate) and a read-only mount of the serve config.
- **`serve.json` layout** — HTTPS on distinct tailnet ports, one per UI (path mounting rejected: serve strips mount paths and none of these UIs reliably honors a base URL):
  - `443` → `http://jellyfin:8096` — the headliner gets the canonical URL
  - `8443` → `http://gluetun:5030` (slskd)
  - `8444` → `http://gluetun:9091` (transmission)
  - `8445` → `gluetun:9696` (prowlarr)
  - `8446` → `http://deemix:6595`
  - `8447` → `http://lidarr:8686`
  - `8448` → `http://soularr:8265`
  - FlareSolverr (8191) is **not** served — API-only, and Prowlarr reaches it via localhost inside the netns anyway.
  The `Web` keys in `serve.json` embed the node's real FQDN (`<TS_HOSTNAME>.<tailnet>.ts.net`), which is deployment-specific — so the tracked file is `tailscale/serve.json.example` and the live `tailscale/serve.json` is git-ignored, matching the repo's `*.example` convention. Requires MagicDNS + HTTPS certificates enabled on the tailnet.
- **Repo layout for the new dirs**: `tailscale/state/` (tailscaled state, git-ignored) and `tailscale/serve.json.example` (tracked template) → `.gitignore` gains `/tailscale/*` with `!/tailscale/serve.json.example`, same pattern as `slskd/` and `soularr/`.
- **`.env` / `.env.example`**: add `OPENVPN_USER`, `OPENVPN_PASSWORD` (IPVanish account email + password), `TS_AUTHKEY` (ephemeral auth key scoped to `tag:container`, generated in the Tailscale admin console), optional `VPN_SERVER_COUNTRIES`.
- **Jellyfin reachability**: the tailnet URL (`https://<host>.<tailnet>.ts.net`) is how clients reach Jellyfin remotely; `JELLYFIN_PublishedServerUrl` stays at the LAN IP — the published-URL mechanism is for autodiscovery, and tailnet devices address the server explicitly by the ts.net name. If the Jellyfin dashboard ever reports a wrong "server address" to clients, that's a config tweak for later, not a blocker.
- **No port forwarding, by design**: `VPN_PORT_FORWARDING` is not set (it fails validation for ipvanish anyway). slskd keeps `SLSKD_SLSK_LISTEN_PORT` at its 50300 default; the port is published on gluetun for LAN reach but accepts nothing inbound through the tunnel — Soulseek still works outbound against peers with open ports. Transmission likewise runs with a closed peer port. A provider change is out of scope (already noted in `lidarr-stack.md`).
- **Manual steps — the human-gated part of the cutover, in order** (the runbook below walks through these; the agent does everything else):
  1. `.env`: set `OPENVPN_USER` + `OPENVPN_PASSWORD` to the IPVanish account email and password (no config files needed — gluetun embeds the IPVanish profile).
  2. Tailscale admin console: enable **MagicDNS** and **HTTPS certificates** for the tailnet (one-time, tailnet-wide).
  3. Tailscale admin console: create an **auth key** (reusable, ephemeral-OK, tagged `tag:container` — the tag must exist in the tailnet ACL/policy file first) and set `TS_AUTHKEY` in `.env`.
  4. Copy `tailscale/serve.json.example` → `tailscale/serve.json` and replace the FQDN placeholder with the real `<hostname>.<tailnet>.ts.net`.
  5. `docker compose up -d` (first `up` after routing changes may need `--force-recreate` on the routed group if the netns is stale).
  6. Prowlarr web UI → Settings → Indexer proxies: change the FlareSolverr Host to `http://localhost:8191` (the only app-side URL that changes — everything else resolves via the moved `*.internal` aliases).
  7. Run the smoke checklist (Testing Decisions).
- **Docs produced (Diátaxis placement)**:
  - **New how-to** `docs/how-to/vpn-and-tailscale-access.md` — the cutover runbook: prereqs, the seven manual steps above expanded with screenshots-of-words (which admin-console page, what to click), the smoke checklist as the verify section, and a rollback note (`docker compose up -d` on the previous revision — routing changes are config-only, no data migration). Diátaxis-consistent: it does the task, links out to the research for the why and to `reference/lidarr-stack.md` for facts.
  - **`docs/README.md`**: add the new guide to the How-to table.
  - **`docs/reference/lidarr-stack.md`**: the service table gains `gluetun` and `tailscale` rows; a networking paragraph records the routed/non-routed boundary, where the `*.internal` aliases live now, and the closed-inbound-port reality (extending the existing VPN note); secrets layout gains the three new `.env` keys.
  - **`docker-compose.yml`**: header comments on the gluetun/tailscale blocks pointing at this spec and the research doc, matching how jellyfin/deemix cite their research.

## Testing Decisions

- **Seam: the rendered compose file + a live smoke pass.** This is declarative infrastructure — there is no `main(argv)` seam to drive, and the repo's convention for the non-stdlib layers is a manual smoke check, not unit tests (AGENTS.md: "the HTTP clients get a manual smoke check"). The highest available seam is `docker compose config`, which fails the build on exactly the mistakes this change invites: leftover `ports:`/`networks:` on a routed service, missing env keys, port collisions.
- **Static gate (fast, repeatable)**: `docker compose config` must render cleanly; the routed services must show `network_mode: service:gluetun` and no `ports:`; all eight published ports must appear under `gluetun`; the tailscale service must have no `network_mode` and no `ports:`.
- **Smoke checklist (live, one pass — becomes the how-to's verify section)**:
  1. `docker compose up -d` → `docker inspect gluetun --format '{{.State.Health.Status}}'` reaches `healthy`; `docker logs tailscale` shows a registered node (check the admin console for the tagged machine).
  2. Egress check: `docker exec prowlarr curl -s ifconfig.me` (or the gluetun control server's public-IP endpoint) returns an IPVanish address, not the real WAN IP.
  3. Kill switch: pause/stop gluetun and confirm a routed service can no longer reach the internet.
  4. UIs on LAN: `curl -o /dev/null -w '%{http_code}' localhost:9696/5030/9091` respond on the host.
  5. Wiring: soularr reaches `slskd.internal:5030`; Prowlarr app-sync to `lidarr.internal:8686` succeeds (exercises `DNS_ADDRESS`); Prowlarr→FlareSolverr at `localhost:8191`.
  6. Tailnet: from a tailnet device, `https://<host>.<tailnet>.ts.net` loads Jellyfin and `…:8443`/`…:8444`/`…:8445`/`…:8446`/`…:8447`/`…:8448` load the other UIs. `docker exec tailscale tailscale serve status` shows the mount table.
- **Prior art**: none in-tree — this is the first spec that changes compose networking. The smoke checklist is written as a literal command list so it can later be folded into a how-to or a shell script if it proves reusable.

## Out of Scope

- **Host-side `tailscale serve`** (research Option A) — rejected by user preference: nothing gets installed on the host; the sidecar is the chosen design.
- **Tailnet-serving FlareSolverr** — API-only service, no UI worth exposing.
- **Public internet exposure (`tailscale funnel`)** — `serve` is tailnet-only; funnel is a different, deliberately-unwanted feature.
- **Switching VPN providers** for real port forwarding (AirVPN/PIA/Proton) — a separate decision with `soulseek.listen_port` consequences, already flagged in `lidarr-stack.md`.
- **`VPN_PORT_FORWARDING`, `FIREWALL_VPN_INPUT_PORTS`, gluetun's HTTP proxy/Shadowsocks outputs** — all inapplicable under IPVanish or unneeded.
- **Path-mounted tailscale serve** (`--set-path`-style) — rejected in favour of per-service ports.
- **Subnet routing / exit-node behaviour for the tailscale container** — it only serves the UIs; it does not advertise routes or act as an exit node.
- **Changes to the stdlib tools, the union layout, ADRs 0001–0005** — untouched.
- **Automated tests** — none exist for compose config in this repo and none are introduced; verification is the smoke checklist.

## Further Notes

- **The `.internal` DNS caveat is the subtlest part.** Routed containers use gluetun's resolver, not Docker's `127.0.0.11`, unless `DNS_ADDRESS=127.0.0.11` is set — without it, Prowlarr's push to `lidarr.internal` fails with "no such host" even though nothing else looks wrong. This is the failure mode to check first if indexer sync breaks.
- **Netns rebuilds.** Changing gluetun's published `ports:` later requires `docker compose up -d --force-recreate` of gluetun *and* every routed service — the shared netns is torn down with it. Routine restarts (`docker compose restart gluetun`) re-establish the tunnel in place and the routed containers keep the netns.
- **`serve.json` FQDN is deployment-specific.** The `Web` keys must literally match `<hostname>.<tailnet-name>.ts.net` — hence the `*.example` convention rather than a tracked live file. After first `up`, `docker exec tailscale tailscale serve status` is the source of truth for what's actually mounted.
- **Key expiry bites.** If the tag is forgotten, the tailscale node appears to work for months then vanishes from the tailnet when the node key expires. The tag + `TS_AUTHKEY` pairing is what makes `docker compose up -d` self-healing.
- **Seam check:** the pasted process asked to confirm testing seams with the user; per "do not interview", this spec picks the single highest seam available — rendered-config validation plus one live smoke pass — and flags no lower-level seams as needed.
- **`SLSKD_REMOTE_CONFIGURATION=true` stays as-is** (it already is today) but the tailnet exposure is the documented warning: serve 5030 only to the tailnet, never publish it more broadly.
- **Roll-forward path if IPVanish is replaced later**: the gluetun block is provider-generic — swap `VPN_SERVICE_PROVIDER` + credential env names, optionally enable `VPN_PORT_FORWARDING` and set `soulseek.listen_port`; the routed-service and tailscale wiring is unchanged.
