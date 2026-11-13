# ADR 0004: A union root of relative symlinks is the only path Jellyfin scans

**Status:** accepted (2026-11-13) · **Spec:** [0003](../specs/0003-union-library-for-deemix-and-lidarr.md) · **Evidence:** [jellyfin-multilibrary-dedup-research.md](../jellyfin-multilibrary-dedup-research.md)

## Context

Two downloaders write into two trees: Deemix owns `~/Music/Deemix` (flat `<Album artist> - <Album>` folders, the current library root) and the Lidarr stack owns `~/Music/Lidarr/media/music` (`<Artist>/<Album> (<Year>)`, MusicBrainz-tagged). Jellyfin cannot deduplicate: every item is keyed `MD5(type + path)` (verified at v12.4), so an album reachable at two scanned paths appears twice. The trees already overlap (`Head Hunters`, `Tiempo pa' matar`, `The Mouse & The Man`).

The same path-keyed IDs make the naive fix expensive: repointing the library at a new root would change every item's `Path` and orphan every playlist entry, favourite and play-progress record.

## Decision

1. **The library is a union root**, `~/Music/Jellyfin/`, holding one entry per album — a **relative symlink** into whichever source tree holds the canonical copy (`../Deemix/<Album artist> - <Album>`, `../Lidarr/media/music/<Artist>/<Album> (<Year>)`), plus verbatim links for the Deemix root's loose items. `union_library` builds and maintains it; see [docs/union_library.md](../union_library.md).
2. **The union mounts at `/media`**, the path Jellyfin already scans (`PathInfos` unchanged), and Deemix-sourced entries keep the Deemix folder's name **verbatim**. Every existing item keeps its exact path string and therefore its ID — no playlist/favourite/history loss. This works because Jellyfin keeps the *link* path as the item `Path` (`ManagedFileSystem` at v12.4). The source trees mount read-only at `/Deemix` and `/Lidarr` purely so the relative targets resolve inside the container too.
3. **Lidarr wins on content, Deemix wins on naming.** When an album exists in both trees (normalised artist + album, trailing year stripped), the union entry keeps the Deemix name but links to the Lidarr copy — complete releases, MusicBrainz tags. Different releases (`Kill 'Em All (Remastered)` vs `Kill 'Em All (1983)`) never match. Multi-candidate matches are ambiguous: reported, Deemix kept, settled by a `union_library_overrides` directive.
4. **The union only ever hides copies.** The tool's only filesystem effects are `symlink`/`unlink` inside the union root; neither source tree is moved, copied, retagged or deleted. Consolidating onto one tree (Option D in the research doc) remains a separate decision.

## Consequences

- Run `python3 -m union_library` (dry-run first) after Lidarr/Soularr or Deemix downloads land, then scan in Jellyfin. There is no daemon — scheduled scans pick up the union as-is.
- Adding a third source tree, or pointing the library at anything but `/media`, breaks the ID-preservation invariant in point 2. Do not do it without re-reading this ADR and the research doc.
- Deleting or renaming an album at source leaves a dangling link; the next run prunes and reports it. Hand-added union entries are foreign: reported, never touched.
- slskd's shares stay pointed at the two real trees; Soulseek sharing is unchanged.
