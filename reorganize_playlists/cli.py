"""Command-line entry point: `migrate`, `import`, `export`, `rollback`."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from reorganize_playlists.deemix import DeemixSettings
from reorganize_playlists.deezer import DeezerClient, HttpDeezerClient
from reorganize_playlists.executor import Executor, rollback
from reorganize_playlists.history import commit, export_playlists, write_inventory
from reorganize_playlists.jellyfin import (
    HttpJellyfinClient, JellyfinClient, JellyfinUnavailable, load_settings, require_api_key,
)
from reorganize_playlists.importer import run_import
from reorganize_playlists.library import group_songs, scan
from reorganize_playlists.migrate import (
    CONFLICTS, MOVES, TRASHED, Move, Plan, RemoveDir, Trash, Write, plan_files, self_check,
)
from reorganize_playlists.report import Report

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = Path("/Users/john/Music/Deemix")
STATE_DIR = ".reorganize"


@dataclass
class Context:
    root: Path
    trash_root: Path
    env_path: Path
    deemix_settings: DeemixSettings
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    _deezer: DeezerClient | None = None
    _jellyfin: JellyfinClient | None = None

    @property
    def state(self) -> Path:
        return self.root / STATE_DIR

    @property
    def run_dir(self) -> Path:
        return self.state / "runs" / self.run_id

    def executor(self, command: str, dry_run: bool) -> Executor:
        return Executor(self.root, self.trash_root / self.run_id, self.run_dir / "manifest.json", command, dry_run)

    def deezer(self) -> DeezerClient:
        if self._deezer is None:
            self._deezer = HttpDeezerClient(self.state / "deezer-cache.json")
        return self._deezer

    def jellyfin(self, required: bool) -> JellyfinClient | None:
        if self._jellyfin is None:
            settings = load_settings(self.env_path)
            if not settings.api_key and not required:
                return None
            require_api_key(settings, self.env_path)
            self._jellyfin = HttpJellyfinClient(settings)
        return self._jellyfin

    def save_report(self, text: str) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        path = self.run_dir / "report.txt"
        path.write_text(text, encoding="utf-8")
        return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reorganize_playlists", description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="library root (default: %(default)s)")
    parser.add_argument("--trash", type=Path, help="trash folder outside the library (default: <root>-trash)")
    parser.add_argument("--env", type=Path, default=REPO / ".env", help="file with JELLYFIN_* settings")
    parser.add_argument("--deemix-config", type=Path, help="Deemix config.json (default: repo deemix-config/)")
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser("migrate", help="one-off migration out of legacy playlist folders")
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument("--phase", choices=["files", "playlists"], default="files",
                         help="files: move songs (Jellyfin stopped); playlists: create Jellyfin playlists "
                              "(Jellyfin running, after the file phase)")
    imp = commands.add_parser("import", help="import root-level Deemix playlist files after a Deemix session")
    imp.add_argument("--dry-run", action="store_true")
    commands.add_parser("export", help="export Jellyfin playlists and the inventory, and commit")
    rollback = commands.add_parser("rollback", help="undo a live run, including Jellyfin-side changes")
    rollback.add_argument("manifest", help="manifest.json printed by the run")
    return parser


def _deemix_config(args: argparse.Namespace) -> Path | None:
    if args.deemix_config:
        return Path(args.deemix_config)
    for candidate in (REPO / "deemix-config" / "config.json", args.root / "Config" / "config.json"):
        if candidate.is_file():
            return candidate
    return None


def main(argv: list[str] | None = None, deezer: DeezerClient | None = None,
         jellyfin: JellyfinClient | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.root).resolve()
    trash = Path(args.trash).resolve() if args.trash else root.with_name(root.name + "-trash")
    if trash.is_relative_to(root):
        print(f"error: the trash ({trash}) must be outside the library root", file=sys.stderr)
        return 2
    ctx = Context(root=root, trash_root=trash, env_path=Path(args.env),
                  deemix_settings=DeemixSettings.load(_deemix_config(args)),
                  _deezer=deezer, _jellyfin=jellyfin)
    try:
        if args.command == "migrate" and args.phase == "files":
            return migrate_files(ctx, args.dry_run)
        if args.command == "migrate":
            return import_playlists(ctx, args.dry_run, "migrate-playlists")
        if args.command == "import":
            return import_playlists(ctx, args.dry_run, "import")
        if args.command == "export":
            return export(ctx)
        return rollback_run(ctx, Path(args.manifest))
    except JellyfinUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if isinstance(ctx._deezer, HttpDeezerClient):
            ctx._deezer.flush()


def execute(ctx: Context, plan: Plan, executor: Executor) -> None:
    for op in plan.ops:
        if isinstance(op, Move):
            ok = executor.move(op.src, ctx.root / op.dst)
        elif isinstance(op, Trash):
            ok = executor.to_trash(op.src)
        elif isinstance(op, Write):
            ok = executor.write(ctx.root / op.dst, op.data, replace=op.replace)
        elif isinstance(op, RemoveDir):
            if not executor.remove_dir(ctx.root / op.path):
                plan.report.add("Folders not removed (not empty)", op.path)
            continue
        if not ok:
            plan.report.add("Failed actions", repr(op))


def _check_jellyfin_stopped(ctx: Context) -> bool:
    jellyfin = ctx.jellyfin(required=False)
    if jellyfin is None:
        print("warning: JELLYFIN_API_KEY is not set, so the tool cannot tell whether Jellyfin is running; "
              "make sure it is stopped (docker compose stop jellyfin).", file=sys.stderr)
        return True
    status = jellyfin.scan_status()
    if status == "scanning":
        print("error: Jellyfin is scanning the library. Stop it (docker compose stop jellyfin) before a live "
              "migration so real-time monitoring does not react to thousands of moves.", file=sys.stderr)
        return False
    if status == "idle":
        print("warning: Jellyfin is running; stop it (docker compose stop jellyfin) before a live migration so "
              "real-time monitoring does not react to the moves.", file=sys.stderr)
    return True


def record_history(ctx: Context, message: str) -> str:
    """Inventory + playlist exports (when Jellyfin is reachable) + a commit in the library repo."""
    write_inventory(ctx.root, scan(ctx.root))
    jellyfin = ctx.jellyfin(required=False)
    exported = "playlists not exported (Jellyfin not configured)"
    if jellyfin is not None and jellyfin.scan_status() != "unreachable":
        count = export_playlists(ctx.root, jellyfin, jellyfin.get_user_id(load_settings(ctx.env_path).user))
        exported = f"{count} playlists exported"
    elif jellyfin is not None:
        exported = "playlists not exported (Jellyfin not reachable; run `export` later)"
    committed = commit(ctx.root, message)
    return f"inventory written; {exported}; " + ("committed: " + message.splitlines()[0] if committed
                                                  else "nothing new to commit")


def _finish(ctx: Context, report: Report, title: str, executor: Executor, message: str | None,
            ok: bool = True) -> int:
    manifest = executor.save()
    if message and ok and not executor.dry_run:
        report.add("History", record_history(ctx, message))
    text = report.render(f"{title} [{'DRY RUN' if executor.dry_run else 'LIVE'}] {ctx.root}")
    print(text)
    print(f"Report: {ctx.save_report(text)}")
    if manifest:
        print(f"Manifest (for rollback): {manifest}")
    return 0 if ok else 1


def migrate_files(ctx: Context, dry_run: bool) -> int:
    if not dry_run and not _check_jellyfin_stopped(ctx):
        return 2
    for warning in ctx.deemix_settings.warnings():
        print(f"warning: {warning}", file=sys.stderr)
    songs = group_songs(scan(ctx.root))
    plan = plan_files(ctx.root, songs, ctx.deezer(), ctx.deemix_settings)
    if isinstance(ctx._deezer, HttpDeezerClient) and ctx._deezer.network_errors:
        errors = ctx._deezer.network_errors
        line = f"{len(errors)} failed requests; first: {errors[0]}"
        plan.report.add("Deezer network errors (those songs used the tag fallback; re-run the dry run)", line)
        print(f"warning: Deezer network errors: {line}", file=sys.stderr)
    executor = ctx.executor("migrate-files", dry_run)
    try:
        execute(ctx, plan, executor)
    finally:
        executor.save()
    ok = True
    if not dry_run:
        ok, message = self_check(songs, group_songs(scan(ctx.root)), plan, executor)
        plan.report.add("Self-check", message)
    report = plan.report
    summary = (f"migrate: {len(report.lines(MOVES))} songs into album folders; "
               f"{len(report.lines(TRASHED))} duplicate copies trashed; {len(report.lines(CONFLICTS))} conflicts")
    return _finish(ctx, report, "migrate (files)", executor, summary, ok)


def import_playlists(ctx: Context, dry_run: bool, command: str) -> int:
    jellyfin = ctx.jellyfin(required=True)
    assert jellyfin is not None
    migrating = command == "migrate-playlists"
    executor = ctx.executor(command, dry_run)
    try:
        result = run_import(ctx.root, jellyfin, load_settings(ctx.env_path).user, executor,
                            strict=migrating, take_root_artifacts=not migrating)
    finally:
        executor.save()
    if migrating:
        message = f"migrate: created {len(result.summary)} Jellyfin playlists"
    else:
        message = "import: " + ("; ".join(result.summary) or "no playlist changes")
    if len(result.summary) > 1 or migrating:
        message += "\n\n" + "\n".join(result.summary)
    return _finish(ctx, result.report, command, executor, message, result.ok)


def export(ctx: Context) -> int:
    ctx.jellyfin(required=True)
    executor = ctx.executor("export", dry_run=False)
    return _finish(ctx, Report(), "export", executor, "export: playlists and inventory")


def rollback_run(ctx: Context, manifest: Path) -> int:
    problems = rollback(manifest, ctx.jellyfin(required=False))
    report = Report()
    for problem in problems:
        report.add("Rollback problems", problem)
    report.add("Rollback", f"{'partially ' if problems else ''}undone: {manifest}")
    executor = ctx.executor("rollback", dry_run=False)
    return _finish(ctx, report, "rollback", executor, f"rollback: {manifest.parent.name}", ok=not problems)


if __name__ == "__main__":
    sys.exit(main())
