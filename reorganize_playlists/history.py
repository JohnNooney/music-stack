"""Playlist exports, inventory, and commits to the library's text-only git repo (never pushed)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from reorganize_playlists import playlist_file
from reorganize_playlists.deemix import fix_name
from reorganize_playlists.jellyfin import JellyfinClient
from reorganize_playlists.library import AudioFile
from reorganize_playlists.tags import read_tags

INVENTORY = ".inventory.tsv"
EXPORTS_DIR = ".playlists/jellyfin"

# Allow-list: only the hidden text files are tracked; audio, images and everything else are ignored.
GITIGNORE = """\
# Managed by reorganize_playlists: track only playlist/text history, never audio or images.
*
!.gitignore
!.inventory.tsv
!.playlists/
!.playlists/map.json
!.playlists/imports/
!.playlists/imports/*.m3u8
!.playlists/jellyfin/
!.playlists/jellyfin/*.m3u8
!.artifacts/
!.artifacts/*/
!.artifacts/*/errors.txt
"""


def _clean(value: str) -> str:
    return value.replace("\t", " ").replace("\n", " ")


def write_inventory(root: Path, files: list[AudioFile]) -> None:
    rows = ["path\tisrc\tsize\tartist\talbum\ttitle"]
    for f in sorted(files, key=lambda f: f.rel):
        t = f.tags
        rows.append("\t".join(_clean(v) for v in (f.rel, t.isrc, str(f.size), "; ".join(t.artists),
                                                  t.album, t.title)))
    (root / INVENTORY).write_text("\n".join(rows) + "\n", encoding="utf-8")


def export_playlists(root: Path, jellyfin: JellyfinClient, user_id: str) -> int:
    """Rewrite `.playlists/jellyfin/` from the user's Jellyfin playlists; stale exports are removed."""
    directory = root / EXPORTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    written = set()
    for playlist in jellyfin.list_playlists(user_id):
        items = jellyfin.get_playlist_items(playlist.id, user_id) or []
        entries = [playlist_file.Entry(i.path, playlist_file.label(read_tags(root / i.path))) for i in items]
        name = fix_name(playlist.name, "_") + ".m3u8"
        (directory / name).write_bytes(playlist_file.render(entries))
        written.add(name)
    for stale in directory.glob("*.m3u8"):
        if stale.name not in written:
            stale.unlink()
    return len(written)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def commit(root: Path, message: str) -> bool:
    """Commit every allow-listed change with `message`. Returns False when there was nothing to commit."""
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    _git(root, "add", "-A").check_returncode()
    if _git(root, "diff", "--cached", "--quiet").returncode == 0:
        return False
    identity: list[str] = []
    if not _git(root, "config", "user.email").stdout.strip():
        identity = ["-c", "user.name=reorganize_playlists", "-c", "user.email=reorganize_playlists@localhost"]
    subprocess.run(["git", "-C", str(root), *identity, "commit", "-q", "-m", message],
                   check=True, capture_output=True, text=True)
    return True
