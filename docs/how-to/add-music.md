# How to add music via the Lidarr stack

Get an artist's albums downloaded through the Soulseek/torrent pipeline once the
stack is wired ([wire-lidarr-stack.md](wire-lidarr-stack.md)).

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

## What "failure" looks like (it's usually fine)

- `Download error. Requeue file` / `reported as failed by the remote user`
  in Soularr/slskd logs = an individual **peer** rejected or dropped the
  transfer. Normal on Soulseek. Soularr requeues and tries other sources.
- `Failed to grab` for an album = that search result was a dead end; Soularr
  moves to the next result next cycle.
- `No releases wanted` = the wanted list is empty — either everything's
  downloaded, or albums aren't monitored (see step 2 above).
- `stalled_timeout = 3600` in `config.ini` controls how long Soularr waits on
  a stalled album before giving up on it.

Verify Soulseek connectivity: the slskd UI should show *Connected* to
`vps.slsknet.org`, and `docker logs soularr` should show grabs rather than
`NameResolutionError` or 401/403 (401 = wrong API key).
