"""Reads playlist files from Deemix, Jellyfin, dedup_music.py or legacy folders; writes extended M3U8."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reorganize_playlists.library import nfc
from reorganize_playlists.tags import Tags

CONTAINER_ROOTS = ("/media/", "/downloads/")


@dataclass(frozen=True)
class Entry:
    path: str  # relative to the library root, POSIX, NFC
    label: str = ""  # "Artist - Title" for #EXTINF


def label(tags: Tags) -> str:
    """`#EXTINF` display text for a song."""
    return f"{tags.artist} - {tags.title}" if tags.title else ""


def decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _relative(line: str, root: Path) -> str:
    path = nfc(line.replace("\\", "/"))
    for prefix in (nfc(root.as_posix()).rstrip("/") + "/", *CONTAINER_ROOTS):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path.removeprefix("./")


def read(path: Path, root: Path) -> list[str]:
    """Entry paths in order; comments, directives and blank lines (failed Deemix tracks) dropped."""
    lines = decode(path.read_bytes()).splitlines()
    return [_relative(line.strip(), root) for line in lines if line.strip() and not line.strip().startswith("#")]


def render(entries: list[Entry]) -> bytes:
    out = ["#EXTM3U"]
    for entry in entries:
        if entry.label:
            out.append(f"#EXTINF:-1,{entry.label}")
        out.append(entry.path)
    return ("\n".join(out) + "\n").encode("utf-8")
