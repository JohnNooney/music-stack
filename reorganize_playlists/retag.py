"""The `retag` command: rewrite ARTIST/ALBUM/ALBUMARTIST from Deezer so tags match album folders."""

from __future__ import annotations

from reorganize_playlists.deezer import DeezerAlbum, DeezerClient, DeezerTrack
from reorganize_playlists.executor import Executor
from reorganize_playlists.library import AudioFile, Location, normalise_words
from reorganize_playlists.migrate import Plan, Rewrite
from reorganize_playlists.progress import Progress
from reorganize_playlists.tags import read_tags

RETAGGED = "Retagged"
MISPLACED = "Misplaced (tag agrees with Deezer)"
COSMETIC = "Cosmetic differences (not rewritten)"
LOOKUP_FAILED = "Deezer lookup failed (folder fallback used / artist kept)"


def _norm(value: str) -> str:
    """Loose compare that also folds Deemix's `_` path replacer (`AC_DC` == `AC/DC`)."""
    return normalise_words(value.replace("_", ""))


def _norm_list(values: list[str]) -> list[str]:
    return [_norm(v) for v in values]


def _folder_parts(file: AudioFile) -> tuple[str, str] | None:
    """`(album artist, album)` parsed from the album folder name, when there is one."""
    if file.location is not Location.ALBUM:
        return None
    artist, sep, album = file.rel.split("/", 1)[0].partition(" - ")
    return (artist, album) if sep else None


def _misplaced(file: AudioFile, album: DeezerAlbum | None,
               folder: tuple[str, str] | None) -> bool:
    """Deezer and the `ALBUM` tag agree, but the album folder names a different album."""
    return (album is not None and folder is not None
            and _norm(file.tags.album) == _norm(album.title)
            and _norm(folder[1]) != _norm(album.title))


def _diffs(file: AudioFile, artists: list[str], album: str, album_artists: list[str]) -> list[str]:
    """Per-field `old -> new` for the fields whose stored value differs verbatim."""
    tags = file.tags
    diffs = []
    if tags.artists != artists:
        diffs.append(f"artist {'; '.join(tags.artists)!r} -> {'; '.join(artists)!r}")
    if tags.album != album:
        diffs.append(f"album {tags.album!r} -> {album!r}")
    if tags.album_artists != album_artists:
        diffs.append(f"album artist {'; '.join(tags.album_artists)!r} -> {'; '.join(album_artists)!r}")
    return diffs


def _substantive(file: AudioFile, artists: list[str], album: str, album_artists: list[str]) -> bool:
    """True when normalised values differ — case/punctuation-only differences are cosmetic."""
    tags = file.tags
    return (_norm_list(tags.artists) != _norm_list(artists)
            or _norm(tags.album) != _norm(album)
            or _norm_list(tags.album_artists) != _norm_list(album_artists))


def _resolve(file: AudioFile, deezer: DeezerClient) -> tuple[DeezerAlbum | None, DeezerTrack | None]:
    """The migration's order: barcode for the exact release, ISRC for the track (contributors)."""
    tags = file.tags
    track = deezer.lookup_track_by_isrc(tags.isrc) if tags.isrc else None
    album = deezer.get_album(f"upc:{tags.barcode}") if tags.barcode else None
    if album is None and track is not None:
        album = deezer.get_album(track.album_id)
    return album, track


def plan_retag(files: list[AudioFile], deezer: DeezerClient, progress: Progress) -> Plan:
    plan = Plan()
    sections: dict[str, list[str]] = {RETAGGED: [], MISPLACED: [], COSMETIC: [], LOOKUP_FAILED: []}
    lookups = progress.counter("Deezer lookups", len(files))
    for file in sorted(files, key=lambda f: f.rel):
        lookups.advance(file.rel)
        tags = file.tags
        album, track = _resolve(file, deezer)
        folder = _folder_parts(file)

        misplaced = _misplaced(file, album, folder)
        if misplaced:
            assert folder is not None and album is not None
            sections[MISPLACED].append(
                f"{file.rel}  (album {tags.album!r} vs folder album {folder[1]!r})")

        if album is not None:
            canon_album, canon_album_artists = album.title, [album.artist]
        elif folder is not None:
            # Folder fallback: keep tag values that already agree with the folder — the tag's
            # real character is better than the folder's mangled `_` (e.g. ':' for '_').
            canon_album = tags.album if _norm(tags.album) == _norm(folder[1]) else folder[1]
            canon_album_artists = (tags.album_artists
                                   if _norm_list(tags.album_artists) == _norm_list([folder[0]])
                                   else [folder[0]])
        else:
            canon_album, canon_album_artists = tags.album, tags.album_artists
        canon_artists = (list(track.contributors) if track and track.contributors
                         else list(tags.artists))

        diffs = _diffs(file, canon_artists, canon_album, canon_album_artists)
        line = f"{file.rel}: {'; '.join(diffs)}"
        substantive = _substantive(file, canon_artists, canon_album, canon_album_artists)
        if substantive:
            plan.ops.append(Rewrite(path=file.path, artists=canon_artists,
                                    album=canon_album, album_artists=canon_album_artists))
        if album is None or track is None:
            notes = []
            if album is None:
                notes.append("album fields from folder" if folder is not None else
                             "album fields kept (no folder fallback)")
            if track is None:
                notes.append("artist kept")
            sections[LOOKUP_FAILED].append(f"{line}  ({'; '.join(notes)})" if substantive
                                           else f"{file.rel}  ({'; '.join(notes)})")
        elif substantive:
            sections[RETAGGED].append(line)
        elif diffs and not misplaced:
            sections[COSMETIC].append(line)
    lookups.finish()

    for section, lines in sections.items():
        for line in lines:
            plan.report.add(section, line)
    return plan


def self_check(plan: Plan, executor: Executor) -> tuple[bool, str]:
    """Re-read every rewritten file: its tags must parse to the intended values, backed up in the trash."""
    problems = []
    checked = 0
    for op in plan.ops:
        if not isinstance(op, Rewrite):
            continue
        backup = executor.trash_path(op.path)
        if not backup.is_file():
            problems.append(f"no backup in the trash: {backup.relative_to(executor.trash)}")
        tags = read_tags(op.path)
        if (tags.artists, tags.album, tags.album_artists) != (op.artists, op.album, op.album_artists):
            problems.append(f"tags do not match the rewrite: {op.path.name}")
        else:
            checked += 1
    if problems:
        return False, "Self-check FAILED: " + "; ".join(problems)
    return True, f"Self-check passed: {checked} files re-read and verified"
