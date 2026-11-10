"""Applies changes while recording each one in a JSON manifest; rollback replays it in reverse."""

from __future__ import annotations

import base64
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reorganize_playlists.jellyfin import JellyfinClient


class Executor:
    """Never overwrites. In dry-run mode every method is a no-op that reports success."""

    def __init__(self, root: Path, trash: Path, manifest_path: Path, command: str, dry_run: bool) -> None:
        self.root = root
        self.trash = trash
        self.manifest_path = manifest_path
        self.dry_run = dry_run
        self.actions: list[dict[str, Any]] = []
        self.header = {"command": command, "root": str(root), "trash": str(trash),
                       "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def _record(self, **action: Any) -> None:
        self.actions.append(action)

    def _mkdirs(self, directory: Path) -> None:
        missing = []
        while not directory.exists():
            missing.append(directory)
            directory = directory.parent
        for d in reversed(missing):
            d.mkdir()
            self._record(op="mkdir", path=str(d))

    def move(self, src: Path, dst: Path) -> bool:
        if self.dry_run:
            return True
        if dst.exists() or not src.exists():
            return False
        self._mkdirs(dst.parent)
        shutil.move(str(src), str(dst))
        self._record(op="move", src=str(src), dst=str(dst))
        return True

    def trash_path(self, src: Path) -> Path:
        return self.trash / src.relative_to(self.root)

    def to_trash(self, src: Path) -> bool:
        return self.move(src, self.trash_path(src))

    def write(self, path: Path, data: bytes, replace: bool = False) -> bool:
        if self.dry_run:
            return True
        if path.exists() and not replace:
            return False
        previous = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
        self._mkdirs(path.parent)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        self._record(op="write", path=str(path), previous=previous)
        return True

    def remove_dir(self, path: Path) -> bool:
        if self.dry_run:
            return True
        try:
            path.rmdir()
        except OSError:
            return False
        self._record(op="rmdir", path=str(path))
        return True

    def jellyfin_created(self, playlist_id: str) -> None:
        self._record(op="jellyfin_create", playlist_id=playlist_id)

    def jellyfin_appended(self, playlist_id: str, entry_ids: list[str]) -> None:
        self._record(op="jellyfin_append", playlist_id=playlist_id, entry_ids=entry_ids)

    def save(self) -> Path | None:
        if self.dry_run or not self.actions:
            return None
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps({**self.header, "actions": self.actions},
                                                 indent=1, ensure_ascii=False), encoding="utf-8")
        return self.manifest_path


def rollback(manifest_path: Path, jellyfin: JellyfinClient | None) -> list[str]:
    """Undo every recorded action, newest first. Returns problems encountered."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for action in reversed(data["actions"]):
        op = action["op"]
        if op == "move":
            src, dst = Path(action["src"]), Path(action["dst"])
            if not dst.exists():
                problems.append(f"missing, cannot restore: {dst}")
            elif src.exists():
                problems.append(f"occupied, not restored: {src}")
            else:
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
        elif op == "mkdir":
            try:
                Path(action["path"]).rmdir()
            except OSError:
                pass  # not empty (e.g. user added files): leave it
        elif op == "rmdir":
            Path(action["path"]).mkdir(parents=True, exist_ok=True)
        elif op == "write":
            path = Path(action["path"])
            if action["previous"] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(base64.b64decode(action["previous"]))
        elif op in ("jellyfin_create", "jellyfin_append"):
            if jellyfin is None:
                problems.append(f"Jellyfin not available, not undone: {op} {action['playlist_id']}")
            elif op == "jellyfin_create":
                jellyfin.delete_playlist(action["playlist_id"])
            else:
                jellyfin.remove_from_playlist(action["playlist_id"], action["entry_ids"])
        else:
            problems.append(f"unknown action {op!r}")
    if not problems:
        os.replace(manifest_path, manifest_path.with_suffix(".rolled-back.json"))
    return problems
