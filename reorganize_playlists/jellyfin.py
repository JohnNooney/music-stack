"""Jellyfin client port plus the `.env`-configured HTTP implementation."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

ScanStatus = Literal["unreachable", "idle", "scanning"]
SCAN_START_GRACE = 30.0  # seconds to wait for a requested scan to show up as running


class JellyfinUnavailable(Exception):
    """Raised when a command needs Jellyfin but it is not configured or reachable."""


@dataclass(frozen=True)
class PlaylistEntry:
    entry_id: str
    item_id: str
    path: str  # relative to the library root, POSIX, NFC


@dataclass(frozen=True)
class PlaylistInfo:
    id: str
    name: str


class JellyfinClient(Protocol):
    def scan_status(self) -> ScanStatus: ...
    def start_library_scan(self) -> None: ...
    def wait_for_scan(self, on_progress: Callable[[float], None] | None = None) -> None:
        """Block until the library scan has finished, reporting its percentage along the way."""
        ...
    def find_items_by_paths(self, paths: list[str]) -> dict[str, str]:
        """Map library-relative paths to item ids; unknown paths are omitted."""
        ...
    def get_user_id(self, username: str) -> str: ...
    def create_playlist(self, name: str, item_ids: list[str], user_id: str) -> str: ...
    def list_playlists(self, user_id: str) -> list[PlaylistInfo]:
        """User-owned playlists only (not playlists imported from playlist files)."""
        ...
    def get_playlist_items(self, playlist_id: str, user_id: str) -> list[PlaylistEntry] | None:
        """None when the playlist no longer exists."""
        ...
    def append_to_playlist(self, playlist_id: str, item_ids: list[str], user_id: str) -> None: ...
    def remove_from_playlist(self, playlist_id: str, entry_ids: list[str]) -> None: ...
    def delete_playlist(self, playlist_id: str) -> None: ...
    def upload_playlist_image(self, playlist_id: str, image: bytes) -> None: ...


@dataclass(frozen=True)
class Settings:
    url: str
    api_key: str
    user: str
    media_root: str


def load_settings(env_path: Path) -> Settings:
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    return Settings(
        url=values.get("JELLYFIN_URL") or "http://localhost:8096",
        api_key=values.get("JELLYFIN_API_KEY", ""),
        user=values.get("JELLYFIN_USER") or "john",
        media_root=values.get("JELLYFIN_MEDIA_ROOT") or "/media",
    )


def require_api_key(settings: Settings, env_path: Path) -> None:
    if not settings.api_key:
        raise JellyfinUnavailable(
            f"JELLYFIN_API_KEY is not set. Create an API key in Jellyfin "
            f"(Dashboard > API Keys) and put it in {env_path} (see .env.example)."
        )


class HttpJellyfinClient:
    def __init__(self, settings: Settings) -> None:
        self._base = settings.url.rstrip("/")
        self._key = settings.api_key
        self._media_root = settings.media_root.rstrip("/") + "/"
        self._items: dict[str, str] | None = None

    def _scan_task(self) -> dict[str, Any] | None:
        """The RefreshLibrary scheduled task; None when Jellyfin is unreachable."""
        try:
            tasks = self._request("GET", "/ScheduledTasks", {"isHidden": "false"})
        except urllib.error.HTTPError as exc:
            raise JellyfinUnavailable(f"Jellyfin at {self._base} rejected the request (HTTP {exc.code}); "
                                      "check JELLYFIN_API_KEY in .env") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            return None
        task: dict[str, Any] = next((t for t in tasks or [] if t.get("Key") == "RefreshLibrary"), {})
        return task

    def scan_status(self) -> ScanStatus:
        task = self._scan_task()
        if task is None:
            return "unreachable"
        return "scanning" if task.get("State", "Idle") != "Idle" else "idle"

    def start_library_scan(self) -> None:
        self._request("POST", "/Library/Refresh")
        self._items = None

    def wait_for_scan(self, on_progress: Callable[[float], None] | None = None) -> None:
        started = time.monotonic()
        seen_running = False
        while True:
            task = self._scan_task() or {}
            if task.get("State", "Idle") != "Idle":
                seen_running = True
                if on_progress:
                    on_progress(float(task.get("CurrentProgressPercentage") or 0))
            elif seen_running or time.monotonic() - started > SCAN_START_GRACE:
                break
            time.sleep(2)
        self._items = None

    def find_items_by_paths(self, paths: list[str]) -> dict[str, str]:
        if self._items is None:
            self._items = {}
            start = 0
            while True:
                page = self._request("GET", "/Items", {
                    "Recursive": "true", "IncludeItemTypes": "Audio", "Fields": "Path",
                    "StartIndex": str(start), "Limit": "1000",
                })
                for item in page["Items"]:
                    rel = self._relative(item.get("Path", ""))
                    if rel:
                        self._items[rel] = item["Id"]
                start += len(page["Items"])
                if not page["Items"] or start >= page["TotalRecordCount"]:
                    break
        return {p: self._items[p] for p in paths if p in self._items}

    def get_user_id(self, username: str) -> str:
        for user in self._request("GET", "/Users"):
            if user["Name"].casefold() == username.casefold():
                return str(user["Id"])
        raise JellyfinUnavailable(f"Jellyfin user {username!r} not found (set JELLYFIN_USER in .env)")

    def create_playlist(self, name: str, item_ids: list[str], user_id: str) -> str:
        result = self._request("POST", "/Playlists", body={
            "Name": name, "Ids": item_ids, "UserId": user_id, "MediaType": "Audio",
        })
        return str(result["Id"])

    def list_playlists(self, user_id: str) -> list[PlaylistInfo]:
        page = self._request("GET", "/Items", {
            "userId": user_id, "Recursive": "true", "IncludeItemTypes": "Playlist", "Fields": "Path",
        })
        return [
            PlaylistInfo(id=item["Id"], name=item["Name"])
            for item in page["Items"]
            if not item.get("Path", "").startswith(self._media_root)
        ]

    def get_playlist_items(self, playlist_id: str, user_id: str) -> list[PlaylistEntry] | None:
        try:
            page = self._request("GET", f"/Playlists/{playlist_id}/Items", {"userId": user_id, "Fields": "Path"})
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        return [
            PlaylistEntry(entry_id=item["PlaylistItemId"], item_id=item["Id"],
                          path=self._relative(item.get("Path", "")) or item.get("Path", ""))
            for item in page["Items"]
        ]

    def append_to_playlist(self, playlist_id: str, item_ids: list[str], user_id: str) -> None:
        for start in range(0, len(item_ids), 100):
            self._request("POST", f"/Playlists/{playlist_id}/Items",
                          {"ids": ",".join(item_ids[start:start + 100]), "userId": user_id})

    def remove_from_playlist(self, playlist_id: str, entry_ids: list[str]) -> None:
        self._request("DELETE", f"/Playlists/{playlist_id}/Items", {"entryIds": ",".join(entry_ids)})

    def delete_playlist(self, playlist_id: str) -> None:
        self._request("DELETE", f"/Items/{playlist_id}")

    def upload_playlist_image(self, playlist_id: str, image: bytes) -> None:
        content_type = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"
        self._request("POST", f"/Items/{playlist_id}/Images/Primary",
                      raw=base64.b64encode(image), content_type=content_type)

    def _relative(self, path: str) -> str | None:
        if not path.startswith(self._media_root):
            return None
        return unicodedata.normalize("NFC", path[len(self._media_root):])

    def _request(self, method: str, path: str, query: dict[str, str] | None = None,
                 body: Any = None, raw: bytes | None = None, content_type: str = "application/json") -> Any:
        url = self._base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f'MediaBrowser Token="{self._key}"',
            "Content-Type": content_type,
        })
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
        return json.loads(payload) if payload else None
