"""Fixture library builder and in-memory fakes for the Deezer and Jellyfin ports."""

from __future__ import annotations

import io
import json
import os
import struct
import subprocess
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from reorganize_playlists.cli import main
from reorganize_playlists.deezer import DeezerAlbum, DeezerTrack
from reorganize_playlists.jellyfin import PlaylistEntry, PlaylistInfo, ScanStatus

JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg" + b"\xff\xd9"

DEEMIX_CONFIG = {
    "downloadLocation": "/downloads/",
    "tracknameTemplate": "%artist% - %title%",
    "albumTracknameTemplate": "%tracknumber% - %title%",
    "playlistTracknameTemplate": "%tracknumber% - %title%",
    "createPlaylistFolder": False,
    "playlistNameTemplate": "Playlists/%playlist%",
    "createArtistFolder": False,
    "albumNameTemplate": "%artist% - %album%",
    "createAlbumFolder": True,
    "createCDFolder": True,
    "createStructurePlaylist": True,
    "padTracks": True,
    "padSingleDigit": True,
    "paddingSize": 0,
    "illegalCharacterReplacer": "_",
    "createM3U8File": True,
    "playlistFilenameTemplate": "%title%",
}


def _vorbis_block(tags: dict[str, list[str]]) -> bytes:
    vendor = b"fixture"
    comments = [f"{k}={v}".encode() for k, values in tags.items() for v in values]
    body = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(comments))
    for c in comments:
        body += struct.pack("<I", len(c)) + c
    return body


def _picture_block(image: bytes) -> bytes:
    mime = b"image/jpeg"
    return (struct.pack(">II", 3, len(mime)) + mime + struct.pack(">I", 0)
            + struct.pack(">IIIII", 0, 0, 0, 0, len(image)) + image)


def _flac_bytes(tags: dict[str, list[str]], art: bytes | None, audio_size: int) -> bytes:
    blocks = [(0, b"\x00" * 34), (4, _vorbis_block(tags))]
    if art is not None:
        blocks.append((6, _picture_block(art)))
    out = b"fLaC"
    for i, (kind, body) in enumerate(blocks):
        last = 0x80 if i == len(blocks) - 1 else 0
        out += bytes([last | kind]) + len(body).to_bytes(3, "big") + body
    return out + b"\xff\xf8" + b"\x00" * audio_size


def _synchsafe(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def _mp3_bytes(frames: dict[str, str], art: bytes | None, audio_size: int, version: int) -> bytes:
    body = b""
    for frame_id, text in frames.items():
        payload = b"\x03" + text.encode("utf-8") if version == 4 else b"\x01" + text.encode("utf-16")
        size = _synchsafe(len(payload)) if version == 4 else struct.pack(">I", len(payload))
        body += frame_id.encode() + size + b"\x00\x00" + payload
    if art is not None:
        payload = b"\x00image/jpeg\x00\x03\x00" + art
        size = _synchsafe(len(payload)) if version == 4 else struct.pack(">I", len(payload))
        body += b"APIC" + size + b"\x00\x00" + payload
    header = b"ID3" + bytes([version, 0, 0]) + _synchsafe(len(body))
    return header + body + b"\xff\xfb" + b"\x00" * audio_size


class Library:
    """Builds a tiny music library on disk."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, rel: str) -> Path:
        return self.root / rel

    def flac(self, rel: str, *, title: str, artist: str | list[str], album: str,
             albumartist: str | list[str] | None = None, track: int = 1, disc: int = 1,
             isrc: str | None = None, barcode: str | None = None, art: bytes | None = JPEG,
             size: int = 100) -> Path:
        tags: dict[str, list[str]] = {
            "TITLE": [title], "ARTIST": artist if isinstance(artist, list) else [artist],
            "ALBUM": [album], "TRACKNUMBER": [str(track)], "DISCNUMBER": [str(disc)],
        }
        if albumartist is not None:
            tags["ALBUMARTIST"] = albumartist if isinstance(albumartist, list) else [albumartist]
        if isrc:
            tags["ISRC"] = [isrc]
        if barcode:
            tags["BARCODE"] = [barcode]
        return self.write(rel, _flac_bytes(tags, art, size))

    def mp3(self, rel: str, *, title: str, artist: str, album: str, albumartist: str | None = None,
            track: int = 1, disc: int = 1, isrc: str | None = None, art: bytes | None = JPEG,
            size: int = 100, version: int = 3) -> Path:
        frames = {"TIT2": title, "TPE1": artist, "TALB": album, "TRCK": str(track), "TPOS": str(disc)}
        if albumartist is not None:
            frames["TPE2"] = albumartist
        if isrc:
            frames["TSRC"] = isrc
        return self.write(rel, _mp3_bytes(frames, art, size, version))

    def write(self, rel: str, content: bytes | str, encoding: str = "utf-8") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode(encoding) if isinstance(content, str) else content)
        return path

    def snapshot(self) -> dict[str, bytes]:
        """Every file under the root (except tool state) with its content."""
        result = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d != ".reorganize"]
            for name in filenames:
                p = Path(dirpath) / name
                result[unicodedata.normalize("NFC", p.relative_to(self.root).as_posix())] = p.read_bytes()
        return result

    def files(self) -> set[str]:
        return set(self.snapshot())


class FakeDeezer:
    def __init__(self) -> None:
        self.tracks: dict[str, DeezerTrack] = {}
        self.albums: dict[str, DeezerAlbum] = {}
        self.calls: list[tuple[str, str]] = []

    def add(self, isrc: str, *, album: str, artist: str, track_total: int, disc_total: int = 1,
            album_id: str | None = None, upc: str | None = None,
            contributors: list[str] | None = None) -> None:
        album_id = album_id or f"alb-{album}-{artist}"
        self.tracks[isrc] = DeezerTrack(id=f"trk-{isrc}", album_id=album_id,
                                        contributors=contributors if contributors is not None else [artist])
        info = DeezerAlbum(id=album_id, title=album, artist=artist,
                           track_total=track_total, disc_total=disc_total)
        self.albums[album_id] = info
        if upc:
            self.albums[f"upc:{upc}"] = info

    def lookup_track_by_isrc(self, isrc: str) -> DeezerTrack | None:
        self.calls.append(("track", isrc))
        return self.tracks.get(isrc)

    def get_album(self, album_id: str) -> DeezerAlbum | None:
        self.calls.append(("album", album_id))
        return self.albums.get(album_id)


@dataclass
class FakePlaylist:
    name: str
    owner: str
    entries: list[tuple[str, str]] = field(default_factory=list)  # (entry_id, item_id)
    image: bytes | None = None


class FakeJellyfin:
    """Holds scanned items keyed by library-relative path and user-owned playlists."""

    AUDIO = {".flac", ".mp3"}

    def __init__(self, root: Path, status: ScanStatus = "idle") -> None:
        self.root = root
        self.status: ScanStatus = status
        self.users = {"john": "user-john"}
        self.items: dict[str, str] = {}
        self.playlists: dict[str, FakePlaylist] = {}
        self.mutations: list[str] = []
        self.scans_started = 0
        self.scan_progress: list[float] = []
        self._scan_pending = False
        self._next = 0

    def _id(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}{self._next}"

    def scan(self) -> None:
        """Index every audio file currently on disk (dot-entries ignored, like Jellyfin)."""
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                p = Path(dirpath) / name
                if p.suffix.lower() in self.AUDIO and not name.startswith("."):
                    rel = unicodedata.normalize("NFC", p.relative_to(self.root).as_posix())
                    self.items.setdefault(rel, self._id("item"))

    def _require_scanned(self) -> None:
        if self._scan_pending:
            raise AssertionError("library touched before the scan finished")

    def path_of(self, item_id: str) -> str:
        return next(p for p, i in self.items.items() if i == item_id)

    def playlist_paths(self, playlist_id: str) -> list[str]:
        return [self.path_of(item) for _, item in self.playlists[playlist_id].entries]

    def by_name(self, name: str) -> tuple[str, FakePlaylist]:
        return next((pid, pl) for pid, pl in self.playlists.items() if pl.name == name)

    def add_playlist(self, name: str, paths: list[str]) -> str:
        pid = self._id("pl")
        self.playlists[pid] = FakePlaylist(name=name, owner="user-john",
                                           entries=[(self._id("entry"), self.items[p]) for p in paths])
        return pid

    # --- port ---
    def scan_status(self) -> ScanStatus:
        return self.status

    def start_library_scan(self) -> None:
        self.scans_started += 1
        self._scan_pending = True

    def wait_for_scan(self, on_progress: Callable[[float], None] | None = None) -> None:
        for percent in self.scan_progress:
            if on_progress:
                on_progress(percent)
        if self._scan_pending:
            self.scan()
        self._scan_pending = False

    def find_items_by_paths(self, paths: list[str]) -> dict[str, str]:
        self._require_scanned()
        return {p: self.items[p] for p in paths if p in self.items}

    def get_user_id(self, username: str) -> str:
        return self.users[username]

    def create_playlist(self, name: str, item_ids: list[str], user_id: str) -> str:
        self._require_scanned()
        self.mutations.append(f"create {name}")
        pid = self._id("pl")
        self.playlists[pid] = FakePlaylist(name=name, owner=user_id,
                                           entries=[(self._id("entry"), i) for i in item_ids])
        return pid

    def list_playlists(self, user_id: str) -> list[PlaylistInfo]:
        return [PlaylistInfo(id=pid, name=pl.name) for pid, pl in self.playlists.items() if pl.owner == user_id]

    def get_playlist_items(self, playlist_id: str, user_id: str) -> list[PlaylistEntry] | None:
        pl = self.playlists.get(playlist_id)
        if pl is None:
            return None
        return [PlaylistEntry(entry_id=e, item_id=i, path=self.path_of(i)) for e, i in pl.entries]

    def append_to_playlist(self, playlist_id: str, item_ids: list[str], user_id: str) -> None:
        self._require_scanned()
        self.mutations.append(f"append {playlist_id}")
        self.playlists[playlist_id].entries += [(self._id("entry"), i) for i in item_ids]

    def remove_from_playlist(self, playlist_id: str, entry_ids: list[str]) -> None:
        self.mutations.append(f"remove {playlist_id}")
        pl = self.playlists[playlist_id]
        pl.entries = [(e, i) for e, i in pl.entries if e not in entry_ids]

    def delete_playlist(self, playlist_id: str) -> None:
        self.mutations.append(f"delete {playlist_id}")
        del self.playlists[playlist_id]

    def upload_playlist_image(self, playlist_id: str, image: bytes) -> None:
        self.mutations.append(f"image {playlist_id}")
        self.playlists[playlist_id].image = image


class ToolTestCase(unittest.TestCase):
    """A temp library, trash, Deemix config and `.env`, plus a `run()` entry-point helper."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root = base / "Deemix"
        self.root.mkdir()
        self.trash = base / "trash"
        self.lib = Library(self.root)
        self.deezer = FakeDeezer()
        self.jellyfin = FakeJellyfin(self.root)
        self.deemix_config = base / "deemix-config" / "config.json"
        self.deemix_config.parent.mkdir()
        self.deemix_config.write_text(json.dumps(DEEMIX_CONFIG))
        self.env = base / ".env"
        self.env.write_text("JELLYFIN_URL=http://localhost:8096\nJELLYFIN_API_KEY=test-key\nJELLYFIN_USER=john\n")
        gitconfig = base / "gitconfig"
        gitconfig.write_text("[user]\n\tname = Test\n\temail = test@example.com\n[init]\n\tdefaultBranch = main\n")
        for key, value in {"GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_NOSYSTEM": "1"}.items():
            self.addCleanup(self._restore_env, key, os.environ.get(key))
            os.environ[key] = value
        self.output = ""

    def set_env(self, key: str, value: str) -> None:
        self.addCleanup(self._restore_env, key, os.environ.get(key))
        os.environ[key] = value

    @staticmethod
    def _restore_env(key: str, old: str | None) -> None:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old

    def run_tool(self, *args: str, paths: bool = True, real_jellyfin: bool = False,
                 expect: int = 0) -> str:
        """Run the tool in-process; `real_jellyfin` makes it build its HTTP client from `.env`."""
        argv = (["--root", str(self.root), "--trash", str(self.trash)] if paths else []) + [
                "--deemix-config", str(self.deemix_config), "--env", str(self.env), *args]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv, deezer=self.deezer, jellyfin=None if real_jellyfin else self.jellyfin)
        self.output = out.getvalue() + err.getvalue()
        self.assertEqual(code, expect, self.output)
        return self.output

    def latest_manifest(self) -> Path:
        runs = sorted((self.root / ".reorganize" / "runs").glob("*/manifest.json"))
        return runs[-1]

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout
