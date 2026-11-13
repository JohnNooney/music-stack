# Spec 0003: `union_library` — one deduplicated Jellyfin library over Deemix and Lidarr

**Status:** ready-for-agent
**Labels:** `ready-for-agent`
**Glossary:** use the terms defined in `CONTEXT.md` at the repo root (library root, album folder, partial album, song, canonical copy, album artist, track artist, playlist, playlist file, trash, inventory). New terms introduced by this spec:

- **Union root**: the directory `~/Music/Jellyfin/` containing one symlink per album (plus loose-root items), the *only* directory Jellyfin scans.
- **Union entry**: one top-level entry inside the union root — a symlink to an album folder in either source tree, or to a loose root item from the Deemix library root.
- **Source tree**: either `~/Music/Deemix` (the existing library root, flat `<Album artist> - <Album>` album folders) or `~/Music/Lidarr/media/music` (Lidarr's root, `<Artist>/<Album> (<Year>)`).

**Evidence:** `docs/jellyfin-multilibrary-dedup-research.md` — Jellyfin keys every item as `MD5(type + path)` (verified at `v12.4`), so identical files at two scanned paths always appear twice; no dedupe, no audio merge-versions feature. The union root is the agreed remedy ("Option C" in §5C of that document).

## Problem Statement

Two downloaders write into two separate music trees. Deemix owns `~/Music/Deemix` (~1,571 album folders, ~4,700 audio files — the current Jellyfin library root). The Lidarr stack (Lidarr + Soularr + slskd) owns `~/Music/Lidarr/media/music` (~30 album folders, ~450 files, `Artist/Album (Year)` layout, fully MusicBrainz-tagged).

The user wants Jellyfin to also serve the Lidarr downloads, but Jellyfin cannot deduplicate: whatever is scanned becomes items, keyed by path. The trees already overlap — 8 of the 10 Lidarr artists exist in Deemix, and at least three albums are duplicated outright (`Herbie Hancock - Head Hunters`, `Willie Colón - Tiempo pa' matar`, `Eek-A-Mouse - The Mouse & The Man`), plus the Metallica catalogue as different editions. Mounting the Lidarr tree as a second folder in the existing library would put duplicate albums and tracks directly into the main Albums/Songs views; a separate library would still leak duplicates onto the 8 shared artist pages.

Separately, the union must not churn Jellyfin's database: item IDs are `MD5(type + path)`, so a wholesale path change (e.g. repointing the library at `/music/Jellyfin`) would orphan every playlist entry, favourite and play-progress record.

## Solution

Build a **union root** at `~/Music/Jellyfin/` — one symlink per album pointing into whichever source tree holds the canonical copy — and make it the only path Jellyfin scans. The union keeps the in-container path `/media` and names its Deemix-sourced entries **verbatim** after the Deemix album folders, so every existing item keeps its exact path string and therefore its ID: zero playlist/favourite/history loss, no re-migration.

When an album exists in both trees, the union entry keeps the Deemix folder's name (ID stability) but links to the **Lidarr** copy (complete releases, MusicBrainz-tagged — better provider matching). Albums that exist only in Lidarr get constructed entry names `<Artist> - <Album> (<Year>)`. Different-release overlaps (e.g. Deemix `Kill 'Em All (Remastered)` vs Lidarr `Kill 'Em All (1983)`) are not matches and both appear — they are genuinely different releases.

A new stdlib-only tool, `union_library`, builds and maintains the union root: idempotent runs, `--dry-run`, a per-run report, an overrides file for matches the normalizer can't settle, and pruning of links whose targets vanished. Docker-compose mounts the union root at `/media` plus the two source trees read-only at sibling paths (`/Deemix`, `/Lidarr`) purely so the relative symlinks resolve inside the container.

## User Stories

1. As a listener, I want each album to appear exactly once in Jellyfin, so that browsing Albums isn't polluted by duplicate copies from two downloaders.
2. As a listener, I want the full-length Lidarr copy of `Head Hunters` shown instead of the one-song Deemix partial album, so that I hear the whole album.
3. As a listener, I want different releases of the same record (original vs remaster) to remain separate albums, so that I can still choose between editions.
4. As a listener, I want my existing Jellyfin playlists, favourites and play progress untouched by the switch, so that the union change is invisible beyond removing duplicates.
5. As a listener, I want new Lidarr/Soularr downloads to appear in Jellyfin after a union rebuild and rescan, so that the library grows on its own.
6. As a listener, I want album art and `.lrc` sidecars from whichever copy was chosen to keep working, so that lyrics and covers don't regress.
7. As a listener, I want the Deemix root's loose items (playlist files, notes files) to keep being scanned exactly as today, so that no current behaviour silently disappears.
8. As the maintainer, I want `union_library --dry-run` to show every link it would create, every link it would retarget (Deemix → Lidarr), every entry it would prune, and every ambiguous match — before anything changes.
9. As the maintainer, I want ambiguous matches reported rather than guessed, so that the tool never hides the wrong copy by accident.
10. As the maintainer, I want an overrides file where I can force a match, force keep-both, or force the Deemix side for a specific album, so that fuzzy cases resolve deliberately and persist across runs.
11. As the maintainer, I want the winning copy's name but the existing entry's identity, so that an album that flips from Deemix to Lidarr keeps its Jellyfin item ID and playlist references.
12. As the maintainer, I want links to use relative targets (`../Deemix/…`, `../Lidarr/…`) that resolve both on the host and inside the container, so that the union root is browsable and scriptable outside Docker too.
13. As the maintainer, I want each run to be idempotent — a union already in the desired state produces an empty plan — so that the tool is safe to run routinely.
14. As the maintainer, I want entries whose targets have disappeared (album deleted or renamed at source) pruned and reported, so that the union never rots.
15. As the maintainer, I want a written report per run listing links created, retargeted, pruned, ambiguous, overridden and errored, so that one glance shows union health.
16. As the maintainer, I want symlink creation and pruning to be the only filesystem effects — no file is ever moved, copied, retagged or deleted in either source tree.
17. As the maintainer, I want the tool to be runnable manually after downloads land, without a daemon or watch mode, so that it stays a plain repo tool.
18. As the maintainer, I want the compose change confined to the jellyfin stack (union root → `/media`; `~/Music/Deemix` → `/Deemix:ro`; `~/Music/Lidarr` → `/Lidarr:ro`), leaving `PathInfos` at `/media` and the lidarr-stack compose untouched.
19. As the maintainer, I want slskd's shares (`/data/music`, `/deemix`) unaffected — the union root is never mounted into or shared by slskd — so that Soulseek sharing is unchanged.
20. As the maintainer, I want a post-switch verification step (rescan, then confirm item counts and spot-check playlists) documented in the report/docs, so that the first cutover proves ID preservation worked.
21. As a future session, I want an ADR recording the union decision (path-keyed IDs ⇒ mount-at-`/media` constraint, Lidarr-wins precedence) and a docs page for the tool, so that the layout's invariants are discoverable.
22. As the maintainer, I want the tool stdlib-only, tested through `main(argv)` on real temp trees with unittest and strict mypy, matching `reorganize_playlists` conventions.

## Implementation Decisions

- **Union root and entry model.** Default union root `~/Music/Jellyfin` (flag `--union`). Flat top level: each union entry is one album folder's canonical copy. No artist level — the union mirrors the flat `Artist - Album` vocabulary the existing library already uses.
- **Entry naming.** An album that exists (or matched) in the Deemix tree keeps that Deemix album folder's name **verbatim** — this is what preserves item IDs. An album present only in the Lidarr tree gets a constructed name `<Artist> - <Album> (<Year>)` from its `Artist/Album (Year)` path segments. Name collisions between a constructed Lidarr name and an existing union entry are reported and skipped, never overwritten.
- **Link mechanism.** Symbolic links with **relative** targets of the form `../Deemix/<Album artist> - <Album>` and `../Lidarr/media/music/<Artist>/<Album> (<Year>)`. These resolve identically on the host (`~/Music/Jellyfin/../Deemix`) and in the container (`/media/../Deemix`) given the mounts below. Absolute host paths are forbidden (they'd be broken inside the container). Jellyfin follows such links and keeps the *link* path as the item `Path` (research doc §5C, `ManagedFileSystem` at `v12.4`) — this is the property ID preservation rests on.
- **Compose/mount change (jellyfin repo `docker-compose.yml`).** Replace the `~/Music/Deemix → /media` bind with three mounts: `~/Music/Jellyfin → /media`, `~/Music/Deemix → /Deemix:ro`, `~/Music/Lidarr → /Lidarr:ro`. The library's `PathInfos` stays `/media` — no Jellyfin config change. The lidarr-stack compose and slskd shares are untouched.
- **Overlap matching.** Match keys are `normalized(album artist) + normalized(album)` per tree. Deemix keys come from album-folder names split on ` - `; Lidarr keys come from its `Artist/Album (Year)` two-level path. Normalization: NFC, case-folded, punctuation stripped, whitespace collapsed (same style as the repo's existing `_normalise_words`), **plus a trailing `(\d{4})` group stripped from the album part** (Lidarr always appends the year; Deemix doesn't).
- **Precedence.** On a single confident match, the union entry keeps the Deemix name and targets the Lidarr dir (Lidarr wins on content quality; Deemix wins on naming). Non-matching entries from both trees are linked as-is. A Deemix name that matches *more than one* Lidarr candidate after normalization (e.g. `Asalto navideño (1972)` and `Asalto navideño (1992)` collapse to one key) is **ambiguous**: reported, and the union keeps the Deemix target (status quo) until an override decides.
- **Overrides file.** A small text file (`--overrides`, default `union_library_overrides` next to the tool or under the union root's parent — implementer's call, documented in the tool's docs page) with one directive per line: `match <deemix-name> = <lidarr-artist>/<lidarr-album>` (force dedupe, Lidarr target), `prefer-deemix <deemix-name> = <lidarr-artist>/<lidarr-album>` (force match but keep Deemix target), `keep-both <deemix-name> = <lidarr-artist>/<lidarr-album>` (suppress the dedupe and emit both entries). Unknown entries in the file are reported as unused, not silently ignored.
- **Loose-root mirroring.** Every top-level entry of the Deemix library root that is *not* an album folder matched elsewhere (root-level `.m3u8`/`.m3u`/`.txt`/`.json`/`.tsv` files, `.gitignore`, stray dirs) is symlinked into the union root verbatim — today's scan behaviour is preserved bit-for-bit. A small built-in exclude list covers clearly-internal dirs (e.g. `Config/`, `_duplicates_trash/`, `Deemix-trash/`) if present; the list is a flag-extendable constant, and the report shows what was excluded.
- **Pruning.** A union entry whose target no longer exists is removed and reported under "Pruned dangling links". A union entry that exists but isn't part of the current plan (e.g. hand-added) is left alone and reported under "Foreign entries (untouched)" — the tool owns only the links it creates.
- **Idempotence and effects.** Re-running on an unchanged world yields an empty plan. The only filesystem effects are `symlink`/`unlink` inside the union root. No source-tree mutation, no Jellyfin API calls, no tag reads or writes — the tool is a pure directory-matching script, so it needs neither `deezer` nor `jellyfin` clients.
- **Report sections (order):** `Linked (new)`, `Relinked (Deemix → Lidarr)`, `Ambiguous matches (kept Deemix)`, `Overridden`, `Loose-root items mirrored`, `Excluded`, `Foreign entries (untouched)`, `Pruned dangling links`, `Failed actions`. Ends with a reminder to rescan the Jellyfin library.
- **CLI.** `union_library` with `--union`, `--deemix`, `--lidarr`, `--overrides`, `--dry-run`, matching the repo's run conventions (plan → report → execute; dry-run is the safety default posture, per the repo's "dry-run first" culture for tools that touch the library).
- **Verification note in docs.** First cutover: build union → `docker compose up -d` with new mounts → trigger a library scan → confirm (a) item counts unchanged for existing albums, (b) the three known duplicate albums now show once, (c) playlists still resolve. Documented as a short runbook step in the tool's docs page.

## Testing Decisions

- **Same seam philosophy as the suite, simpler shape:** `main(argv)` against **real temp source trees** — build a fake `Deemix/` and `Lidarr/media/music/` plus an empty union dir in tmp, run the tool, observe the union dir's links (existence, link targets, relative-path correctness), report text, and (for live runs) actual symlinks on disk. No `deezer`/`jellyfin` fakes are needed — the tool makes no API calls; a test asserts the plan contains only fs operations.
- **Assertions observe outcomes, not internals:** link presence/absence and `os.readlink` targets, broken-link pruning on real dangling links, dry-run produces zero fs changes, second run produces an empty plan, override directives change which target a matched entry gets.
- **Prior art:** `tests/support.py` and `tests/test_migrate_files.py` in `reorganize_playlists` (real tmp trees, report-text assertions, `run_tool` helper). Fixture dirs need no real audio — empty files suffice; the tool never opens file contents.
- **Coverage sketch:** new album in each tree → correct link + name; overlap with confident match → Deemix name, Lidarr target; remaster-style name difference → both kept; multi-candidate ambiguity (`Asalto navideño`) → reported, Deemix kept, override resolves both ways; constructed Lidarr name colliding with an existing entry → skipped + reported; loose root files mirrored verbatim; exclude list honoured; dangling link pruned; foreign entry untouched + reported; unused override reported; dry-run/no-op; idempotent rerun.
- **Normalization unit surface:** exercised *through* the CLI using crafted folder names (case/diacritic/punctuation/year variants) — no separate unit-test seam.

## Out of Scope

- **Song-level dedupe** — the union chooses per *album folder*, not per song. A partial Deemix album whose missing tracks exist in a Lidarr release is wholly replaced by the Lidarr release (the desired behaviour), not merged track-by-track.
- **Deleting or merging real duplicate files** — the union only *hides* the non-canonical copy from Jellyfin. Any disk-space reclamation or upstream consolidation (making Lidarr's tree canonical, importing the Deemix tree into Lidarr) is a separate decision ("Option D" in the research doc).
- **The `Ryo Fukui, 福居良` vs `福居良` artist-name split** — a pre-existing tag/naming divergence between sources; Jellyfin artists are name-keyed, so this split persists until one side is retagged. Same class of problem as spec 0002's artist-alias cases; deliberately not here.
- **slskd share topology** — shares stay pointed at the two real trees; Soulseek will keep seeing both namespaces (status quo). Presenting a deduped share namespace is a separate change with its own symlink-following caveats.
- **Scheduling/automation** — v1 is manual runs. A launchd job or running the tool before scheduled Jellyfin scans is a trivial follow-up once the tool proves out.
- **Realtime Jellyfin refresh** — Docker Desktop file-event propagation is unreliable; the workflow already assumes scheduled scans.
- **Track-level metadata or tag changes** — the tool never opens file contents; tags are the retag tool's domain.
- **Rollback machinery** — symlinks are self-describing and recreatable; a manifest/trash system like `reorganize_playlists`'s is unnecessary. The per-run report is the audit trail.

## Further Notes

- Scale: ~1,571 Deemix album folders + ~30 Lidarr album folders; three confirmed duplicate albums and one artist-name split. First live run should create ~1,600 links and retarget ~3.
- The known duplicates are the live acceptance check: `Head Hunters` (Deemix 1-track partial → Lidarr full), `Tiempo pa' matar`, `The Mouse & The Man`. The Metallica pairs (`(Remastered)` vs `(1983)`-style names) must *not* match — they validate the normalization isn't too aggressive.
- ID preservation is the load-bearing assumption: it holds only if Jellyfin stores `Path` as the *link* path, which the research doc verifies at `v12.4` (`ManagedFileSystem` keeps `FullName` = link path). The post-cutover verification step exists to catch any regression in this assumption cheaply — worst case, everything still works but with new item IDs and one clean rescan.
- Nice side effect of Lidarr-wins on `Head Hunters`: the winning Lidarr dir also contains `01 - Chameleon.flac`, so even the *track* item ID survives; tracks 02–04 simply appear as new items under the same album entity.
- If a future migration makes the union the canonical library (Option D), the union root's flat `Artist - Album` naming keeps it compatible with Deemix paths; nothing here precludes that direction.
