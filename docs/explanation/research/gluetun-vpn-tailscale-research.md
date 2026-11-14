# Gluetun (IPVanish) VPN + Tailscale remote access for the download stack — research

Research date: 2026-11-13. Sources: the official gluetun wiki and source repo
(`qdm12/gluetun`, `qdm12/gluetun-wiki`), IPVanish's own support articles, the
Docker Compose spec and docker docs, the slskd repo (`slskd/slskd`), the
Transmission docs, and tailscale.com docs + the `tailscale/tailscale` image
reference. Secret values are **never** reproduced — placeholders only.

> **TL;DR — All four services can share one Gluetun container's network stack;
> IPVanish means OpenVPN only and no inbound ports — ever.** Gluetun supports
> IPVanish via OpenVPN (`VPN_SERVICE_PROVIDER=ipvanish` + `OPENVPN_USER`/
> `OPENVPN_PASSWORD`, §1). Gluetun does **not** support IPVanish over WireGuard
> natively (§1.2) — a `custom`-provider WireGuard config file is the only
> alternative. IPVanish runs a NAT firewall with **no port forwarding** per its
> own docs, and Gluetun's `VPN_PORT_FORWARDING` doesn't cover IPVanish anyway —
> so slskd's listen port and Transmission's peer port stay permanently closed
> inbound (§5). Routing is `network_mode: "service:gluetun"` per service; all
> published ports move onto `gluetun` (§3). Non-routed containers (lidarr,
> soularr, jellyfin) reach the routed apps as `gluetun:<port>` — and the routed
> apps reach them back by service name only if gluetun uses Docker DNS
> (`DNS_ADDRESS=127.0.0.11`, §4). For Tailscale, run `tailscale serve` **on the
> Mac host** against the gluetun-published localhost ports — simpler than a
> sidecar container, and the routed services never touch the tailnet directly
> (§6).

---

## 1. IPVanish in Gluetun

Source: https://github.com/qdm12/gluetun-wiki/blob/main/setup/providers/ipvanish.md

### 1.1 Required environment variables — OpenVPN

- `VPN_SERVICE_PROVIDER=ipvanish`
- `OPENVPN_USER` — the IPVanish account username (the email you signed up with,
  per IPVanish: "log in with your IPVanish username (This is the email you
  signed up with)" —
  https://support.ipvanish.com/hc/en-us/articles/360024000253). Manual OpenVPN
  setups use the same account username/password —
  https://support.ipvanish.com/hc/en-us/articles/360042284673.
- `OPENVPN_PASSWORD`

Optional filters: `SERVER_COUNTRIES`, `SERVER_CITIES`, `SERVER_HOSTNAMES`
(comma-separated; the wiki warns `SERVER_HOSTNAMES` is the narrowest filter and
breaks if that hostname disappears from Gluetun's server data). Server list
refresh: `UPDATER_PERIOD` (e.g. `168h`) —
https://github.com/qdm12/gluetun-wiki/blob/main/setup/servers.md. Gluetun's
OpenVPN implementation for IPVanish is verified in source:
`internal/provider/ipvanish/openvpnconf.go` (auth-user-pass, AES-256-GCM/CBC,
SHA256, embedded IPVanish CA) —
https://github.com/qdm12/gluetun/blob/master/internal/provider/ipvanish/openvpnconf.go.

### 1.2 WireGuard — not supported natively for IPVanish

Gluetun's WireGuard provider list is hard-coded in
`internal/configuration/settings/provider.go`: `airvpn, custom, fastestvpn,
ivpn, mullvad, nordvpn, protonvpn, surfshark, windscribe` — **IPVanish is not
in it**, and setting `VPN_TYPE=wireguard` with `VPN_SERVICE_PROVIDER=ipvanish`
fails validation. Source:
https://github.com/qdm12/gluetun/blob/master/internal/configuration/settings/provider.go;
tracking issue https://github.com/qdm12/gluetun/issues/134 explicitly marks
"IPVanish not supported" for WireGuard. IPVanish *does* offer manual WireGuard
configs in its account panel ("WireGuard — the WireGuards configurator for
creating manual WireGuard setups",
https://support.ipvanish.com/hc/en-us/articles/360024000253), so the escape
hatch is `VPN_SERVICE_PROVIDER=custom` + `VPN_TYPE=wireguard` + a bind-mounted
`wg0.conf` or `WIREGUARD_*` env vars —
https://github.com/qdm12/gluetun-wiki/blob/main/setup/providers/custom.md.
That's extra machinery; OpenVPN is the supported path and is what the proposal
uses.

### 1.3 Image and container requirements

- Image: `qmcgaw/gluetun` on Docker Hub. Tags: `:latest` tracks the master
  branch edge; release tags (`v3.x.x`), minor tags (`v3.41`) and the rolling
  stable `:v3` exist. The wiki recommends release tags for stability;
  `:v3` = latest stable. https://github.com/qdm12/gluetun-wiki/blob/main/setup/docker-image-tags.md
- `cap_add: NET_ADMIN` and `devices: /dev/net/tun` are required for OpenVPN —
  https://github.com/qdm12/gluetun-wiki/blob/main/setup/providers/ipvanish.md.
  (On Docker Desktop for Mac the `/dev/net/tun` device exists inside the Linux
  VM, so the mapping works the same as on Linux.)
- **Built-in Docker healthcheck:** the image ships
  `HEALTHCHECK --interval=5s --timeout=5s --start-period=10s --retries=3 CMD /gluetun-entrypoint healthcheck`
  (Dockerfile), which queries the internal health server on
  `HEALTH_SERVER_ADDRESS` (default `127.0.0.1:9999`, 200/500). So
  `depends_on: { gluetun: { condition: service_healthy } }` works with **no
  extra config** — https://github.com/qdm12/gluetun-wiki/blob/main/faq/healthcheck.md,
  https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/healthcheck.md,
  https://github.com/qdm12/gluetun/blob/master/Dockerfile.
- Gluetun also auto-heals the VPN *inside* the container on failure
  (`HEALTH_RESTART_VPN=on`, default) — connected containers keep the netns
  while the tunnel is re-established. Same wiki page.
- Optional: gluetun's HTTP control server on port 8000 (`EXPOSE 8000/tcp` in
  the Dockerfile) reports forwarded port / public IP; publish it only if you
  want to query it.

### 1.4 Firewall vars that matter here

https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/firewall.md

- `FIREWALL_OUTBOUND_SUBNETS` — "comma separated subnets that Gluetun and the
  containers sharing its network stack are allowed to access." **Only needed
  when a routed container must initiate connections to the physical LAN**
  (e.g. reaching the Mac host or a non-Docker LAN device by LAN IP). It is
  *not* needed for traffic to other containers on gluetun's own Docker
  networks: Gluetun auto-allows its attached Docker subnets in both
  directions (`AcceptOutputFromIPToSubnet` / `AcceptInputToSubnet` over
  `localNetworks` in `internal/firewall/enable.go`, and confirmed by qdm12:
  "the Gluetun local Docker network is allowed to communicate by default" —
  https://github.com/qdm12/gluetun/issues/1909#issuecomment-1761712264).
  Typical value if ever needed: the home LAN CIDR, e.g. `192.168.178.0/24`
  for this host's `192.168.178.x` LAN (see `JELLYFIN_PublishedServerUrl`).
- Caution: don't list a subnet overlapping the tunnel address range, and
  DNS answers pointing at private IPs are blocked by rebinding protection —
  exempt with `DNS_REBINDING_PROTECTION_EXEMPT_HOSTNAMES`. Same wiki page.
- `FIREWALL_VPN_INPUT_PORTS` is irrelevant here — IPVanish forwards nothing
  inbound (§5).

## 2. Proposed gluetun compose block

Informed by the wiki examples and this repo's conventions (`container_name`,
`restart: unless-stopped`, `logging: json-file`, `${VAR}` from `.env`).
Secrets stay in `.env` per repo convention — new keys: `OPENVPN_USER`,
`OPENVPN_PASSWORD` (gluetun's own env names, so `.env` interpolation is
one-to-one).

```yaml
  # Gluetun: VPN client container. prowlarr, slskd, flaresolverr and
  # transmission share this network stack (network_mode: service:gluetun) —
  # their ports are published HERE, not on their own services.
  # See docs/explanation/research/gluetun-vpn-tailscale-research.md.
  gluetun:
    container_name: gluetun
    hostname: gluetun.internal
    networks:
      default:
        aliases:
          - gluetun.internal
          # Aliases moved off the routed services (they can no longer carry
          # network aliases) so existing config URLs keep resolving:
          - prowlarr.internal
          - slskd.internal
          - transmission.internal
          - flaresolverr.internal
    image: qmcgaw/gluetun:v3   # pinned major line per wiki advice; :latest = master edge
    restart: unless-stopped
    logging:
      driver: json-file
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun:/dev/net/tun
    environment:
      - VPN_SERVICE_PROVIDER=ipvanish
      - VPN_TYPE=openvpn                       # default; explicit for clarity
      - OPENVPN_USER=${OPENVPN_USER}           # IPVanish account email — in .env
      - OPENVPN_PASSWORD=${OPENVPN_PASSWORD}   # IPVanish account password — in .env
      - SERVER_COUNTRIES=${VPN_SERVER_COUNTRIES:-Netherlands}
      - DNS_ADDRESS=127.0.0.11                 # Docker DNS: routed containers can
                                               # resolve lidarr.internal etc. (§4.2)
      - TZ=${TZ}
      # - UPDATER_PERIOD=168h                  # optional: refresh IPVanish server list
      # - FIREWALL_OUTBOUND_SUBNETS=192.168.178.0/24  # only if a routed app must
      #                                             # initiate to physical LAN IPs
    ports:
      # All routed services' web/peer ports are published on gluetun:
      - "9696:9696"            # prowlarr UI
      - "5030:5030"            # slskd web UI (HTTP)
      - "5031:5031"            # slskd web UI (HTTPS, self-signed)
      - "50300:50300"          # slskd Soulseek listen port (LAN-side only;
                               # never reachable inbound through IPVanish — §5)
      - "9091:9091"            # transmission UI/RPC
      - "51413:51413"          # transmission peer port (LAN-side; see §5)
      - "51413:51413/udp"
      - "8191:8191"            # flaresolverr API — only needed for LAN/host access;
                               # prowlarr reaches it via localhost:8191 regardless
      # - "8000:8000"          # gluetun control server (optional)
```

The `*.internal` aliases moved onto gluetun deliberately: a routed service can
no longer join a network, so its old alias would vanish — putting all four
aliases on gluetun's `networks:` entry means `slskd.internal:5030` etc. keep
resolving (to gluetun's container IP, where the app is listening inside the
shared netns). Per the wiki, container-to-container access to a routed app is
`<gluetun-name>:<port>` with **no published port required** —
https://github.com/qdm12/gluetun-wiki/blob/main/setup/inter-containers-networking.md.

## 3. Routing the four services

Mechanism — `network_mode: "service:gluetun"`:
https://github.com/qdm12/gluetun-wiki/blob/main/setup/connect-a-container-to-gluetun.md.
Port publishing on routed services is a hard error ("conflicting options: port
publishing and the container type network mode"), so every `ports:`/`expose:`
entry moves to gluetun, and `networks:` must be removed entirely —
https://github.com/qdm12/gluetun-wiki/blob/main/setup/port-mapping.md and the
Compose spec (network_mode and networks are mutually exclusive;
`network_mode: "service:..."` also creates an implicit dependency so gluetun
starts first — https://docs.docker.com/compose/how-tos/startup-order/).

Per-service edits:

```yaml
  prowlarr:
    # REMOVE: networks:, hostname aliases are now on gluetun
    # REMOVE: ports: — published on gluetun
    network_mode: "service:gluetun"
    depends_on:
      gluetun:
        condition: service_healthy   # gluetun ships a HEALTHCHECK — §1.3
    # image/env/volumes unchanged
```

```yaml
  flaresolverr:
    network_mode: "service:gluetun"
    depends_on:
      gluetun:
        condition: service_healthy
    # REMOVE networks:+ports:. tmpfs stays. Now shares prowlarr's netns AND
    # egress IP — which the Prowlarr integration requires anyway
    # (flaresolverr-research.md §3: cf_clearance cookies are IP+UA bound).
```

```yaml
  slskd:
    network_mode: "service:gluetun"
    depends_on:
      gluetun:
        condition: service_healthy
    # REMOVE networks:+ports:. user:/environment:/volumes: unchanged.
    # SLSKD_SLSK_LISTEN_PORT (default 50300, slskd Dockerfile ENV) still
    # applies — but nothing can reach it inbound through IPVanish (§5).
```

```yaml
  transmission:
    network_mode: "service:gluetun"
    depends_on:
      gluetun:
        condition: service_healthy
    # REMOVE networks:+ports: (9091, 51413 tcp+udp → gluetun). Nothing else
    # needed — linuxserver/transmission has no VPN-specific requirements;
    # the peer port simply won't be reachable inbound (§5).
```

`depends_on: condition: service_healthy` waits for the tunnel, not just the
container: Compose honors `service_started` / `service_healthy` /
`service_completed_successfully` conditions —
https://docs.docker.com/compose/how-tos/startup-order/,
https://compose-spec.github.io/compose-spec/workload_spec.html#depends-on.
The wiki's "no need for depends_on" only means startup ordering is already
implied by `network_mode`; the explicit health-gated version prevents routed
apps from racing VPN establishment.

## 4. Who reaches whom after the change

### 4.1 Routed ↔ routed: localhost

All four routed services share one network namespace — they reach each other
at `127.0.0.1:<port>` and cannot bind the same port —
https://github.com/qdm12/gluetun-wiki/blob/main/setup/inter-containers-networking.md.
Consequences for this stack:

- Prowlarr → FlareSolverr proxy Host becomes `http://localhost:8191` (or
  `http://127.0.0.1:8191`). The existing `flaresolverr.internal` alias also
  still resolves *from other containers* to gluetun's IP — but inside the
  shared netns use `localhost`. Bonus: solver and Prowlarr now share the same
  egress IP, which Prowlarr's cookie replay requires
  (flaresolverr-research.md §3/§6).
- Port conflicts across the four routed apps must not exist — current ports
  (8191, 9696, 5030, 5031, 50300, 9091, 51413) are all distinct.

### 4.2 Non-routed → routed, and routed → non-routed

Per the same wiki page: a non-routed container `B` on the same Docker network
reaches routed app `A` as `gluetun:<port>` (or via the moved `*.internal`
aliases); `A` reaches `B` as `B:<port>` — supported "since v3.41". No
published ports are needed for this path, and no `FIREWALL_OUTBOUND_SUBNETS`
either (docker network is allowed by default — §1.4).

- soularr's `config.ini` `[Slskd] host_url` can stay
  `http://slskd.internal:5030` **if** the alias is moved to gluetun (§2), or
  change to `http://gluetun:5030`.
- Lidarr's download-client entry for Transmission: `gluetun` or
  `transmission.internal` host, port `9091`.
- **Caveat — DNS inside routed containers:** Gluetun rewrites
  `/etc/resolv.conf` to `127.0.0.1` (its DoT/Unbound resolver, `DOT=on`
  default); Docker's embedded `127.0.0.11` then isn't used, so routed
  containers **cannot resolve docker service names like `lidarr.internal`**
  unless gluetun is told to use Docker DNS: `DNS_ADDRESS=127.0.0.11` —
  https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/dns.md.
  This matters because routed **Prowlarr pushes indexers to Lidarr**
  (`lidarr.internal:8686`/`lidarr:8686`). `DNS_ADDRESS` is preferable to
  `DNS_KEEP_NAMESERVER=on`, which the wiki warns "will likely leak DNS
  traffic outside the VPN" (it implies `DOT=off`). Trade-off of
  `DNS_ADDRESS=127.0.0.11`: service-name resolution works and public
  lookups are forwarded by Docker's resolver — still inside the netns, so
  they egress via the tunnel — but Gluetun's own Unbound/DoT + blocklists
  are bypassed. (If you ever drop the DNS override, routed apps can only
  reach non-routed containers by static IP.)

### 4.3 LAN/host → routed: published ports on gluetun

Ports published on the gluetun service land on the Docker host exactly like
any other publish (`host:container`) —
https://github.com/qdm12/gluetun-wiki/blob/main/setup/port-mapping.md,
https://docs.docker.com/engine/network/drivers/bridge/. So
`localhost:9696`, `:5030`, `:9091` on the Mac keep working — this is also
what makes host-side `tailscale serve` viable (§6). One operational note:
adding/removing a published port means recreating gluetun's netns, i.e.
`docker compose up -d --force-recreate` on the whole gluetun group.

## 5. Inbound connectivity: there is none — and that's mostly fine

- **IPVanish forwards no ports, period.** "Due to our NAT firewall, anyone
  trying to ... require port forwarding ... will not be able to route that
  access through our VPN" —
  https://support.ipvanish.com/hc/en-us/articles/115002080173-Port-Forwarding.
- Gluetun's `VPN_PORT_FORWARDING` only supports PIA, Perfect Privacy,
  PrivateVPN and ProtonVPN — `VPN_PORT_FORWARDING_PROVIDER` choices per
  https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/port-forwarding.md
  and
  https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md.
  Setting it for ipvanish fails validation (`PortForwarding.Validate`).
- **slskd:** `soulseek.listen_port` (env `SLSKD_SLSK_LISTEN_PORT`, default
  50300 — https://github.com/slskd/slskd/blob/master/Dockerfile ENV block and
  https://github.com/slskd/slskd/blob/master/docs/config.md) can never accept
  inbound peer connections. Soulseek still functions: connections are made
  outbound to peers with open ports; firewalled-to-firewalled transfers fail.
  (The stack's own VPN note in `docs/reference/lidarr-stack.md` already
  records this; keep publishing 50300 on gluetun only for LAN uniformity —
  it does nothing through the tunnel.) If full inbound is ever wanted, the
  fix is a provider change (AirVPN static ports; PIA/Proton dynamic via
  `VPN_PORT_FORWARDING=on`) and setting `soulseek.listen_port` to match.
- **Transmission:** same story — "you _can_ get by with a closed port, but
  on average you will get much faster speeds if peers can connect to you"
  — https://github.com/transmission/transmission/blob/main/docs/Why-Are-My-Speeds-So-Slow.md.
  Outbound peer connections work; expect a smaller peer pool. No
  image-specific VPN setup needed for `lscr.io/linuxserver/transmission`.
- **Outbound-only services (prowlarr indexer calls, flaresolverr fetches,
  slskd's Soulseek server connection) are unaffected** — they're client
  connections and traverse the tunnel normally. Kill-switch coverage is the
  point: if the VPN drops, gluetun's firewall blocks egress —
  https://github.com/qdm12/gluetun-wiki/blob/main/faq/healthcheck.md.

## 6. Tailscale access to the web UIs

### Option A — Tailscale on the Mac host + `tailscale serve` (recommended)

Docs: https://tailscale.com/docs/features/tailscale-serve,
https://tailscale.com/docs/reference/tailscale-cli/serve.

`tailscale serve` reverse-proxies a localhost service to the tailnet over
HTTPS on `https://<machine>.<tailnet>.ts.net`, auto-provisioning TLS (requires
MagicDNS + HTTPS certificates enabled — https://tailscale.com/docs/use-cases/application-testing/share-local-dev-server-with-team).
Because gluetun publishes the UI ports onto the Mac host, host-level serve
works unchanged:

```sh
tailscale serve --bg --https=443  http://localhost:9696   # prowlarr -> https://<mac>.<tail>.ts.net
tailscale serve --bg --https=8443 http://localhost:5030   # slskd     -> :8443
tailscale serve --bg --https=8444 http://localhost:9091   # transmission -> :8444
tailscale serve status   # prints the mount table
```

Notes:
- One listener per port: multiple services share the hostname via distinct
  `--https=` ports, or via `--set-path` path mounting (`tailscale serve --bg
  --set-path=/slskd http://localhost:5030`) — but path mounting only works
  cleanly if the app honors a base URL, since serve strips the mount path
  before forwarding (CLI reference:
  https://tailscale.com/docs/reference/tailscale-cli/serve). Distinct ports
  are the safe default for these UIs.
- `serve` is tailnet-only (no public exposure; that would be `funnel`), and
  tailnet ACLs apply. FlareSolverr (8191) is API-only — leave it unexposed.
- Belt-and-braces option: publish gluetun's UI ports bound to loopback only
  (`"127.0.0.1:9696:9696"`) so the UIs are reachable *only* via localhost /
  tailscale serve, not the LAN.

### Option B — `tailscale/tailscale` sidecar container

Image reference: https://hub.docker.com/r/tailscale/tailscale and
https://tailscale.com/docs/features/containers/docker/docker-params;
worked example: https://tailscale.com/blog/docker-tailscale-guide.

- Env: `TS_AUTHKEY` (in `.env`), `TS_STATE_DIR=/var/lib/tailscale` (persisted
  volume — mandatory or the node re-registers every recreate),
  `TS_HOSTNAME`, `TS_SERVE_CONFIG=/config/serve.json`,
  `TS_EXTRA_ARGS=--advertise-tags=tag:container`.
- `TS_USERSPACE` defaults to `true` (userspace netstack, no `/dev/net/tun`
  needed) — https://tailscale.com/docs/concepts/userspace-networking.
- **Give it its own netns on the default compose network** and point
  `TS_SERVE_CONFIG` proxies at the routed apps *by gluetun name* — they
  listen inside gluetun's netns and are reachable at `gluetun:9696` etc.
  (§4.2). Sketch of the serve config (shape per `tailscale serve status
  --json`, documented in the docker-params page):

  ```json
  {
    "TCP": { "443": { "HTTPS": true }, "8443": { "HTTPS": true } },
    "Web": {
      "<host>.<tailnet>.ts.net:443":  { "Handlers": { "/": { "Proxy": "http://gluetun:9696" } } },
      "<host>.<tailnet>.ts.net:8443": { "Handlers": { "/": { "Proxy": "http://gluetun:5030" } } }
    }
  }
  ```

- **Do not share gluetun's netns** for this purpose: with
  `network_mode: service:gluetun`, tailscaled's outbound control/DERP/peer
  traffic is forced through the IPVanish tunnel — direct tailnet paths can't
  form and everything falls back to relays. That pattern only makes sense for
  a deliberate "tailnet exit node over commercial VPN" build (community
  example https://github.com/mhajder/ts-vpn-exit, which *requires*
  `TS_USERSPACE=true` precisely because gluetun owns `/dev/net/tun`). For
  merely reaching UIs, an own-netns sidecar (or Option A) is correct.

### Recommendation: Option A

Zero new containers, no auth-key/state management, works today because the
ports are already published on the host. Choose Option B only if you want the
whole remote-access story inside compose, or distinct tailnet node names per
service (`TS_SERVE_CONFIG` + `svc:`-style naming).

## 7. Gotchas checklist

- Routed services must drop `ports:`, `expose:` and `networks:` — Compose
  refuses otherwise (conflicting options / mutually exclusive).
- Move the four `*.internal` aliases to gluetun or update every consumer's
  URL (soularr `config.ini`, lidarr download client, prowlarr apps +
  flaresolverr proxy host).
- Routed apps resolving non-routed service names need
  `DNS_ADDRESS=127.0.0.11` on gluetun (§4.2) — else Prowlarr→Lidarr sync
  breaks with "no such host".
- `FIREWALL_OUTBOUND_SUBNETS` is only for routed→physical-LAN egress; the
  compose network needs nothing.
- Two routed containers can never share a listen port.
- `SLSKD_REMOTE_CONFIGURATION=true` exposes merged config incl. env-injected
  secrets via the API — fine on the tailnet, but don't publish 5030 more
  broadly than needed (repo note in `lidarr-stack.md`).
- Changing gluetun's `ports:` later requires `--force-recreate` of gluetun
  *and* all routed services (shared netns is rebuilt).
- Gluetun logs will show `connection refused`/`i/o timeout` in routed apps as
  *consequences* of a tunnel drop, not causes — per
  https://github.com/qdm12/gluetun-wiki/blob/main/faq/healthcheck.md.
- `.env` additions: `OPENVPN_USER`, `OPENVPN_PASSWORD` (IPVanish account),
  optionally `VPN_SERVER_COUNTRIES`, and `TS_AUTHKEY` only if Option B.

## Sources

- Gluetun wiki (github.com/qdm12/gluetun-wiki):
  - providers/ipvanish.md — OpenVPN env vars, run examples
  - setup/wireguard.md — native WireGuard provider list (no IPVanish)
  - providers/custom.md — custom OpenVPN/WireGuard incl. wg0.conf mount
  - options/vpn.md — `VPN_SERVICE_PROVIDER`, `VPN_TYPE` defaults
  - options/firewall.md — `FIREWALL_*` vars + rebinding/overlap notes
  - options/port-forwarding.md — `VPN_PORT_FORWARDING*` vars/provider choices
  - advanced/vpn-port-forwarding.md — native PF providers (no IPVanish)
  - options/dns.md — `DOT`, `DNS_ADDRESS`, `DNS_KEEP_NAMESERVER` (leak warning)
  - options/healthcheck.md + faq/healthcheck.md — health server, HEALTHCHECK,
    auto-heal
  - connect-a-container-to-gluetun.md, inter-containers-networking.md,
    port-mapping.md — `network_mode: "service:gluetun"`, localhost sharing,
    `gluetun:<port>` reachability, publishing rules
  - docker-image-tags.md — `:latest` edge vs `:v3`/release tags
- Gluetun source (github.com/qdm12/gluetun):
  - internal/configuration/settings/provider.go — WireGuard provider
    allow-list + PF validation
  - internal/provider/ipvanish/openvpnconf.go — IPVanish OpenVPN profile
  - internal/firewall/enable.go — auto-allows attached Docker subnets
  - Dockerfile — built-in `HEALTHCHECK ... /gluetun-entrypoint healthcheck`,
    EXPOSE 8000/8888/8388
  - issues #134 (WireGuard matrix: "IPVanish not supported"),
    #1909 (qdm12: docker network reachable by default)
- IPVanish support (support.ipvanish.com):
  - articles/115002080173-Port-Forwarding — NAT firewall, no port forwarding
  - articles/360024000253 — account panel (username = signup email; WireGuard
    configurator exists)
  - articles/360042284673 — manual OpenVPN setup uses account credentials
- Docker docs: docs.docker.com/compose/how-tos/startup-order (depends_on
  conditions; network_mode implies ordering), compose-spec.github.io
  workload spec, docs.docker.com/engine/network/drivers/bridge
- slskd (github.com/slskd/slskd): Dockerfile ENV (`SLSKD_SLSK_LISTEN_PORT=50300`,
  `SLSKD_HTTP_PORT=5030`, `SLSKD_HTTPS_PORT=5031`, built-in HEALTHCHECK),
  docs/config.md, docs/docker.md
- Transmission: github.com/transmission/transmission docs/
  Why-Are-My-Speeds-So-Slow.md ("port is closed" = outbound only),
  docs/Port-Forwarding-Guide.md
- Tailscale: tailscale.com/docs/features/tailscale-serve,
  /docs/reference/tailscale-cli/serve (--https/--http/--tcp/--set-path/--bg),
  /docs/features/containers/docker/docker-params (TS_* env incl.
  TS_SERVE_CONFIG/TS_USERSPACE/TS_STATE_DIR),
  /docs/concepts/userspace-networking, /blog/docker-tailscale-guide;
  hub.docker.com/r/tailscale/tailscale
- Community (secondary, flagged as such): github.com/mhajder/ts-vpn-exit
  (tailscale-in-gluetun-netns exit-node pattern, TS_USERSPACE requirement),
  gluetun discussion #2201 (same)
- This repo: docker-compose.yml, docs/reference/lidarr-stack.md,
  soularr/config.ini.example, slskd/slskd.yml.example,
  docs/explanation/research/flaresolverr-research.md
