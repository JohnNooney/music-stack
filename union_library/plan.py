"""Plan the union root: one relative symlink per album across the Deemix and Lidarr trees.

Entry names that exist in the Deemix tree are kept verbatim — Jellyfin item IDs are
MD5(type + path), so the path string is the item's identity (see docs/explanation/specs/0003).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from reorganize_playlists.library import AUDIO_EXTS, nfc, normalise_words
from reorganize_playlists.report import Report

LINKED = "Linked (new)"
RELINKED = "Relinked (Deemix → Lidarr)"
AMBIGUOUS = "Ambiguous matches (kept Deemix)"
OVERRIDDEN = "Overridden"
LOOSE = "Loose-root items mirrored"
EXCLUDED = "Excluded"
FOREIGN = "Foreign entries (untouched)"
PRUNED = "Pruned dangling links"
SPLIT = "Non-disc subfolders (Jellyfin will split these)"
FAILED = "Failed actions"
NEXT_STEP = "Next step"

SECTION_ORDER = [LINKED, RELINKED, AMBIGUOUS, OVERRIDDEN, LOOSE, EXCLUDED, FOREIGN, PRUNED, SPLIT,
                 FAILED]

# Deemix root entries that are tooling, not library content, and must not be mirrored.
DEFAULT_EXCLUDES = {"Config", "_duplicates_trash", "Deemix-trash",
                    ".artifacts", ".git", ".playlists", ".reorganize"}


def _is_volume_noise(name: str) -> bool:
    """macOS writes these alongside real entries on non-Apple volumes (AppleDouble `._*`
    sidecars, `.DS_Store`). They are filesystem metadata, never library content."""
    return name.startswith("._") or name == ".DS_Store"

_YEAR = re.compile(r"\s*\(\d{4}\)\s*$")
_DIRECTIVE = re.compile(r"^(match|prefer-deemix|keep-both)\s+(.+?)\s*=\s*([^/]+?)/(.+?)\s*$")

# AlbumParser.IsMultiPart at v12.4 (Emby.Naming): basename cleaned of separators, a stacking
# prefix, then a number. Subfolders with audio that fail this test become their own albums.
_DISC_PREFIXES = ("cd", "digital media", "disc", "disk", "vol", "volume", "part", "act")
_DISC_CLEAN = re.compile(r"[-.()\s]+")
# Wider than the library's AUDIO_EXTS — downloads can arrive in any common audio format.
_SPLIT_AUDIO_EXTS = AUDIO_EXTS | {".m4a", ".ogg", ".opus", ".wav", ".wma", ".aif", ".aiff"}


def _is_disc_folder(name: str) -> bool:
    cleaned = _DISC_CLEAN.sub(" ", name).lstrip()
    lower = cleaned.casefold()
    for prefix in _DISC_PREFIXES:
        if lower.startswith(prefix):
            first = cleaned[len(prefix):].strip().partition(" ")[0]
            try:
                int(first)
                return True
            except ValueError:
                continue
    return False


def _non_disc_music_subdirs(album_dir: str) -> list[str]:
    """Subfolders holding audio whose names aren't disc names — Jellyfin splits them off."""
    bad: list[str] = []
    try:
        children = _scandir(Path(album_dir))
    except OSError:
        return bad
    for child in children:
        if not child.is_dir() or child.name.startswith(".") or _is_disc_folder(child.name):
            continue
        try:
            if any(e.is_file() and not e.name.startswith(".")
                   and Path(e.name).suffix.lower() in _SPLIT_AUDIO_EXTS
                   for e in os.scandir(child.path)):
                bad.append(nfc(child.name))
        except OSError:
            continue
    return bad


@dataclass(frozen=True)
class Link:
    """Create a union entry (replaces an existing symlink with the same name)."""
    name: str
    target: str  # relative path written into the symlink, e.g. ../Deemix/X - Y


@dataclass(frozen=True)
class Unlink:
    """Remove a dangling union entry."""
    name: str


Op = Link | Unlink


@dataclass
class Plan:
    ops: list[Op] = field(default_factory=list)
    report: Report = field(default_factory=Report)


@dataclass(frozen=True)
class Directive:
    kind: Literal["match", "prefer-deemix", "keep-both"]
    deemix: str     # Deemix album folder name
    artist: str     # Lidarr artist dir name
    album: str      # Lidarr album dir name
    line: str       # original line, for reporting


def parse_overrides(path: Path) -> list[Directive]:
    """One directive per line; `#` comments and blanks ignored. Malformed lines raise ValueError."""
    directives = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _DIRECTIVE.match(line)
        if not m:
            raise ValueError(f"{path}:{number}: not a directive: {raw.strip()!r} "
                             "(want `match|prefer-deemix|keep-both <deemix-name> = <artist>/<album>`)")
        kind, deemix, artist, album = m.groups()
        directives.append(Directive(kind, nfc(deemix), nfc(artist), nfc(album), line))  # type: ignore[arg-type]
    return directives


@dataclass(frozen=True)
class LidarrAlbum:
    artist: str
    album: str  # dir name, e.g. "Head Hunters (1973)"


def _key(artist: str, album: str) -> tuple[str, str]:
    """Match key: normalised album artist + album with a trailing (YYYY) stripped."""
    return normalise_words(artist), normalise_words(_YEAR.sub("", album))


def _deemix_key(name: str) -> tuple[str, str] | None:
    parts = name.split(" - ", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    return _key(parts[0], parts[1])


def _scandir(path: Path) -> list[os.DirEntry[str]]:
    return sorted(os.scandir(path), key=lambda e: nfc(e.name))


def _scan_lidarr(lidarr: Path) -> list[LidarrAlbum]:
    albums = []
    for artist_entry in _scandir(lidarr):
        if artist_entry.name.startswith(".") or not artist_entry.is_dir():
            continue
        for album_entry in _scandir(Path(artist_entry.path)):
            if not album_entry.name.startswith(".") and album_entry.is_dir():
                albums.append(LidarrAlbum(nfc(artist_entry.name), nfc(album_entry.name)))
    return albums


@dataclass(frozen=True)
class Desired:
    """A wanted union entry: its relative link target and how the plan arrived at it."""
    target: str
    origin: Literal["album", "loose", "lidarr-only", "ambiguous", "override"]


def _managed(entry: os.DirEntry[str], sources: tuple[Path, Path]) -> bool:
    """A union symlink is ours (retargetable) only when it points inside a source tree."""
    try:
        resolved = Path(entry.path).resolve()
    except (OSError, RuntimeError):
        return False
    return any(resolved.is_relative_to(source) for source in sources)


def plan_union(union: Path, deemix: Path, lidarr: Path, directives: list[Directive],
               excludes: set[str]) -> Plan:
    plan = Plan()
    lines: dict[str, list[str]] = {section: [] for section in SECTION_ORDER}

    def rel(target: Path) -> str:
        return nfc(os.path.relpath(target, union))

    desired: dict[str, Desired] = {}   # entry name -> wanted entry

    # --- Deemix root: album folders vs loose items vs excluded tooling ---
    deemix_albums: dict[str, tuple[str, str]] = {}   # name -> match key
    loose: list[str] = []
    for entry in _scandir(deemix):
        name = nfc(entry.name)
        if name in excludes:
            lines[EXCLUDED].append(f"{name} ({'directory' if entry.is_dir() else 'file'})")
            continue
        if _is_volume_noise(name):
            continue
        key = _deemix_key(name) if entry.is_dir() else None
        if key is not None:
            deemix_albums[name] = key
        else:
            loose.append(name)
        if entry.is_dir():
            for bad in _non_disc_music_subdirs(entry.path):
                lines[SPLIT].append(f"Deemix/{name}: '{bad}' holds audio but isn't a disc name "
                                    f"(CD N / Disc N / Volume N) — Jellyfin shows it as a "
                                    f"separate album; rename it at the source")

    # --- Lidarr tree: <Artist>/<Album (Year)> ---
    lidarr_albums = _scan_lidarr(lidarr)
    for album in lidarr_albums:
        for bad in _non_disc_music_subdirs(str(lidarr / album.artist / album.album)):
            lines[SPLIT].append(f"Lidarr/{album.artist}/{album.album}: '{bad}' holds audio but "
                                f"isn't a disc name (CD N / Disc N / Volume N) — Jellyfin shows "
                                f"it as a separate album; rename it at the source")
    lidarr_by_name = {(a.artist, a.album): a for a in lidarr_albums}

    lidarr_by_key: dict[tuple[str, str], list[LidarrAlbum]] = {}
    for album in lidarr_albums:
        lidarr_by_key.setdefault(_key(album.artist, album.album), []).append(album)
    deemix_by_key: dict[tuple[str, str], list[str]] = {}
    for name, key in deemix_albums.items():
        deemix_by_key.setdefault(key, []).append(name)

    consumed: set[LidarrAlbum] = set()   # deduped into a Deemix-named entry
    held: set[LidarrAlbum] = set()       # ambiguous, waiting on an override
    handled: set[str] = set()            # Deemix albums settled by a directive

    # --- Overrides ---
    for d in directives:
        target_lidarr = lidarr_by_name.get((d.artist, d.album))
        if d.deemix not in deemix_albums:
            lines[OVERRIDDEN].append(f"unused: {d.line} (no such Deemix album folder)")
            continue
        if d.deemix in handled:
            lines[OVERRIDDEN].append(f"unused: {d.line} (already settled by an earlier directive)")
            continue
        if target_lidarr is None:
            lines[OVERRIDDEN].append(f"unused: {d.line} (no such Lidarr album)")
            continue
        handled.add(d.deemix)
        if d.kind == "match":
            desired[d.deemix] = Desired(rel(lidarr / d.artist / d.album), "override")
            consumed.add(target_lidarr)
        else:
            desired[d.deemix] = Desired(rel(deemix / d.deemix), "override")
            if d.kind == "prefer-deemix":
                consumed.add(target_lidarr)
        lines[OVERRIDDEN].append(f"{d.kind} {d.deemix} = {d.artist}/{d.album} "
                                 f"-> {desired[d.deemix].target}")

    # --- Overlap matching for the rest ---
    for key, names in deemix_by_key.items():
        remaining = [n for n in names if n not in handled]
        if not remaining:
            continue
        candidates = [a for a in lidarr_by_key.get(key, []) if a not in consumed]
        if not candidates:
            for name in remaining:
                desired[name] = Desired(rel(deemix / name), "album")
        elif len(remaining) == 1 and len(candidates) == 1:
            name = remaining[0]
            desired[name] = Desired(rel(lidarr / candidates[0].artist / candidates[0].album), "album")
            consumed.add(candidates[0])
        else:
            for name in remaining:
                desired[name] = Desired(rel(deemix / name), "ambiguous")
                choices = ", ".join(f"'{a.artist}/{a.album}'" for a in candidates)
                lines[AMBIGUOUS].append(f"'{name}' matches multiple Lidarr albums: {choices} "
                                        f"— keeping {desired[name].target} (set an override to dedupe)")
            held.update(candidates)

    # --- Loose Deemix root items mirrored verbatim ---
    for name in loose:
        desired[name] = Desired(rel(deemix / name), "loose")

    # --- Lidarr-only albums get constructed '<Artist> - <Album (Year)>' entries ---
    for album in lidarr_albums:
        if album in consumed or album in held:
            continue
        name = f"{album.artist} - {album.album}"
        if name in desired:
            lines[FAILED].append(f"'{album.artist}/{album.album}': entry name '{name}' is already "
                                 f"taken — skipped")
            continue
        desired[name] = Desired(rel(lidarr / album.artist / album.album), "lidarr-only")

    # --- Existing union entries: keep, retarget, prune or leave foreign ---
    for entry in _scandir(union) if union.is_dir() else []:
        name = nfc(entry.name)
        dangling = entry.is_symlink() and not os.path.exists(entry.path)
        if name not in desired:
            if dangling:
                plan.ops.append(Unlink(name))
                lines[PRUNED].append(f"{name} -> {os.readlink(entry.path)} (target gone)")
            elif _is_volume_noise(name) and entry.is_symlink() and _managed(entry, (deemix, lidarr)):
                plan.ops.append(Unlink(name))
                lines[PRUNED].append(f"{name} -> {os.readlink(entry.path)} "
                                     "(volume noise is never mirrored)")
            elif not name.startswith("."):
                # dot-entries are tooling; the tool and Jellyfin both ignore them
                kind = "symlink" if entry.is_symlink() else ("directory" if entry.is_dir() else "file")
                detail = f" -> {os.readlink(entry.path)}" if entry.is_symlink() else ""
                lines[FOREIGN].append(f"{name} ({kind}{detail})")
            continue
        want = desired.pop(name)
        if not entry.is_symlink():
            lines[FAILED].append(f"'{name}': a non-symlink already exists in the union root — "
                                 f"wanted link to {want.target}; left alone")
        elif not _managed(entry, (deemix, lidarr)):
            lines[FAILED].append(f"'{name}': a foreign symlink -> {os.readlink(entry.path)} already "
                                 f"exists — wanted link to {want.target}; left alone")
        elif os.readlink(entry.path) != want.target:
            plan.ops.append(Link(name, want.target))
            old = os.readlink(entry.path)
            if want.origin == "override":
                lines[OVERRIDDEN].append(f"retargeted: {name} -> {want.target} (was {old})")
            else:
                lines[RELINKED].append(f"{name} -> {want.target} (was {old})")
        # else: already correct

    # --- New links ---
    for name in sorted(desired):
        want = desired[name]
        plan.ops.append(Link(name, want.target))
        if want.origin in ("override", "ambiguous"):
            continue   # already reported under Overridden / Ambiguous matches
        if want.origin == "loose":
            lines[LOOSE].append(f"{name} -> {want.target}")
        else:
            lines[LINKED].append(f"{name} -> {want.target}")

    for section in SECTION_ORDER:
        for line in lines[section]:
            plan.report.add(section, line)
    return plan
