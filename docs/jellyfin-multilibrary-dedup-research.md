# Does Jellyfin deduplicate songs across multiple folders or libraries?

Research date: 2026-11-13. Server source inspected at `jellyfin/jellyfin` tag
[`v12.4`](https://github.com/jellyfin/jellyfin/releases/tag/v12.4) (commit
[`83d0d0e`](https://github.com/jellyfin/jellyfin/commit/83d0d0e7f76e23e2e085c8ff67d28b772d35967d)),
the release behind the pinned `jellyfin/jellyfin:12.4` image in
[`docker-compose.yml`](../docker-compose.yml) (§7). Question context: adding the Lidarr tree
(`/Users/john/Music/Lidarr/media/music`, layout `Artist/Album (Year)`) to a Jellyfin server that
already scans `/Users/john/Music/Deemix` (flat `Artist - Album/` album folders) — ~8 overlapping
artists, at least 3 identically-named albums plus Metallica edition differences.

> **TL;DR — No dedupe, anywhere.** Jellyfin keys every library item's ID on `MD5(Type.FullName +
> Path)` (§1), so a recording that exists at two different paths is **two items**, always — whether
> the paths are in two libraries or two folders of one library. Nothing looks at file content,
> tags, or MusicBrainz IDs for identity. **Albums are per-folder entities**, so the same album in
> two folders appears twice in the Albums/Songs views; **artists are global name-keyed entities**,
> so a shared artist name shows both copies on its artist page *even across separate libraries*
> (maintainer-confirmed design flaw, §2–§3). The "multiple versions"/merge feature is **video-only**
> (§3.3), and there is no fingerprinting or duplicate-finding in the server (§4). The only way to
> show each recording once is to make it reachable at **exactly one scanned path** — practically:
> keep the Lidarr tree in a *separate* library if occasional artist-page doubles are acceptable
> (Albums/Songs views stay clean), or build a **host-side union directory** (relative symlinks or
> APFS clones, one entry per album) and point one library at only that (§5). Adding the Lidarr
> folder as a *second folder of the existing library* is the worst option: it puts the duplicates
> in the same library's own Albums/Songs views too.

---

## 1. Q1 — How a scanned song's identity is keyed: `MD5(Type.FullName + Path)`

Every file-backed item gets its `Id` deterministically from its **path string and concrete type**
— nothing else participates:

- `ResolverHelper.SetInitialItemValues` assigns
  `item.Id = libraryManager.GetNewItemId(item.Path, item.GetType())` for every resolved item
  ([`ResolverHelper.cs` L36 and L76](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/Library/ResolverHelper.cs#L36)).
- `LibraryManager.GetNewItemIdInternal` builds `key = type.FullName + key` and returns `key.GetMD5()`
  ([`LibraryManager.cs` L792-817](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/Library/LibraryManager.cs#L792-L817)).
  The key is lowercased unless `EnableCaseSensitiveItemIds` is set — so **case-only path variants
  still collide to one item**, but any other difference in the path string (different mount,
  different folder, symlink path vs real path) produces a different `Id`.
- Embedded tags and provider IDs are *metadata*, not identity: `AudioFileProber` reads
  `ALBUM`/`ARTIST`/`ALBUMARTIST`/MusicBrainz IDs onto the item's fields after resolution
  (see [jellyfin-music-metadata-research.md](jellyfin-music-metadata-research.md) §1;
  [`AudioFileProber.cs` L486-540](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Providers/MediaInfo/AudioFileProber.cs#L486-L540)).
  Two bit-identical, identically-tagged files at two paths = two `Audio` rows.
- The DB stores `Path` with a **non-unique** index (`HasIndex(e => e.Path)`), primary key `Id`
  ([`BaseItemConfiguration.cs` L36](https://github.com/jellyfin/jellyfin/blob/v12.4/src/Jellyfin.Database/Jellyfin.Database.Implementations/ModelConfiguration/BaseItemConfiguration.cs#L36))
  — nothing enforces content uniqueness.
- `IsShortcut` only recognizes `.mblink`-style files via `IShortcutHandler` extensions
  ([`ManagedFileSystem.cs` L56-77](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/IO/ManagedFileSystem.cs#L56-L77));
  a POSIX symlink is resolved by the OS, but the item keeps the **link path** as its `Path`
  (`FileSystemMetadata.FullName = info.FullName`),
  so the same inode reachable at two paths is also two items.
- One edge consequence: the *same literal path* added to two libraries collapses to the *same* item
  (same `Id`) — path-keyed IDs don't know which library scanned them. Access/ownership of that
  shared item is then ambiguous (this class of bug is live: §2, issue #12764).
- Corollary for this repo's tools: **moving a file = new Id**. Play state, favorites and playlist
  membership ride on `ItemId`, so a path change orphans them (playlist `LinkedChild` resolution is
  itself path-based:
  [`ItemPersistenceService.cs` L567-634](https://github.com/jellyfin/jellyfin/blob/v12.4/Jellyfin.Server.Implementations/Item/ItemPersistenceService.cs#L567-L634)).

## 2. Q2 — Two separate libraries scanning overlapping content: no dedupe

Nothing in the scan dedupes items across (or within) libraries — each path gets its own item row,
tied to its library root via `TopParentId`/ancestor tables. What does leak across libraries is
the **artist entity**, because artists (and genres/persons/studios) are global, name-keyed items:

- `LibraryManager.GetArtist(name)` → `CreateItemByName<MusicArtist>` →
  `GetItemByNameId<MusicArtist>(MusicArtist.GetPath(name))`
  ([`LibraryManager.cs` L1333-1345, L1370-1394](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/Library/LibraryManager.cs#L1333-L1394)),
  and `MusicArtist.GetPath` is a *program-data* path derived from the normalized **name**
  ([`MusicArtist.cs` L174-178](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Entities/Audio/MusicArtist.cs#L174-L178)).
  Same artist name anywhere → one artist entity, regardless of library.
- Maintainer statement (gnattu, Jellyfin member,
  [issue #12976 comment](https://github.com/jellyfin/jellyfin/issues/12976#issuecomment-2459921309)):
  *"Artists are global but albums are 'inside libraries' but the 'physical path in filesystem' of
  the artist is once again a path under a library folder. It is designed this bad"* — no migration
  plan. Same comment thread: these are *"design flaws inherited from emby"*.
- Live evidence, all open at research time:
  - [#12764](https://github.com/jellyfin/jellyfin/issues/12764) — two music libraries, one shared
    artist name → **all albums shown twice** on the artist page, plus artist-page access-control
    breakage between users owning different libraries. Confirmed on 10.10/10.11.
  - [#17215](https://github.com/jellyfin/jellyfin/issues/17215) — artist view aggregates albums
    from *all* Music libraries the user can access (10.11.11); reporter notes it also makes
    artist-page shuffle pick up duplicates.
  - [#10486](https://github.com/jellyfin/jellyfin/issues/10486) — separate FLAC/MP3 libraries:
    Artists/Album-Artists views show albums from **both** libraries; Albums/Songs views stay scoped.
  - [#11890](https://github.com/jellyfin/jellyfin/issues/11890) — same-named artist in multiple
    libraries: duplicates appear in Artist/AlbumArtist/Genre views only — *"the extraneous albums
    do not appear in any other views (i.e. Albums and Songs)"*.

**Net:** separate libraries do *not* dedupe, but they do *contain* the duplication: the default
**Albums and Songs** views are library-scoped and stay clean, while **Artist, Album Artist and
Genre** views are global and will show both copies for the 8 shared artists. There is no
cross-library merge of albums or tracks.

## 3. Q3 — Two folders inside ONE music library

### 3.1 Same recording in two scanned folders → two tracks, two albums

- Every directory that directly contains audio files becomes its own `MusicAlbum` entity, purely
  by directory — verified at v12.4 in
  [jellyfin-music-metadata-research.md](jellyfin-music-metadata-research.md) §4
  ([`MusicAlbumResolver.cs`](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/Library/Resolvers/Audio/MusicAlbumResolver.cs)).
  Official contract: *"one folder containing one and only one album"*
  ([docs](https://jellyfin.org/docs/general/server/media/music)).
- `Audio.AlbumEntity => FindParent<MusicAlbum>()`
  ([`Audio.cs` L61](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Entities/Audio/Audio.cs#L61))
  — album membership is the physical parent folder. There is **no** album-name/AlbumArtist/
  MusicBrainzAlbumId-based merge of `MusicAlbum` entities anywhere in the resolver or metadata
  service; `AlbumMetadataService` only renames/annotates the folder-derived album from child tags.
- So `Deemix/Herbie Hancock - Head Hunters/` and `Lidarr/.../Herbie Hancock/Head Hunters (1973)/`
  become **two `MusicAlbum` items** — both listed in the Albums view (same display name), and each
  track exists as two `Audio` items in the Songs view. Both appear under the single global
  "Herbie Hancock" artist.
- Extra wrinkle for this exact setup: Lidarr's `Artist/` level resolves as a *folder-based*
  `MusicArtist` (path-keyed, `IsAccessedByName=false`), while Deemix's flat layout produces only
  *by-name* artists — so a shared artist can show up **twice as an artist** too (folder-artist +
  name-artist entities), the live bug in
  [#12976](https://github.com/jellyfin/jellyfin/issues/12976) (reopened, unfixed in 12.4).
- Multiple library **root paths** are allowed —
  [docs](https://jellyfin.org/docs/general/server/libraries): *"You can add multiple paths that
  will all be shown under the same library."* Jellyfin only dedupes roots that are literal
  sub-paths of another root (`NormalizeRootPathList` logs "Found duplicate path" and drops the
  nested one —
  [`LibraryManager.cs` L1009-1030](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/Library/LibraryManager.cs#L1009-L1030)).
  Distinct trees are scanned fully, duplicates and all.
- The only *folder-level* merge for audio is **multi-disc**: an album folder may contain disc
  subfolders (`cd`, `disc`, `disk`, `vol`, `volume`, `part`, `act` …,
  [`NamingOptions.cs` L182+](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Naming/Common/NamingOptions.cs#L182);
  [`AlbumParser.IsMultiPart`](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Naming/Audio/AlbumParser.cs#L34);
  [`MusicAlbumResolver.ContainsMusic` disc check](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/Library/Resolvers/Audio/MusicAlbumResolver.cs#L125-L180)).
  Putting a second copy under a `Disc 2/`-style subfolder would merge it into *one album entity
  with a doubled track list* — technically legal, but it's presenting false disc metadata; not a
  real dedupe.

### 3.2 "Multiple versions" is video-only

- `POST /Videos/{id}/MergeVersions` filters the input with `.OfType<Video>()` and relinks via
  `PrimaryVersionId`/`LinkedAlternateVersions`
  ([`VideosController.cs` L183-253](https://github.com/jellyfin/jellyfin/blob/v12.4/Jellyfin.Api/Controllers/VideosController.cs#L183-L253)).
- Automatic same-folder version detection lives on `Video` (`LocalAlternateVersions`,
  `PrimaryVersionId`, [`Video.cs` L45-49, L434-442](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Entities/Video.cs#L45-L49)).
  `BaseItem.CreatePresentationUniqueKey` returns the item's own `Id`
  ([`BaseItem.cs` L863-866](https://github.com/jellyfin/jellyfin/blob/v12.4/MediaBrowser.Controller/Entities/BaseItem.cs#L863-L866));
  only `Video` overrides it to collapse onto `PrimaryVersionId`.
- Query-side version collapsing (`GroupByPresentationUniqueKey`) is explicitly restricted to
  `Episode/Video/Movie/MusicVideo/Series/Season` — **`Audio` is not in the list**
  ([`BaseItemRepository.cs` L188-226](https://github.com/jellyfin/jellyfin/blob/v12.4/Jellyfin.Server.Implementations/Item/BaseItemRepository.cs#L188-L226)).
- `AudioBook` has the alternate-version plumbing *commented out*
  ([`AudioResolver.cs` L196-212](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/Library/Resolvers/Audio/AudioResolver.cs#L196-L212)).
- Docs: *"Jellyfin supports multiple versions of the same video for movies and episodes"* — no
  audio equivalent ([movies docs](https://jellyfin.org/docs/general/server/media/movies#multiple-versions)).

## 4. Q4 — Built-in or plugin dedupe: none

- No audio fingerprinting anywhere in the server: the v12.4 source tree has **no** AcoustID /
  Chromaprint / fingerprint code (tree-wide search), and MusicBrainz integration is a metadata
  provider, not an identity check.
- No merge/dedupe API for `Audio`/`MusicAlbum`; the video merge endpoint can't take audio IDs (§3.2).
- Official feature tracker: [features.jellyfin.org #2837 "Deduplicate files"](https://features.jellyfin.org/posts/2837/deduplicate-files)
  (open, 15 votes) — the requester describes symlinking one album into several artist folders:
  *"Jellyfin correctly follows the links and finds the albums, but it ends up duplicating them.
  I would like it to merge them."* — confirms both that symlinks are followed and that nothing merges.
- A folder-merge request was rejected: [#7711](https://github.com/jellyfin/jellyfin/issues/7711),
  maintainer cvium: *"you can use something like mergerfs to join multiple drives to one 'virtual'
  drive. But this is a feature request and one I do not believe makes sense … we do not want to
  add the extra complexity."*
- Community tools exist for **video** only (e.g. `tremby/jellyfin-find-duplicates` for episodes,
  `MadFra/Jellyfin-Duplicate-Finder` for movies) — no music dedupe plugin was found; the
  awesome-jellyfin list has none either.

## 5. Q5 — Practical options for this setup

### Option A — Lidarr tree as a second folder in the existing "Music" library: simplest, worst display

Mount `/Users/john/Music/Lidarr/media/music` → e.g. `/lidarr`, add `/lidarr` as a second path on
the existing library (supported: [libraries docs](https://jellyfin.org/docs/general/server/libraries)).
Result: every duplicated album/track appears **twice in the same library's Albums/Songs views**
(§3.1), plus a possible doubled *artist* entry for Lidarr's `Artist/` folders vs the by-name
artists (#12976), plus two more artist-name splits that already exist in data (`Ryo Fukui, 福居良`
vs `福居良` — name-keyed artists are literal-string keyed, so these stay separate regardless of
layout). Playlists keep working but pick whichever item you added.

### Option B — Lidarr tree as a separate Jellyfin library ("Music (Lidarr)"): least-bad stock option

- Albums/Songs views are scoped per library → each library's browse views show only its own copy
  (#11890: extraneous albums do **not** appear in Albums/Songs views).
- Artist / Album Artist / Genre views are global → for the 8 shared artists, the artist page
  shows both copies' albums and artist-page shuffle can hit both (#12764, #17215 — both open in
  10.11/12.x era).
- Playlists/user-data unaffected; you can also deny user access per library — but note the
  access-control quirk from #12764 (the shared artist entity is owned by one library's page URL).
- Non-overlapping Lidarr artists (the 2 without Deemix presence) just work.

### Option C — host-side union directory, one library, zero duplicates (recommended if dupes matter)

The only way to get a single clean library: make each album reachable at **one scanned path**.

- Build e.g. `/Users/john/Music/Jellyfin/` containing one entry per album — a **relative symlink**
  (`ln -s ../Deemix/"X - Y"` / `ln -s "../Lidarr/media/music/A/B (Year)"`), or file-level
  hardlinks / APFS clones (`cp -c`, already this repo's copy idiom, ADR-0003) for the album
  contents. For albums present in both trees, link **only one** copy (pick canonical: e.g. Lidarr
  wins where it has the release — it's MusicBrainz-tagged — else Deemix).
- Bind-mount `/Users/john/Music` → `/music` and set the library's sole path to `/music/Jellyfin`.
  **Relative** symlink targets resolve identically on host and in-container; absolute host paths
  (`/Users/john/...`) would be broken links inside the container — don't use them.
- Evidence Jellyfin follows symlinks fine on 12.4:
  - enumeration uses `EnumerateFileSystemInfos` with `AttributesToSkip = 0` — reparse points are
    not skipped ([`ManagedFileSystem.cs` L633-641, L718-726](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/IO/ManagedFileSystem.cs#L633-L641));
    `GetFileSystemMetadata` resolves `LinkTarget` for size/mtime but **keeps the link path** as
    `FullName` ([L240-284](https://github.com/jellyfin/jellyfin/blob/v12.4/Emby.Server.Implementations/IO/ManagedFileSystem.cs#L240-L284));
  - the feature request at features.jellyfin.org #2837 confirms links are followed (and duplicated);
  - broken symlinks are skipped, not fatal, since PR
    [#8521](https://github.com/jellyfin/jellyfin/pull/8521) (fixed #8074, #4934; #9849 tracked the
    same). A 10.11.1 regression where linked items vanished ([#15279](https://github.com/jellyfin/jellyfin/issues/15279))
    was fixed and closed; no symlink problems are open at 12.4.
- Item `Path` stays the union path (`/music/Jellyfin/...`) → stable single `Id`, single album.
- Caveats: (a) **both** source trees must stay out of the library path list or the dupes come
  back; (b) the union needs a maintenance step when Deemix/Lidarr add albums (a tiny script —
  this repo's tools could grow one); (c) macOS Docker Desktop has no union-mount for bind mounts,
  so the union must exist on the host (symlinks/hardlinks/clones), not inside compose; (d) the
  real-time monitor over Docker Desktop's shared filesystem is unreliable
  ([docker/for-mac#7246](https://github.com/docker/for-mac/issues/7246)) — rely on scheduled scans.
- Variant worth noting: because Jellyfin merges `Disc N` subfolders into one album (§3.1), a union
  could *also* expose two copies of the same album as "discs" — legal but semantically wrong;
  prefer picking one copy.

### Option D — fix it upstream (Lidarr/Deemix side), secondary

Per Servarr wiki: a Lidarr **root folder must not overlap the download client's output dir** and
should be on the **same filesystem for hardlinks/fast moves**
([settings](https://wiki.servarr.com/en/lidarr/settings#root-folders),
[quick start](https://wiki.servarr.com/lidarr/quick-start-guide)).
Lidarr **Library Import** can register an existing organized tree *without moving/copying* it
([library docs](https://wiki.servarr.com/lidarr/library)), but
[importing-existing-library](https://wiki.servarr.com/lidarr/importing-existing-library) requires
`Release Artist → Release → tracks` structure and tag-based MusicBrainz matching — the flat
`Artist - Album/` Deemix layout does not satisfy that and Lidarr would want to rename/organize it.
Realistic upstream move: treat **Lidarr's tree as canonical for anything it downloads** and stop
letting Deemix keep duplicates (dedupe once on the host, keep both pipelines), then expose the
result via Option C. Soularr's role is only download orchestration into Lidarr's `download_dir`
([Soularr README](https://github.com/mrusse/soularr)) — no bearing on the Jellyfin question.

### Recommendation

1. If a few artist-page doubles are acceptable → **Option B** (separate library; one extra bind
   mount). Albums/Songs views stay clean.
2. If the goal is *no* duplicates anywhere → **Option C** (host union dir via relative symlinks or
   APFS clones, Jellyfin sees only the union). Handles all four known overlap cases including the
   `Ryo Fukui, 福居良` vs `福居良` split-by-name issue only partially — that artist-name split needs
   retagging one side, independent of mounting.
3. Avoid Option A unless you want duplicates visible in the main library.

## 6. Answers summary

| Question | Answer |
|---|---|
| Item identity | `MD5(Type.FullName + Path)` — path-keyed; tags/MBIDs never participate (§1) |
| Dedupe across libraries | No. Artists merge globally by name; albums/tracks stay per-path → dupes on artist pages (§2) |
| Two folders, one library | No dedupe; two `MusicAlbum` entities; dupes in Albums/Songs views too (§3.1) |
| Merge/multiple-versions for audio | No — video-only (`VideosController.MergeVersions`, `GroupByPresentationUniqueKey` type filter) (§3.2) |
| Fingerprinting/dedupe feature/plugin | None in server; only open feature requests; community tools are video-only (§4) |
| Same inode at two paths (links/bind) | Two items — `Path` is the scanned string (§1, §5C) |
| Clean unification | One path per recording: union dir (C) or accept artist-page dupes with separate library (B) |

## 7. Version check

- `docker-compose.yml` pins `jellyfin/jellyfin:12.4`. Docker Hub tag `12.4` was pushed
  2026-10-26 by `jellyfinbot` (amd64+arm64)
  ([Docker Hub tag API](https://hub.docker.com/v2/repositories/jellyfin/jellyfin/tags/12.4)),
  matching GitHub release
  [**Jellyfin Server 12.4** (`v12.4`)](https://github.com/jellyfin/jellyfin/releases/tag/v12.4),
  commit [`83d0d0e`](https://github.com/jellyfin/jellyfin/commit/83d0d0e7f76e23e2e085c8ff67d28b772d35967d)
  ("minor release … Update to .net 10.0.14"; the 12.x series succeeded 10.11.x).
- All file/line citations above are at tag `v12.4`. The issues cited (#12764, #17215, #11890,
  #12976) span 10.10–10.11 and remain open; the persistence layer was reworked in the 12.x series
  (`ItemPersistenceService`, `LinkedChildren` tables), which is why this note re-verified
  `ResolverHelper`/`GetNewItemId`/`GroupByPresentationUniqueKey` at `v12.4` rather than citing the
  10.11-era master commit used in
  [jellyfin-music-metadata-research.md](jellyfin-music-metadata-research.md).

## 8. Open questions / not verified

- **Exact display name/dedup of `MusicAlbum` entities with identical names in one library** —
  source shows both entities persist (path-keyed) and both list in Albums view; the web UI may
  additionally collapse same-name albums cosmetically in some client views — not verified
  client-side. Worst case assumed (two entries), consistent with #12976/#11890 reports.
- **`TopParentId` for an identical path in two libraries** — IDs collide (same path+type ⇒ same
  `Id`), but which library "owns" the shared item is a deeper edge case; avoided by never giving
  two libraries the same literal path.
- **Whether the Jellyfin realtime monitor sees Lidarr writes through the bind mount** — Docker
  Desktop file-event propagation is known-flaky; assume scheduled scans needed.
- No primary-source statement that "Jellyfin will never add dedupe" — just absence of the feature,
  a rejected folder-merge request (#7711), and maintainer comments treating the artist model as a
  known design flaw without a migration plan (#12976).
