"""Library scanner and song identity / canonical-copy resolution."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from reorganize_playlists.tags import Tags, read_tags

AUDIO_EXTS = {".flac", ".mp3"}
SIDECAR_EXTS = (".lrc",)
PLAYLIST_EXTS = {".m3u", ".m3u8"}
LEGACY_PLAYLISTS_DIR = "Playlists"
DEEMIX_CONFIG_DIR = "Config"
FORMAT_RANK = {".flac": 0, ".mp3": 1}


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def rel_key(path: str) -> str:
    """Comparison key for a library-relative path (APFS is NFC/NFD- and case-insensitive)."""
    return nfc(path).casefold()


class Location(Enum):
    ALBUM = "album folder"
    PLAYLIST = "legacy playlist folder"
    ROOT = "loose root"


@dataclass(frozen=True)
class AudioFile:
    rel: str  # NFC POSIX path relative to the library root
    path: Path  # path as stored on disk
    size: int
    tags: Tags
    location: Location

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()

    @property
    def playlist_folder(self) -> str | None:
        parts = self.rel.split("/")
        return parts[1] if self.location is Location.PLAYLIST and len(parts) > 2 else None

    def sidecars(self) -> list[Path]:
        return [p for p in (self.path.with_suffix(ext) for ext in SIDECAR_EXTS) if p.exists()]


def _location(rel: str) -> Location:
    parts = rel.split("/")
    if len(parts) == 1:
        return Location.ROOT
    if parts[0] == LEGACY_PLAYLISTS_DIR:
        return Location.PLAYLIST
    return Location.ALBUM


def scan(root: Path) -> list[AudioFile]:
    """Every audio file under `root`, skipping dot-entries and the Deemix config folder."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".")
                             and not (here == root and d == DEEMIX_CONFIG_DIR))
        for name in sorted(filenames):
            path = here / name
            if name.startswith(".") or path.suffix.lower() not in AUDIO_EXTS:
                continue
            rel = nfc(path.relative_to(root).as_posix())
            files.append(AudioFile(rel=rel, path=path, size=path.stat().st_size,
                                   tags=read_tags(path), location=_location(rel)))
    return files


def normalise_words(text: str) -> str:
    """NFC, case-folded, punctuation stripped, whitespace collapsed — the loose tag comparison."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", nfc(text).casefold())).strip()


def song_key(tags: Tags, fallback: str) -> str:
    """ISRC first; else normalised artist + title; else the file path (unknown song)."""
    if tags.isrc:
        return f"isrc:{tags.isrc}"
    if tags.title:
        return f"name:{normalise_words(tags.artist)}|{normalise_words(tags.title)}"
    return f"path:{fallback}"


@dataclass(frozen=True)
class Song:
    key: str
    copies: list[AudioFile]

    @property
    def canonical(self) -> AudioFile:
        return min(self.copies, key=lambda f: (f.location is not Location.ALBUM,
                                               FORMAT_RANK.get(f.extension, 9), -f.size, f.rel))

    @property
    def duplicates(self) -> list[AudioFile]:
        canonical = self.canonical
        return [f for f in self.copies if f is not canonical]


def group_songs(files: list[AudioFile]) -> list[Song]:
    groups: dict[str, list[AudioFile]] = {}
    for f in files:
        groups.setdefault(song_key(f.tags, f.rel), []).append(f)
    return [Song(key=k, copies=v) for k, v in groups.items()]
