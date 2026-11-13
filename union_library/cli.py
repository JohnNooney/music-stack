"""Build and maintain the union root Jellyfin scans: one symlink per album across both trees."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from reorganize_playlists.library import nfc
from union_library.plan import (
    DEFAULT_EXCLUDES, FAILED, NEXT_STEP, Link, Plan, Unlink, parse_overrides, plan_union,
)

REPO = Path(__file__).resolve().parent.parent
MUSIC = Path("/Users/john/Music")
STATE_DIR = ".union"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="union_library", description=__doc__)
    parser.add_argument("--union", type=Path, default=MUSIC / "Jellyfin",
                        help="union root (default: %(default)s)")
    parser.add_argument("--deemix", type=Path, default=MUSIC / "Deemix",
                        help="Deemix library root (default: %(default)s)")
    parser.add_argument("--lidarr", type=Path, default=MUSIC / "Lidarr" / "media" / "music",
                        help="Lidarr music root (default: %(default)s)")
    parser.add_argument("--overrides", type=Path, default=REPO / "union_library_overrides",
                        help="overrides file (default: %(default)s)")
    parser.add_argument("--exclude", action="append", default=[], metavar="NAME",
                        help="extra Deemix root entries never mirrored (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def execute(plan: Plan, union: Path, dry_run: bool) -> None:
    """The only filesystem effects: symlink/unlink inside the union root."""
    for op in plan.ops:
        if dry_run:
            continue
        try:
            path = union / op.name
            if isinstance(op, Link):
                if os.path.islink(path):
                    path.unlink()
                os.symlink(op.target, path)
            elif isinstance(op, Unlink):
                path.unlink()
        except OSError as exc:
            plan.report.add(FAILED, f"{op!r}: {exc}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    union, deemix, lidarr = (Path(p).resolve() for p in (args.union, args.deemix, args.lidarr))
    if not deemix.is_dir():
        print(f"error: Deemix root {deemix} does not exist", file=sys.stderr)
        return 2
    if not lidarr.is_dir():
        print(f"error: Lidarr root {lidarr} does not exist", file=sys.stderr)
        return 2
    for source in (deemix, lidarr):
        if union == source or union.is_relative_to(source) or source.is_relative_to(union):
            print(f"error: the union root {union} must be a sibling of {source}", file=sys.stderr)
            return 2
    try:
        directives = parse_overrides(args.overrides) if Path(args.overrides).is_file() else []
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    excludes = DEFAULT_EXCLUDES | {nfc(x) for x in args.exclude}
    plan = plan_union(union, deemix, lidarr, directives, excludes)
    if not args.dry_run and not union.is_dir():
        union.mkdir(parents=True)

    execute(plan, union, args.dry_run)
    plan.report.add(NEXT_STEP, "run a library scan in Jellyfin so the union changes are picked up")
    text = plan.report.render(f"union_library [{'DRY RUN' if args.dry_run else 'LIVE'}] {union}")
    print(text)
    if union.is_dir():
        run_dir = union / STATE_DIR / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        run_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "report.txt"
        report_path.write_text(text, encoding="utf-8")
        print(f"Report: {report_path}")
    return 1 if plan.report.lines(FAILED) else 0


if __name__ == "__main__":
    sys.exit(main())
