"""Deezer client port: album metadata needed to compute a song's Deemix path."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

API_URL = "https://api.deezer.com"
MIN_REQUEST_INTERVAL = 0.1  # Deezer allows ~50 requests / 5 s
MACOS_CA_BUNDLE = "/etc/ssl/cert.pem"


@dataclass(frozen=True)
class DeezerTrack:
    id: str
    album_id: str


@dataclass(frozen=True)
class DeezerAlbum:
    id: str
    title: str
    artist: str
    track_total: int
    disc_total: int


class DeezerClient(Protocol):
    def lookup_track_by_isrc(self, isrc: str) -> DeezerTrack | None: ...

    def get_album(self, album_id: str) -> DeezerAlbum | None:
        """`album_id` is a Deezer album id or `upc:<barcode>`."""
        ...


def _ssl_context() -> ssl.SSLContext:
    """python.org builds on macOS ship without CA certificates; fall back to the system bundle."""
    context = ssl.create_default_context()
    if not context.cert_store_stats()["x509_ca"] and Path(MACOS_CA_BUNDLE).is_file():
        context.load_verify_locations(MACOS_CA_BUNDLE)
    return context


class HttpDeezerClient:
    """Deezer's public unauthenticated API, rate-limited and cached to a JSON file."""

    def __init__(self, cache_path: Path) -> None:
        self._cache_path = cache_path
        self._cache: dict[str, Any] = {}
        if cache_path.exists():
            self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
        self._last_request = 0.0
        self._unsaved = 0
        self._ssl = _ssl_context()
        self.network_errors: list[str] = []

    def lookup_track_by_isrc(self, isrc: str) -> DeezerTrack | None:
        key = f"track/isrc:{isrc}"
        if key in self._cache:
            return DeezerTrack(**self._cache[key]) if self._cache[key] else None
        ok, data = self._get(key)
        result = (DeezerTrack(id=str(data["id"]), album_id=str(data["album"]["id"]))
                  if data and "album" in data else None)
        if ok:
            self._store(key, asdict(result) if result else None)
        return result

    def get_album(self, album_id: str) -> DeezerAlbum | None:
        key = f"album/{album_id}"
        if key in self._cache:
            return DeezerAlbum(**self._cache[key]) if self._cache[key] else None
        ok, album = self._get(key)
        result: DeezerAlbum | None = None
        if album and "artist" in album:
            ok, tracks = self._get(f"album/{album['id']}/tracks?limit=1000")
            discs = [t.get("disk_number") or 1 for t in (tracks or {}).get("data", [])]
            result = DeezerAlbum(
                id=str(album["id"]),
                title=album["title"],
                artist=album["artist"]["name"],
                track_total=int(album["nb_tracks"]),
                disc_total=int(album.get("nb_disk") or max(discs, default=1)),
            )
        if ok:
            self._store(key, asdict(result) if result else None)
        return result

    def _get(self, path: str) -> tuple[bool, dict[str, Any] | None]:
        """(answered, data): answered is False on network/quota errors, which must not be cached."""
        wait = MIN_REQUEST_INTERVAL - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
        try:
            with urllib.request.urlopen(f"{API_URL}/{path}", timeout=20, context=self._ssl) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            self.network_errors.append(f"{path}: {exc}")
            return False, None
        if isinstance(data.get("error"), dict) and data["error"].get("code") == 4:
            self.network_errors.append(f"{path}: quota exceeded")
            time.sleep(5)
            return False, None
        return True, None if "error" in data else data

    def _store(self, key: str, value: Any) -> None:
        self._cache[key] = value
        self._unsaved += 1
        if self._unsaved >= 50:
            self.flush()

    def flush(self) -> None:
        if not self._unsaved:
            return
        self._unsaved = 0
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._cache_path)
