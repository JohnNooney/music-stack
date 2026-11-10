"""Migration file phase: plan moving every song out of legacy playlist folders into album folders."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from reorganize_playlists.deemix import DeemixSettings, TrackMeta, deemix_path
from reorganize_playlists.deezer import DeezerAlbum, DeezerClient
from reorganize_playlists import playlist_file
from reorganize_playlists.library import (
    AUDIO_EXTS, DEEMIX_CONFIG_DIR, LEGACY_PLAYLISTS_DIR, PLAYLIST_EXTS, SIDECAR_EXTS,
    AudioFile, Location, Song, nfc, rel_key, song_key,
)
from reorganize_playlists.executor import Executor
from reorganize_playlists.progress import Progress
from reorganize_playlists.report import Report
from reorganize_playlists.tags import read_art, read_tags


@dataclass(frozen=True)
class Move:
    src: Path
    dst: str  # library-relative


@dataclass(frozen=True)
class Trash:
    src: Path


@dataclass(frozen=True)
class Write:
    dst: str
    data: bytes
    replace: bool = False


@dataclass(frozen=True)
class RemoveDir:
    path: str


Op = Move | Trash | Write | RemoveDir

MOVES = "Moves"
TRASHED = "Trashed duplicate copies"
CONFLICTS = "Conflicts (different recording at the Deemix path; song left in place)"


@dataclass
class Plan:
    ops: list[Op] = field(default_factory=list)
    report: Report = field(default_factory=Report)
    final_paths: dict[str, str] = field(default_factory=dict)  # rel_key(old path) -> final rel path
    labels: dict[str, str] = field(default_factory=dict)  # final rel path -> "Artist - Title"


def lookup_album(file: AudioFile, deezer: DeezerClient) -> DeezerAlbum | None:
    """The exact release first (Deemix writes its UPC as BARCODE), else the album Deezer gives for the ISRC."""
    tags = file.tags
    album = deezer.get_album(f"upc:{tags.barcode}") if tags.barcode else None
    if album is None and tags.isrc:
        track = deezer.lookup_track_by_isrc(tags.isrc)
        album = deezer.get_album(track.album_id) if track else None
    return album


def track_meta(file: AudioFile, album: DeezerAlbum | None) -> TrackMeta:
    tags = file.tags
    track = tags.track_number or 1
    disc = tags.disc_number or 1
    if album is not None:
        return TrackMeta(title=tags.title, artist=tags.artist, album=album.title, album_artist=album.artist,
                         track_number=track, track_total=album.track_total,
                         disc_number=disc, disc_total=album.disc_total, isrc=tags.isrc)
    return TrackMeta(title=tags.title, artist=tags.artist, album=tags.album,
                     album_artist=tags.album_artist or tags.artist,
                     track_number=track, track_total=tags.track_total or track,
                     disc_number=disc, disc_total=tags.disc_total or disc, isrc=tags.isrc)


def _same(a: str, b: str) -> bool:
    return nfc(a).casefold().strip() == nfc(b).casefold().strip()


def _report_metadata(report: Report, file: AudioFile, album: DeezerAlbum | None) -> None:
    tags = file.tags
    if album is None:
        report.add("Deezer lookup failed (tag fallback used; Deemix path parity uncertain)",
                   f"{file.rel}  (ISRC {tags.isrc or 'none'}, barcode {tags.barcode or 'none'})")
    else:
        diffs = []
        if not _same(tags.album, album.title):
            diffs.append(f"album {tags.album!r} vs Deezer {album.title!r}")
        if tags.album_artist and not _same(tags.album_artist, album.artist):
            diffs.append(f"album artist {tags.album_artist!r} vs Deezer {album.artist!r}")
        if diffs:
            report.add("Deezer metadata disagrees with tags", f"{file.rel}: {'; '.join(diffs)}")
    if tags.album_artist and not _same(tags.album_artist, tags.artist):
        report.add("Album artist differs from track artist",
                   f"{file.rel}: artist {tags.artist!r}, album artist {tags.album_artist!r}")


def plan_files(root: Path, songs: list[Song], deezer: DeezerClient, settings: DeemixSettings,
               progress: Progress) -> Plan:
    plan = Plan()
    report = plan.report
    claimed: set[str] = set()
    covered: set[str] = set()
    lookups = progress.counter("Deezer lookups", sum(s.canonical.location is not Location.ALBUM for s in songs))

    for song in sorted(songs, key=lambda s: s.canonical.rel):
        canonical = song.canonical
        if canonical.location is Location.ALBUM:
            final = canonical.rel
        else:
            lookups.advance(canonical.rel)
            album = lookup_album(canonical, deezer)
            _report_metadata(report, canonical, album)
            target = deemix_path(track_meta(canonical, album), canonical.extension, settings)
            if rel_key(target) in claimed or (root / target).exists():
                final = canonical.rel
                report.add(CONFLICTS,
                           f"{canonical.rel}  (Deemix path {target} is taken)")
            else:
                final = target
                claimed.add(rel_key(target))
                folder = target.split("/")[0]
                if (root / folder).exists():
                    report.add("Merges into existing album folders", f"{folder} <- {canonical.rel}")
                elif rel_key(folder) not in covered:
                    art = read_art(canonical.path)
                    if art is not None:
                        covered.add(rel_key(folder))
                        cover = f"{folder}/cover.{'png' if 'png' in art.mime else 'jpg'}"
                        plan.ops.append(Write(cover, art.data))
                        report.add("Covers extracted for new album folders", f"{cover}  (from {canonical.rel})")
                plan.ops.append(Move(canonical.path, target))
                report.add(MOVES, f"{canonical.rel} -> {target}")

        final_stem = final.rsplit(".", 1)[0]
        kept_sidecars = {sc.suffix.lower() for sc in canonical.sidecars()}
        if final != canonical.rel:
            plan.ops += [Move(sc, final_stem + sc.suffix.lower()) for sc in canonical.sidecars()]

        for copy in song.copies:
            plan.final_paths[rel_key(copy.rel)] = copy.rel if copy.location is Location.ALBUM else final
        for dup in song.duplicates:
            if dup.location is Location.ALBUM:
                continue
            plan.ops.append(Trash(dup.path))
            report.add(TRASHED, f"{dup.rel}  (canonical copy: {final})")
            for sidecar in dup.sidecars():
                ext = sidecar.suffix.lower()
                if ext in kept_sidecars:
                    plan.ops.append(Trash(sidecar))
                else:
                    kept_sidecars.add(ext)
                    plan.ops.append(Move(sidecar, final_stem + ext))
                    report.add("Sidecars adopted from a duplicate copy", f"{dup.rel} -> {final_stem}{ext}")
        plan.labels[final] = playlist_file.label(canonical.tags)

    lookups.finish()
    _plan_root_playlists(root, plan)
    _plan_housekeeping(root, plan)
    return plan


def self_check(before: list[Song], after: list[Song], plan: Plan, executor: Executor) -> tuple[bool, str]:
    """Unique songs reconcile, and every trashed audio file has a canonical copy of the same song."""
    before_keys = {s.key for s in before}
    after_keys = {s.key for s in after}
    problems = [f"song missing after the run: {k}" for k in sorted(before_keys - after_keys)]
    trashed = 0
    for op in plan.ops:
        if isinstance(op, Trash) and op.src.suffix.lower() in AUDIO_EXTS:
            in_trash = executor.trash_path(op.src)
            if not in_trash.is_file():
                problems.append(f"not in trash: {in_trash}")
                continue
            trashed += 1
            if song_key(read_tags(in_trash), "") not in after_keys:
                problems.append(f"trashed copy has no canonical copy: {in_trash}")
    if problems:
        return False, "Self-check FAILED: " + "; ".join(problems)
    return True, (f"Self-check passed: {len(before_keys)} unique songs before and after; "
                  f"{trashed} trashed copies have a canonical copy")


ARTIFACT_NAMES = {"cover.jpg", "errors.txt"}
JUNK_NAMES = {".DS_Store"}
ARTIFACTS_DIR = ".artifacts"


def _is_handled_audio(path: Path) -> bool:
    if path.suffix.lower() in AUDIO_EXTS:
        return True
    return path.suffix.lower() in SIDECAR_EXTS and any(path.with_suffix(e).exists() for e in AUDIO_EXTS)


def _clear_folder(root: Path, folder: Path, plan: Plan) -> None:
    """Archive playlist artifacts, trash stale files; songs are handled separately."""
    report = plan.report
    for path in sorted(folder.iterdir()):
        rel = nfc(path.relative_to(root).as_posix())
        if path.is_dir():
            report.add("Left in place (unexpected; folder kept)", rel + "/")
        elif _is_handled_audio(path):
            continue
        elif path.name in ARTIFACT_NAMES or path.suffix.lower() in SIDECAR_EXTS:
            # An orphaned sidecar (its audio never downloaded or is elsewhere) is playlist debris.
            dest = f"{ARTIFACTS_DIR}/{nfc(folder.name)}/{path.name}"
            if (root / dest).exists():
                plan.ops.append(Trash(path))
                report.add("Artifacts trashed (already archived)", rel)
            else:
                plan.ops.append(Move(path, dest))
                report.add("Playlist artifacts archived", f"{rel} -> {dest}")
        elif path.suffix.lower() in PLAYLIST_EXTS:
            plan.ops.append(Trash(path))
            report.add("Stale in-folder playlist files trashed", rel)
        elif path.suffix.lower() == ".log" or path.name in JUNK_NAMES:
            plan.ops.append(Trash(path))
            if path.name not in JUNK_NAMES:
                report.add("Stray logs trashed", rel)
        else:
            report.add("Left in place (unexpected; folder kept)", rel)


def _contains_audio(folder: Path) -> bool:
    return any(p.suffix.lower() in AUDIO_EXTS for p in folder.rglob("*"))


def _plan_housekeeping(root: Path, plan: Plan) -> None:
    legacy = root / LEGACY_PLAYLISTS_DIR
    if legacy.is_dir():
        for folder in sorted(p for p in legacy.iterdir() if p.is_dir()):
            _clear_folder(root, folder, plan)
            plan.ops.append(RemoveDir(nfc(folder.relative_to(root).as_posix())))
        for path in legacy.iterdir():
            if path.is_file():
                if path.name in JUNK_NAMES:
                    plan.ops.append(Trash(path))
                else:
                    plan.report.add("Left in place (unexpected; folder kept)", nfc(path.relative_to(root).as_posix()))
        plan.ops.append(RemoveDir(LEGACY_PLAYLISTS_DIR))

    for folder in sorted(root.iterdir()):
        if (not folder.is_dir() or folder.name.startswith(".")
                or folder.name in (LEGACY_PLAYLISTS_DIR, DEEMIX_CONFIG_DIR) or _contains_audio(folder)):
            continue
        contents = list(folder.iterdir())
        if contents and all(p.is_file() and p.name in ARTIFACT_NAMES | JUNK_NAMES for p in contents):
            _clear_folder(root, folder, plan)
            plan.ops.append(RemoveDir(nfc(folder.name)))
            plan.report.add("Empty album folders removed", nfc(folder.name))

    for path in sorted(root.iterdir()):
        if path.is_file() and (path.name in ("dedup_music.py", "dedup_music.log")
                               or (path.name.startswith("dedup_manifest_") and path.suffix == ".json")):
            plan.ops.append(Trash(path))
            plan.report.add("Retired dedup_music.py files trashed", path.name)


def root_playlist_files(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir()
                  if p.is_file() and p.suffix.lower() in PLAYLIST_EXTS and not p.name.startswith("."))


def _plan_root_playlists(root: Path, plan: Plan) -> None:
    for playlist in root_playlist_files(root):
        old = playlist_file.read(playlist, root)
        new = []
        for entry in old:
            final = plan.final_paths.get(rel_key(entry))
            if final is None:
                plan.report.add("Dangling playlist entries (no such song; kept as is)", f"{playlist.name}: {entry}")
            new.append(final or entry)
        content = playlist_file.render([playlist_file.Entry(p, plan.labels.get(p, "")) for p in new])
        if content != playlist.read_bytes():
            plan.ops.append(Write(playlist.name, content, replace=True))
            changed = sum(a != b for a, b in zip(old, new))
            plan.report.add("Playlist file rewrites", f"{playlist.name}: {len(new)} entries, {changed} repointed")
