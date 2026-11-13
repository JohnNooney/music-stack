"""Poll the source trees; when they are quiet, run `migrate` → `union_library` → `import`.

Detection is polling, not filesystem events: every WATCH_INTERVAL_S the watcher recomputes a
fingerprint of the directory entries the tools care about (names + mtimes, never contents).
A job fires only after the fingerprint has been stable for QUIET_PERIOD_S, and each job's
trigger-set hash is remembered so a failed run refires only on change or after RETRY_COOLDOWN_S.
See docs/specs/0004-library-watcher.md and ADR 0005.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from reorganize_playlists.jellyfin import HttpJellyfinClient, JellyfinClient, load_settings
from reorganize_playlists.library import PLAYLIST_EXTS, nfc
from union_library.plan import (
    AMBIGUOUS, DEFAULT_EXCLUDES, LINKED, LOOSE, OVERRIDDEN, PRUNED, RELINKED,
)

REPO = Path(__file__).resolve().parent.parent
MUSIC = Path("/Users/john/Music")
STATE_DIR = ".reorganize"
STATE_FILE = "watcher-state.json"

MODES = ("auto", "dry", "off")
JELLYFIN_KEYS = ("JELLYFIN_URL", "JELLYFIN_API_KEY", "JELLYFIN_USER", "JELLYFIN_MEDIA_ROOT")

# The union report sections that carry link ops. Overridden and Ambiguous matches lines appear
# even on no-op runs (they describe the plan, not the ops), so they may over-nudge — harmless —
# while the alternative misses real links a run created through a directive or ambiguity.
_OPS_SECTION = re.compile(r"^(" + "|".join(re.escape(s) for s in
                          (LINKED, RELINKED, LOOSE, PRUNED, OVERRIDDEN, AMBIGUOUS)) + r") \(\d+\)",
                          re.M)
_RETARGETED = re.compile(r"^ {2}retargeted:", re.M)


def _union_made_links(output: str) -> bool:
    return bool(_OPS_SECTION.search(output) or _RETARGETED.search(output))


class Clock(Protocol):
    def time(self) -> float: ...       # wall time, persisted for cross-restart cooldowns
    def monotonic(self) -> float: ...  # quiet-period timing
    def sleep(self, seconds: float) -> None: ...


class _RealClock:
    def time(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True)
class RunResult:
    code: int
    output: str


Runner = Callable[[list[str]], RunResult]


def _subprocess_run(argv: list[str]) -> RunResult:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return RunResult(proc.returncode, proc.stdout + proc.stderr)


@dataclass(frozen=True)
class Fingerprint:
    """The watcher's view of the world: names + mtimes of the entries the tools act on."""
    deemix: frozenset[tuple[str, int]]      # top-level library-root entries, tooling excluded
    lidarr: frozenset[tuple[str, int]]      # "<Artist>" and "<Artist>/<Album>" two levels deep
    playlists: frozenset[tuple[str, int]]   # Deemix-root playlist files (the import trigger)
    overrides: int                          # union_library_overrides mtime, -1 when absent


def fingerprint(deemix: Path, lidarr: Path, overrides: Path) -> Fingerprint | None:
    """None when a source root can't be read (e.g. a dropped bind mount): an empty scan would
    look like mass deletion and union would prune every link."""
    top: set[tuple[str, int]] = set()
    playlists: set[tuple[str, int]] = set()
    try:
        entries = list(os.scandir(deemix))
        artists = list(os.scandir(lidarr))
    except OSError:
        return None
    for entry in entries:
        name = nfc(entry.name)
        if name in DEFAULT_EXCLUDES:
            continue
        try:
            mtime = entry.stat(follow_symlinks=False).st_mtime_ns
        except OSError:
            continue
        top.add((name, mtime))
        if entry.is_file() and not name.startswith(".") and Path(name).suffix.lower() in PLAYLIST_EXTS:
            playlists.add((name, mtime))

    lidarr_entries: set[tuple[str, int]] = set()
    for artist in artists:
        if artist.name.startswith(".") or not artist.is_dir():
            continue
        try:
            lidarr_entries.add((nfc(artist.name), artist.stat(follow_symlinks=False).st_mtime_ns))
        except OSError:
            pass
        try:
            albums = list(os.scandir(artist.path))
        except OSError:
            continue
        for album in albums:
            if album.name.startswith(".") or not album.is_dir():
                continue
            try:
                lidarr_entries.add((f"{nfc(artist.name)}/{nfc(album.name)}",
                                    album.stat(follow_symlinks=False).st_mtime_ns))
            except OSError:
                continue

    try:
        overrides_mtime = overrides.stat().st_mtime_ns
    except OSError:
        overrides_mtime = -1
    return Fingerprint(frozenset(top), frozenset(lidarr_entries),
                       frozenset(playlists), overrides_mtime)


# What each job's trigger set is made of. A Lidarr-only change leaves the Deemix component
# untouched, which is what lets `migrate` skip a change it can do nothing about.
_TRIGGER: dict[str, Callable[[Fingerprint], object]] = {
    "migrate": lambda fp: sorted(fp.deemix),
    "union": lambda fp: [sorted(fp.deemix), sorted(fp.lidarr), fp.overrides],
    "import": lambda fp: sorted(fp.playlists),
}


def _digest(component: object) -> str:
    return hashlib.sha256(json.dumps(component).encode()).hexdigest()[:16]


@dataclass
class Attempt:
    """The trigger-set hash a job last ran against, and when it may legitimately refire."""
    hash: str
    attempted_at: float
    retry_after: float | None  # None: suppressed until the trigger set changes


def _load_state(path: Path) -> dict[str, Attempt]:
    try:
        jobs = json.loads(path.read_text(encoding="utf-8"))["jobs"]
        if not isinstance(jobs, dict):
            return {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    attempted = {}
    for name, entry in jobs.items():
        try:
            retry = entry.get("retry_after")
            attempted[name] = Attempt(str(entry["hash"]), float(entry["attempted_at"]),
                                      None if retry is None else float(retry))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return attempted


def _save_state(path: Path, attempted: dict[str, Attempt]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    jobs = {name: {"hash": a.hash, "attempted_at": a.attempted_at, "retry_after": a.retry_after}
            for name, a in attempted.items()}
    path.write_text(json.dumps({"jobs": jobs}, indent=2) + "\n", encoding="utf-8")


def _materialise_env(source: Path) -> Path:
    """Effective JELLYFIN_* settings for the child processes: the --env file overlaid with the
    watcher's own environment, so the compose JELLYFIN_URL override reaches the tools unchanged
    (they read an env file, not os.environ). Written to the tempdir — it holds the API key, so
    it must not land in the source trees, which other containers can read."""
    settings = load_settings(source)
    values = {"JELLYFIN_URL": settings.url, "JELLYFIN_API_KEY": settings.api_key,
              "JELLYFIN_USER": settings.user, "JELLYFIN_MEDIA_ROOT": settings.media_root}
    for key in JELLYFIN_KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    dest = Path(tempfile.gettempdir()) / "library_watcher-jellyfin.env"
    dest.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    dest.chmod(0o600)
    return dest


def _env_seconds(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"error: {name}={raw!r} is not a number of seconds", file=sys.stderr)
        raise SystemExit(2)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="library_watcher", description=__doc__)
    parser.add_argument("--deemix", type=Path, default=MUSIC / "Deemix",
                        help="Deemix library root (default: %(default)s)")
    parser.add_argument("--lidarr", type=Path, default=MUSIC / "Lidarr" / "media" / "music",
                        help="Lidarr music root (default: %(default)s)")
    parser.add_argument("--union", type=Path, default=MUSIC / "Jellyfin",
                        help="union root (default: %(default)s)")
    parser.add_argument("--overrides", type=Path, default=REPO / "union_library_overrides",
                        help="union overrides file (default: %(default)s)")
    parser.add_argument("--env", type=Path, default=REPO / ".env",
                        help="file with JELLYFIN_* settings (default: %(default)s)")
    parser.add_argument("--watch-interval", type=float, metavar="S",
                        default=_env_seconds("WATCH_INTERVAL_S", 30.0),
                        help="poll cadence (env WATCH_INTERVAL_S, default: %(default)s)")
    parser.add_argument("--quiet-period", type=float, metavar="S",
                        default=_env_seconds("QUIET_PERIOD_S", 60.0),
                        help="stability required before firing (env QUIET_PERIOD_S, default: %(default)s)")
    parser.add_argument("--retry-cooldown", type=float, metavar="S",
                        default=_env_seconds("RETRY_COOLDOWN_S", 900.0),
                        help="earliest refire of a failed job (env RETRY_COOLDOWN_S, default: %(default)s)")
    parser.add_argument("--migrate-mode", metavar="|".join(MODES),
                        default=os.environ.get("MIGRATE_MODE", "auto"),
                        help="run migrate live, as a dry run, or never (env MIGRATE_MODE, default: %(default)s)")
    parser.add_argument("--import-mode", metavar="|".join(MODES),
                        default=os.environ.get("IMPORT_MODE", "auto"),
                        help="run import live, as a dry run, or never (env IMPORT_MODE, default: %(default)s)")
    parser.add_argument("--once", action="store_true",
                        help="run the startup jobs and a single due-check, then exit")
    return parser


@dataclass(frozen=True)
class Config:
    deemix: Path
    lidarr: Path
    union: Path
    overrides: Path
    effective_env: Path
    interval: float
    quiet: float
    cooldown: float
    migrate_mode: str
    import_mode: str
    once: bool


Job = tuple[str, list[str], str]  # name, argv, trigger-set hash


class Watcher:
    def __init__(self, cfg: Config, runner: Runner, clock: Clock,
                 jellyfin: JellyfinClient | None) -> None:
        self.cfg = cfg
        self.runner = runner
        self.clock = clock
        self._jellyfin = jellyfin
        self._jellyfin_unusable = False
        self._holding_logged = False
        self.state_path = cfg.deemix / STATE_DIR / STATE_FILE
        self.attempted = _load_state(self.state_path)

    def run(self) -> int:
        fp0 = self._fingerprint()
        if fp0 is None:
            self._log("warning: a source tree is unreadable — skipping the startup run")
        else:
            startup: list[Job] = []
            if self.cfg.migrate_mode != "off":
                startup.append(("migrate", self._argv("migrate"), self._trigger("migrate", fp0)))
            startup.append(("union", self._union_argv(), self._trigger("union", fp0)))
            self._execute(startup)

        prev = self._fingerprint()
        unstable_until = 0.0
        while True:
            fp = self._fingerprint()
            if fp is None:
                self._log("warning: a source tree is unreadable — skipping this poll")
            else:
                if fp != prev:
                    prev = fp
                    unstable_until = self.clock.monotonic() + self.cfg.quiet
                if self.clock.monotonic() >= unstable_until:
                    self._fire_due(prev)
            if self.cfg.once:
                return 0
            self.clock.sleep(self.cfg.interval)

    def _fingerprint(self) -> Fingerprint | None:
        return fingerprint(self.cfg.deemix, self.cfg.lidarr, self.cfg.overrides)

    def _trigger(self, job: str, fp: Fingerprint) -> str:
        return _digest(_TRIGGER[job](fp))

    def _migrate_settled(self, fp: Fingerprint) -> bool:
        """Union mirrors the Deemix tree verbatim and import scans it, so while migrate's last
        attempt on the current trigger set is in cooldown the later jobs must hold — running
        them would link and scan a tree that still holds loose tracks and dupes."""
        if self.cfg.migrate_mode == "off":
            return True
        attempted = self.attempted.get("migrate")
        if attempted is None or attempted.hash != self._trigger("migrate", fp):
            return True  # no attempt yet, or a new set migrate will run on first in this batch
        return attempted.retry_after is None

    def _fire_due(self, fp: Fingerprint) -> None:
        jobs: list[Job] = []
        if self.cfg.migrate_mode != "off":
            trigger = self._trigger("migrate", fp)
            if self._due("migrate", trigger):
                jobs.append(("migrate", self._argv("migrate"), trigger))
        if self._migrate_settled(fp):
            if self._due("union", trigger := self._trigger("union", fp)):
                jobs.append(("union", self._union_argv(), trigger))
            if self.cfg.import_mode != "off" and fp.playlists \
                    and self._due("import", trigger := self._trigger("import", fp)):
                jobs.append(("import", self._argv("import"), trigger))
            self._holding_logged = False
        else:
            held = self._due("union", self._trigger("union", fp)) \
                or self.cfg.import_mode != "off" and fp.playlists \
                and self._due("import", self._trigger("import", fp))
            if held and not self._holding_logged:
                self._log("holding union/import until migrate's cooldown or a new trigger set")
                self._holding_logged = True
        if jobs:
            self._execute(jobs)

    def _due(self, job: str, trigger: str) -> bool:
        attempted = self.attempted.get(job)
        if attempted is None or attempted.hash != trigger:
            return True
        return attempted.retry_after is not None and self.clock.time() >= attempted.retry_after

    def _execute(self, jobs: list[Job]) -> None:
        for name, argv, trigger in jobs:
            self._log(f"running: {' '.join(argv)}")
            result = self.runner(argv)
            sys.stdout.write(result.output)
            sys.stdout.flush()
            self._record(name, trigger, result.code)
            if result.code != 0:
                self._log(f"{name} failed (exit {result.code}); report paths are in the output above")
                break
            if name == "union" and _union_made_links(result.output):
                self._nudge()
        _save_state(self.state_path, self.attempted)

    def _record(self, job: str, trigger: str, code: int) -> None:
        now = self.clock.time()
        # Exit 2 suppresses a job until its trigger set changes — except migrate, whose
        # refusal while Jellyfin is scanning is a normal transient retried on the cooldown.
        retry_after = now + self.cfg.cooldown if code != 0 and not (code == 2 and job != "migrate") else None
        self.attempted[job] = Attempt(trigger, now, retry_after)

    def _argv(self, job: str) -> list[str]:
        argv = [sys.executable, "-m", "reorganize_playlists",
                "--root", str(self.cfg.deemix), "--env", str(self.cfg.effective_env)]
        argv.append(job)
        if (job == "migrate" and self.cfg.migrate_mode == "dry") \
                or (job == "import" and self.cfg.import_mode == "dry"):
            argv.append("--dry-run")
        return argv

    def _union_argv(self) -> list[str]:
        return [sys.executable, "-m", "union_library",
                "--union", str(self.cfg.union), "--deemix", str(self.cfg.deemix),
                "--lidarr", str(self.cfg.lidarr), "--overrides", str(self.cfg.overrides)]

    def _nudge(self) -> None:
        if self._jellyfin is None and not self._jellyfin_unusable:
            settings = load_settings(self.cfg.effective_env)
            if not settings.api_key:
                self._log("JELLYFIN_API_KEY is not set; library refresh nudges disabled")
                self._jellyfin_unusable = True
            else:
                self._jellyfin = HttpJellyfinClient(settings)
        if self._jellyfin is None:
            return
        try:
            self._jellyfin.start_library_scan()
            self._log("asked Jellyfin to refresh the library")
        except Exception as exc:
            self._log(f"warning: Jellyfin refresh failed: {exc}")

    @staticmethod
    def _log(message: str) -> None:
        print(f"[library-watcher] {message}", flush=True)


def main(argv: list[str] | None = None, *, runner: Runner | None = None,
         clock: Clock | None = None, jellyfin: JellyfinClient | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.migrate_mode not in MODES or args.import_mode not in MODES:
        print(f"error: modes must be one of {'|'.join(MODES)} "
              f"(migrate={args.migrate_mode!r}, import={args.import_mode!r})", file=sys.stderr)
        return 2
    for name, path in (("deemix", args.deemix), ("lidarr", args.lidarr)):
        if not path.is_dir():
            print(f"error: {name} root {path} does not exist", file=sys.stderr)
            return 2
    effective_env = _materialise_env(args.env)
    cfg = Config(deemix=Path(args.deemix), lidarr=Path(args.lidarr), union=Path(args.union),
                 overrides=Path(args.overrides), effective_env=effective_env,
                 interval=args.watch_interval,
                 quiet=args.quiet_period, cooldown=args.retry_cooldown,
                 migrate_mode=args.migrate_mode, import_mode=args.import_mode, once=args.once)
    watcher = Watcher(cfg, runner or _subprocess_run, clock or _RealClock(), jellyfin)
    try:
        return watcher.run()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
