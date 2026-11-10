"""Playlist import: bring root-level playlist files into Jellyfin with a three-way merge.

Inputs per playlist: the previous import reference (last Deezer list), the new playlist file, and the
current Jellyfin playlist. Songs new on Deezer are appended at the end in Deezer order; songs removed by
hand stay removed; songs Deezer dropped are only reported. Nothing is ever removed or reordered.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from reorganize_playlists import playlist_file
from reorganize_playlists.executor import Executor
from reorganize_playlists.jellyfin import JellyfinClient
from reorganize_playlists.library import nfc, rel_key
from reorganize_playlists.migrate import ARTIFACT_NAMES, ARTIFACTS_DIR, root_playlist_files
from reorganize_playlists.report import Report
from reorganize_playlists.tags import read_tags

PLAYLISTS_DIR = ".playlists"
IMPORTS_DIR = f"{PLAYLISTS_DIR}/imports"
MAP_FILE = f"{PLAYLISTS_DIR}/map.json"
ROOT_ARTIFACTS = sorted(ARTIFACT_NAMES)


@dataclass(frozen=True)
class Merge:
    append: list[str]
    dropped: list[str]


def three_way_merge(previous: list[str], new: list[str], current: list[str]) -> Merge:
    previous_keys = {rel_key(p) for p in previous}
    current_keys = {rel_key(p) for p in current}
    new_keys = {rel_key(p) for p in new}
    append, seen = [], set()
    for path in new:
        key = rel_key(path)
        if key not in previous_keys and key not in current_keys and key not in seen:
            append.append(path)
            seen.add(key)
    return Merge(append=append, dropped=[p for p in previous if rel_key(p) not in new_keys])


@dataclass
class ImportResult:
    report: Report = field(default_factory=Report)
    summary: list[str] = field(default_factory=list)
    ok: bool = True


def load_map(root: Path) -> dict[str, str]:
    path = root / MAP_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _labels(root: Path, paths: list[str]) -> list[playlist_file.Entry]:
    return [playlist_file.Entry(p, playlist_file.label(read_tags(root / p))) for p in paths]


def run_import(root: Path, jellyfin: JellyfinClient, user: str, executor: Executor,
               strict: bool, take_root_artifacts: bool) -> ImportResult:
    """`strict`: refuse to touch anything if any entry is unknown to Jellyfin (migration playlist phase)."""
    result = ImportResult()
    report = result.report
    dry_run = executor.dry_run
    playlists = root_playlist_files(root)
    if not playlists:
        report.add("Playlists", "no playlist files at the library root; nothing to import")
        return result

    if not dry_run:
        jellyfin.start_library_scan()
        jellyfin.wait_for_scan()
    user_id = jellyfin.get_user_id(user)
    mapping = load_map(root)

    lists = {nfc(p.stem): playlist_file.read(p, root) for p in playlists}
    ids = jellyfin.find_items_by_paths(sorted({e for entries in lists.values() for e in entries}))
    unresolved = {name: [e for e in entries if e not in ids] for name, entries in lists.items()}
    for name, missing in unresolved.items():
        for entry in missing:
            report.add("Entries not found in Jellyfin", f"{name}: {entry}")
    if strict and any(unresolved.values()):
        result.ok = False
        report.add("Aborted", "some entries are not in Jellyfin yet; finish the scan (or fix the paths) and re-run")
        return result

    artifact_owner = None
    if take_root_artifacts and any((root / a).is_file() for a in ROOT_ARTIFACTS):
        artifact_owner = nfc(max(playlists, key=lambda p: p.stat().st_mtime).stem)
        if len(playlists) > 1:
            report.add("Root artifacts", f"several playlist files at the root; errors.txt/cover.jpg attributed "
                                         f"to the newest one, {artifact_owner}")

    for playlist in playlists:
        name = nfc(playlist.stem)
        entries = [e for e in lists[name] if e in ids]
        reference_path = root / IMPORTS_DIR / f"{name}.m3u8"
        previous = playlist_file.read(reference_path, root) if reference_path.exists() else []
        playlist_id = mapping.get(name)
        current = jellyfin.get_playlist_items(playlist_id, user_id) if playlist_id else None

        if current is None:
            if playlist_id:
                report.add("Mapped playlists missing in Jellyfin (recreated)", f"{name}: {playlist_id}")
            report.add("Playlists created", f"{name}: {len(entries)} songs")
            result.summary.append(f"{name} created ({len(entries)} songs)")
            if not dry_run:
                playlist_id = jellyfin.create_playlist(name, [ids[e] for e in entries], user_id)
                executor.jellyfin_created(playlist_id)
                mapping[name] = playlist_id
        else:
            assert playlist_id is not None
            merge = three_way_merge(previous, entries, [e.path for e in current])
            for path in merge.append:
                report.add("Songs appended", f"{name}: {path}")
            for path in merge.dropped:
                report.add("Dropped on Deezer (not removed from Jellyfin)", f"{name}: {path}")
            parts = []
            if merge.append:
                parts.append(f"+{len(merge.append)} songs")
            if merge.dropped:
                parts.append(f"{len(merge.dropped)} dropped on Deezer")
            if parts:
                result.summary.append(f"{name} {'; '.join(parts)}")
            if merge.append and not dry_run:
                jellyfin.append_to_playlist(playlist_id, [ids[p] for p in merge.append], user_id)
                after = jellyfin.get_playlist_items(playlist_id, user_id) or []
                executor.jellyfin_appended(playlist_id, [e.entry_id for e in after[len(current):]])

        artifacts = root / ARTIFACTS_DIR / name
        cover: Path | None = artifacts / "cover.jpg" if current is None else None
        if name == artifact_owner:
            if (root / "cover.jpg").is_file():
                cover = root / "cover.jpg"
            for artifact in ROOT_ARTIFACTS:
                if (root / artifact).is_file():
                    report.add("Root artifacts archived", f"{artifact} -> {ARTIFACTS_DIR}/{name}/{artifact}")
        if cover is not None and cover.is_file():
            report.add("Playlist covers uploaded", name)
            if not dry_run and playlist_id:
                jellyfin.upload_playlist_image(playlist_id, cover.read_bytes())
        if name == artifact_owner:
            for artifact in ROOT_ARTIFACTS:
                if (root / artifact).is_file():
                    if (artifacts / artifact).exists():
                        executor.to_trash(artifacts / artifact)
                    executor.move(root / artifact, artifacts / artifact)

        executor.write(reference_path, playlist_file.render(_labels(root, entries)), replace=True)
        executor.to_trash(playlist)
        report.add("Playlist files imported", f"{playlist.name} -> {IMPORTS_DIR}/{name}.m3u8")

    executor.write(root / MAP_FILE, (json.dumps(mapping, indent=2, ensure_ascii=False, sort_keys=True)
                                     + "\n").encode("utf-8"), replace=True)
    return result
