#!/usr/bin/env python3
"""
dedup_music.py — Remove duplicate audio files from a music library.

Priority: FLAC > MP3. Within the same format, larger file wins.
Duplicates are identified per-folder using fuzzy filename matching.
Losers (and their .lrc sidecars) are moved to _duplicates_trash/.
M3U/M3U8 playlist files in the same folder are updated to remove loser entries.

Usage:
    python3 dedup_music.py [--dry-run] [--threshold 0.90] [--root /path/to/dir]
    python3 dedup_music.py --rollback dedup_manifest_<timestamp>.json

Matching rules:
  - Cross-format pairs (FLAC vs MP3): fuzzy threshold applies (default 0.90).
  - Same-format pairs: only matched if stems are near-identical (threshold 0.98).
    This prevents false positives like "Song Pt. 1" vs "Song Pt. 2".

Manifest:
  Every live run writes dedup_manifest_<timestamp>.json recording all moves
  and playlist edits. Pass that file to --rollback to undo the run completely.
"""

import argparse
import difflib
import json
import logging
import os
import re
import shutil
import string
from datetime import datetime, timezone
from pathlib import Path


SKIP_DIRS = {"_duplicates_trash", "Config"}
AUDIO_EXTS = {".flac", ".mp3"}
SIDECAR_EXTS = {".lrc"}
PLAYLIST_EXTS = {".m3u", ".m3u8"}
FORMAT_PRIORITY = {".flac": 1, ".mp3": 2}  # lower = better
SAME_FORMAT_THRESHOLD = 0.98  # much stricter for same-format comparisons


def normalize(stem: str) -> str:
    """Lowercase, strip punctuation and extra whitespace for comparison."""
    stem = stem.lower()
    stem = stem.translate(str.maketrans("", "", string.punctuation))
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def collect_audio_files(root: Path) -> dict[Path, list[Path]]:
    """Return a dict mapping each folder to its list of audio files."""
    folder_map: dict[Path, list[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in-place so os.walk won't descend into them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        folder = Path(dirpath)
        audio = [folder / f for f in filenames if Path(f).suffix.lower() in AUDIO_EXTS]
        if audio:
            folder_map[folder] = audio
    return folder_map


def group_duplicates(files: list[Path], threshold: float) -> list[list[Path]]:
    """
    Group files within a folder that refer to the same song.

    Cross-format pairs (e.g. FLAC vs MP3) use `threshold` for similarity.
    Same-format pairs use SAME_FORMAT_THRESHOLD (0.98) to avoid false positives
    between distinct tracks that share long common prefixes (e.g. live sets,
    multi-part tracks).

    Returns a list of groups; singletons mean no duplicate.
    """
    items = [(f, normalize(f.stem)) for f in files]
    n = len(items)
    parent: list[int] = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            fi, stem_i = items[i]
            fj, stem_j = items[j]
            same_format = fi.suffix.lower() == fj.suffix.lower()
            effective_threshold = SAME_FORMAT_THRESHOLD if same_format else threshold
            ratio = difflib.SequenceMatcher(None, stem_i, stem_j).ratio()
            if ratio >= effective_threshold:
                union(i, j)

    groups_map: dict[int, list[Path]] = {}
    for i, (f, _) in enumerate(items):
        root_i = find(i)
        groups_map.setdefault(root_i, []).append(f)

    return list(groups_map.values())


def pick_winner(group: list[Path]) -> tuple[Path, list[Path]]:
    """
    Given a group of duplicate files, return (winner, [losers]).
    FLAC beats MP3; ties broken by file size (larger wins).
    """
    def sort_key(f: Path):
        priority = FORMAT_PRIORITY.get(f.suffix.lower(), 99)
        size = f.stat().st_size if f.exists() else 0
        return (priority, -size)

    sorted_group = sorted(group, key=sort_key)
    winner = sorted_group[0]
    losers = sorted_group[1:]
    return winner, losers


def find_sidecar(audio: Path) -> list[Path]:
    """Return any .lrc sidecar files that share the audio file's stem."""
    sidecars = []
    for ext in SIDECAR_EXTS:
        candidate = audio.with_suffix(ext)
        if candidate.exists():
            sidecars.append(candidate)
    return sidecars


def handle_loser_sidecar(
    sidecar: Path,
    winner: Path,
    root: Path,
    trash_root: Path,
    dry_run: bool,
    manifest: list | None = None,
) -> str | None:
    """
    Decide what to do with a loser's .lrc sidecar:
    - If the winner already has its own .lrc  -> trash the loser's copy.
    - If the winner has no .lrc               -> rename/copy it to match the winner's stem.
    Returns the filename that was trashed (for M3U removal), or None if it was kept.
    """
    winner_lrc = winner.with_suffix(sidecar.suffix)
    if winner_lrc.exists():
        logging.info(
            "  SIDECAR  winner already has %s, trashing loser copy %s%s",
            winner_lrc.name, sidecar.name, "  [dry-run]" if dry_run else "",
        )
        move_to_trash(sidecar, root, trash_root, dry_run, manifest)
        return sidecar.name
    else:
        logging.info(
            "  SIDECAR  transfer %s -> %s%s",
            sidecar.name, winner_lrc.name, "  [dry-run]" if dry_run else "",
        )
        if not dry_run:
            sidecar.rename(winner_lrc)
            if manifest is not None:
                manifest.append({
                    "action": "move",
                    "from": str(winner_lrc),
                    "to": str(sidecar),
                })
        return None  # not trashed, not removed from playlists


def move_to_trash(
    file: Path,
    root: Path,
    trash_root: Path,
    dry_run: bool,
    manifest: list | None = None,
) -> None:
    """Move a file into the trash directory, preserving relative path."""
    rel = file.relative_to(root)
    dest = trash_root / rel
    logging.info("  MOVE  %s  ->  %s%s", file, dest, "  [dry-run]" if dry_run else "")
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file), str(dest))
        if manifest is not None:
            manifest.append({"action": "move", "from": str(dest), "to": str(file)})


def update_playlists(
    folder: Path,
    removed_names: set[str],
    dry_run: bool,
    manifest: list | None = None,
) -> dict[Path, int]:
    """
    Remove entries for `removed_names` from every M3U/M3U8 file in `folder`.

    The M3U files produced by Deemix use bare filenames (no path prefix).
    Lines starting with '#' (directives/comments) are always preserved.
    A line matches a removed file if its basename (after stripping any path
    separators) equals one of the removed filenames.

    Returns a dict of {abs_playlist_path: entries_removed} for affected playlists.
    """
    stats: dict[Path, int] = {}
    for playlist in folder.iterdir():
        if playlist.suffix.lower() not in PLAYLIST_EXTS:
            continue
        try:
            original = playlist.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logging.warning("  Cannot read playlist %s: %s", playlist.name, exc)
            continue

        kept_lines = []
        removed_lines = []
        for line in original.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("#") or stripped == "":
                kept_lines.append(line)
                continue
            # Extract just the filename portion of the entry
            entry_name = Path(stripped.replace("\\", "/")).name
            if entry_name in removed_names:
                removed_lines.append(stripped)
                logging.info(
                    "  M3U  remove '%s' from %s%s",
                    stripped,
                    playlist.name,
                    "  [dry-run]" if dry_run else "",
                )
            else:
                kept_lines.append(line)

        if removed_lines:
            stats[playlist.resolve()] = len(removed_lines)
            if not dry_run:
                playlist.write_text("".join(kept_lines), encoding="utf-8")
                logging.info("  M3U  updated %s  (%d entr%s removed)",
                             playlist.name, len(removed_lines),
                             "y" if len(removed_lines) == 1 else "ies")
                if manifest is not None:
                    manifest.append({
                        "action": "playlist_edit",
                        "playlist": str(playlist.resolve()),
                        "original_content": original,
                    })
    return stats


def do_rollback(manifest_path: Path) -> None:
    """Undo a previous live run using its manifest file."""
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}")
        raise SystemExit(1)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = data.get("changes", [])
    if not entries:
        print("Manifest has no changes to roll back.")
        return

    print(f"Rolling back {len(entries)} change(s) from manifest: {manifest_path.name}")
    errors = 0
    for entry in reversed(entries):  # reverse order so renames undo cleanly
        action = entry["action"]
        if action == "move":
            src = Path(entry["from"])
            dst = Path(entry["to"])
            if not src.exists():
                print(f"  SKIP (already gone): {src}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            print(f"  RESTORED  {dst}")
        elif action == "playlist_edit":
            playlist = Path(entry["playlist"])
            original_content = entry["original_content"]
            playlist.write_text(original_content, encoding="utf-8")
            print(f"  RESTORED  {playlist}")
        else:
            print(f"  UNKNOWN action '{action}', skipping.")
            errors += 1

    print(f"\nRollback complete. Errors: {errors}")
    if errors == 0:
        manifest_path.unlink()
        print(f"Manifest deleted: {manifest_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove duplicate audio files, keeping higher quality.")
    parser.add_argument(
        "--root",
        default="/Users/john/Music/Deemix",
        help="Root music directory (default: /Users/john/Music/Deemix)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without moving any files.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.90,
        help="Fuzzy match similarity threshold for cross-format pairs 0.0-1.0 (default: 0.90).",
    )
    parser.add_argument(
        "--rollback",
        metavar="MANIFEST",
        help="Path to a manifest JSON file produced by a previous live run. Undoes all changes.",
    )
    args = parser.parse_args()

    if args.rollback:
        do_rollback(Path(args.rollback))
        return

    root = Path(args.root).resolve()
    trash_root = root / "_duplicates_trash"
    log_file = root / "dedup_music.log"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest_path = root / f"dedup_manifest_{timestamp}.json"
    manifest: list = []  # populated only during live runs

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    logging.info("=" * 70)
    logging.info("dedup_music.py  mode=%s  root=%s  threshold=%.2f", mode, root, args.threshold)
    logging.info("=" * 70)

    folder_map = collect_audio_files(root)

    # Stats: folder_rel_path -> {kept, removed, groups}
    folder_stats: dict[str, dict] = {}
    total_groups = 0
    total_kept = 0
    total_moved = 0
    global_losers: set[str] = set()  # all trashed basenames, for root-level m3u update
    m3u_stats: dict[Path, int] = {}   # absolute playlist path -> entries removed
    live_manifest: list | None = None if args.dry_run else manifest

    for folder, files in sorted(folder_map.items()):
        groups = group_duplicates(files, args.threshold)

        # Collect all losers for this folder before touching playlists
        folder_losers: set[str] = set()
        folder_kept = 0
        folder_removed = 0
        folder_groups = 0

        for group in groups:
            if len(group) < 2:
                continue
            winner, losers = pick_winner(group)
            folder_groups += 1
            total_groups += 1
            folder_kept += 1
            logging.info(
                "DUPLICATE GROUP in %s  (winner: %s)",
                folder.relative_to(root),
                winner.name,
            )
            for loser in losers:
                logging.info("  LOSER: %s", loser.name)
                folder_losers.add(loser.name)
                move_to_trash(loser, root, trash_root, args.dry_run, live_manifest)
                folder_removed += 1
                total_moved += 1
                # Handle .lrc sidecars
                for sc in find_sidecar(loser):
                    trashed_name = handle_loser_sidecar(
                        sc, winner, root, trash_root, args.dry_run, live_manifest
                    )
                    if trashed_name:
                        folder_losers.add(trashed_name)

        # Update any M3U playlists in this folder
        if folder_losers:
            sub_stats = update_playlists(folder, folder_losers, args.dry_run, live_manifest)
            m3u_stats.update(sub_stats)
            global_losers.update(folder_losers)

        if folder_groups > 0:
            total_kept += folder_kept
            folder_stats[str(folder.relative_to(root))] = {
                "groups": folder_groups,
                "kept": folder_kept,
                "removed": folder_removed,
            }

    # Update root-level m3u files (they reference nested paths but basename matching works)
    if global_losers:
        logging.info("Updating root-level playlists in %s", root)
        root_stats = update_playlists(root, global_losers, args.dry_run, live_manifest)
        m3u_stats.update(root_stats)

    # Write manifest for live runs
    if not args.dry_run and manifest:
        manifest_data = {
            "created": timestamp,
            "root": str(root),
            "threshold": args.threshold,
            "changes": manifest,
        }
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logging.info("Manifest written: %s", manifest_path)

    # ------------------------------------------------------------------ #
    #  DASHBOARD SUMMARY                                                   #
    # ------------------------------------------------------------------ #
    print("\n" + "=" * 70)
    print(f"  DEDUP SUMMARY  [{mode}]")
    print("=" * 70)

    if folder_stats:
        # Column widths
        col_folder = max(len(k) for k in folder_stats) + 2
        col_folder = max(col_folder, 8)
        header = f"  {'Folder':<{col_folder}}  {'Dup Songs':>9}  {'Kept':>5}  {'Removed':>7}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for rel_path, s in sorted(folder_stats.items()):
            print(
                f"  {rel_path:<{col_folder}}  {s['groups']:>9}  {s['kept']:>5}  {s['removed']:>7}"
            )
        print("  " + "-" * (len(header) - 2))
        print(
            f"  {'TOTAL':<{col_folder}}  {total_groups:>9}  {total_kept:>5}  {total_moved:>7}"
        )
    else:
        print("  No duplicates found.")

    # M3U section
    if m3u_stats:
        print()
        total_m3u_files = len(m3u_stats)
        total_m3u_entries = sum(m3u_stats.values())
        # Display relative paths so Untitled.m3u files are distinguishable
        m3u_display = {
            str(abs_path.relative_to(root)): count
            for abs_path, count in m3u_stats.items()
        }
        col_pl = max(len(k) for k in m3u_display) + 2
        col_pl = max(col_pl, 8)
        m3u_header = f"  {'Playlist file':<{col_pl}}  {'Entries removed':>15}"
        print(m3u_header)
        print("  " + "-" * (len(m3u_header) - 2))
        for pl_name, count in sorted(m3u_display.items()):
            print(f"  {pl_name:<{col_pl}}  {count:>15}")
        print("  " + "-" * (len(m3u_header) - 2))
        print(f"  {f'{total_m3u_files} playlists updated':<{col_pl}}  {total_m3u_entries:>15}")

    print("=" * 70)
    if args.dry_run:
        print("  DRY-RUN: no files were modified.")
        print("  Re-run without --dry-run to apply changes.")
    else:
        print(f"  Files moved to: {trash_root}")
        if manifest:
            print(f"  Manifest:       {manifest_path}")
            print(f"  To rollback:    python3 dedup_music.py --rollback {manifest_path}")
        print("  Inspect and delete that folder manually when satisfied.")
    print("=" * 70 + "\n")

    logging.info("-" * 70)
    logging.info(
        "DONE  duplicate_groups=%d  kept=%d  files_moved=%d  mode=%s",
        total_groups,
        total_kept,
        total_moved,
        mode,
    )


if __name__ == "__main__":
    main()
