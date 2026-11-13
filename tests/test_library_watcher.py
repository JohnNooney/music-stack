from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable

from library_watcher.cli import RunResult, main
from tests.support import FakeJellyfin


class FakeClock:
    """Deterministic wall+monotonic time; scripted hooks run inside each sleep, then it stops the loop."""

    def __init__(self) -> None:
        self.wall = 1_800_000_000.0
        self.mono = 0.0
        self.hooks: list[Callable[[], object]] = []

    def time(self) -> float:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def sleep(self, seconds: float) -> None:
        self.wall += seconds
        self.mono += seconds
        if self.hooks:
            self.hooks.pop(0)()
        else:
            raise KeyboardInterrupt


def job_key(argv: list[str]) -> str:
    if "union_library" in argv:
        return "union"
    if "migrate" in argv:
        return "migrate"
    return "import"


class FakeRunner:
    """Records subprocess argv and replays scripted RunResults per job."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.results: dict[str, list[RunResult]] = {}

    def __call__(self, argv: list[str]) -> RunResult:
        self.calls.append(list(argv))
        queue = self.results.get(job_key(argv))
        if queue:
            return queue.pop(0)
        return RunResult(0, f"{job_key(argv)} report\nReport: /runs/x/report.txt\n")


def union_ops_report() -> str:
    return ("union_library [LIVE] /u\n=====================\n\n"
            "Linked (new) (1)\n----------------\n  A - B -> ../Deemix/A - B\n\n"
            "Report: /u/.union/runs/r1/report.txt\n")


def flag_value(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


class WatcherTestCase(unittest.TestCase):
    """Real temp Deemix/ + Lidarr/media/music/ + Jellyfin/ trees driven through main(argv)."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.deemix = base / "Deemix"
        self.deemix.mkdir()
        self.lidarr = base / "Lidarr" / "media" / "music"
        self.lidarr.mkdir(parents=True)
        self.union = base / "Jellyfin"
        self.union.mkdir()
        self.overrides = base / "union_library_overrides"
        self.env = base / ".env"
        self.env.write_text("JELLYFIN_URL=http://localhost:8096\n"
                            "JELLYFIN_API_KEY=test-key\nJELLYFIN_USER=john\n")
        self.runner = FakeRunner()
        self.clock = FakeClock()
        self.jellyfin = FakeJellyfin(self.union)
        self.output = ""

    def run_watcher(self, *args: str, expect: int = 0) -> str:
        argv = ["--deemix", str(self.deemix), "--lidarr", str(self.lidarr),
                "--union", str(self.union), "--overrides", str(self.overrides),
                "--env", str(self.env), *args]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv, runner=self.runner, clock=self.clock, jellyfin=self.jellyfin)
        self.output = out.getvalue() + err.getvalue()
        self.assertEqual(code, expect, self.output)
        return self.output

    def set_env(self, key: str, value: str) -> None:
        self.addCleanup(self._restore_env, key, os.environ.get(key))
        os.environ[key] = value

    @staticmethod
    def _restore_env(key: str, old: str | None) -> None:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old

    def commands(self) -> list[str]:
        return [job_key(c) for c in self.runner.calls]

    def noop(self) -> None:
        pass

    def assert_calls(self, count: int) -> Callable[[], None]:
        return lambda: self.assertEqual(len(self.runner.calls), count, self.runner.calls)


class StartupTest(WatcherTestCase):
    def test_startup_runs_migrate_then_union(self) -> None:
        self.run_watcher("--once")

        self.assertEqual(self.commands(), ["migrate", "union"])

    def test_subprocess_argv_carries_the_configured_paths(self) -> None:
        self.run_watcher("--once")

        migrate, union = self.runner.calls
        self.assertEqual(migrate[1:3], ["-m", "reorganize_playlists"])
        self.assertEqual(flag_value(migrate, "--root"), str(self.deemix))
        self.assertEqual(migrate[-1], "migrate")
        self.assertEqual(union[1:3], ["-m", "union_library"])
        self.assertEqual(flag_value(union, "--union"), str(self.union))
        self.assertEqual(flag_value(union, "--deemix"), str(self.deemix))
        self.assertEqual(flag_value(union, "--lidarr"), str(self.lidarr))
        self.assertEqual(flag_value(union, "--overrides"), str(self.overrides))

    def test_env_file_is_materialised_and_passed_to_children(self) -> None:
        self.set_env("JELLYFIN_URL", "http://jellyfin:8096")

        self.run_watcher("--once")

        effective = Path(tempfile.gettempdir()) / "library_watcher-jellyfin.env"
        self.assertEqual(flag_value(self.runner.calls[0], "--env"), str(effective))
        self.assertIn("JELLYFIN_URL=http://jellyfin:8096", effective.read_text())
        self.assertIn("JELLYFIN_API_KEY=test-key", effective.read_text())
        self.assertEqual(effective.stat().st_mode & 0o777, 0o600)


class TriggerTest(WatcherTestCase):
    def test_no_change_runs_nothing_after_startup(self) -> None:
        self.clock.hooks = [self.noop] * 3

        self.run_watcher("--watch-interval", "30", "--quiet-period", "60")

        self.assertEqual(self.commands(), ["migrate", "union"])

    def test_deemix_change_runs_migrate_then_union(self) -> None:
        self.clock.hooks = [lambda: (self.deemix / "A - B").mkdir(), self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30")

        self.assertEqual(self.commands(), ["migrate", "union", "migrate", "union"])

    def test_lidarr_only_change_runs_union_alone(self) -> None:
        self.clock.hooks = [lambda: (self.lidarr / "X" / "Y (2000)").mkdir(parents=True),
                            self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30")

        self.assertEqual(self.commands(), ["migrate", "union", "union"])

    def test_change_does_not_fire_before_the_quiet_period(self) -> None:
        self.clock.hooks = [lambda: (self.deemix / "A - B").mkdir(),
                            self.assert_calls(2), self.assert_calls(2), self.assert_calls(2),
                            self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "120")

        self.assertEqual(self.commands(), ["migrate", "union", "migrate", "union"])

    def test_a_further_change_restarts_the_quiet_period(self) -> None:
        self.clock.hooks = [lambda: (self.deemix / "A - B").mkdir(),
                            lambda: (self.deemix / "C - D").mkdir(),
                            self.assert_calls(2), self.assert_calls(2), self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "60")

        self.assertEqual(self.commands(), ["migrate", "union", "migrate", "union"])

    def test_pending_playlist_file_appends_import_last(self) -> None:
        self.clock.hooks = [lambda: (self.deemix / "Mix.m3u8").write_text("x\n"),
                            self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30")

        self.assertEqual(self.commands(), ["migrate", "union", "migrate", "union", "import"])
        argv = self.runner.calls[-1]
        self.assertEqual(argv[1:3], ["-m", "reorganize_playlists"])
        self.assertEqual(argv[-1], "import")

    def test_overrides_change_triggers_union_alone(self) -> None:
        self.clock.hooks = [lambda: self.overrides.write_text("match A - B = X/Y (2000)\n"),
                            self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30")

        self.assertEqual(self.commands(), ["migrate", "union", "union"])

    def test_state_dir_writes_do_not_self_trigger(self) -> None:
        self.clock.hooks = [self.noop] * 3

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30")

        self.assertTrue((self.deemix / ".reorganize" / "watcher-state.json").is_file())
        self.assertEqual(self.commands(), ["migrate", "union"])

    def test_tool_churn_dotfiles_do_not_self_trigger(self) -> None:
        # migrate/import rewrite .inventory.tsv and .gitignore at the library root on every run.
        self.clock.hooks = [lambda: (self.deemix / ".inventory.tsv").write_text("x\n"),
                            self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30")

        self.assertEqual(self.commands(), ["migrate", "union"])


class ModeTest(WatcherTestCase):
    def test_migrate_mode_dry_adds_dry_run(self) -> None:
        self.run_watcher("--once", "--migrate-mode", "dry")

        self.assertEqual(self.commands(), ["migrate", "union"])
        self.assertIn("--dry-run", self.runner.calls[0])

    def test_migrate_mode_off_never_runs_migrate(self) -> None:
        self.clock.hooks = [lambda: (self.deemix / "A - B").mkdir(), self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30", "--migrate-mode", "off")

        self.assertEqual(self.commands(), ["union", "union"])

    def test_import_mode_dry_adds_dry_run(self) -> None:
        self.clock.hooks = [lambda: (self.deemix / "Mix.m3u8").write_text("x\n"),
                            self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30", "--import-mode", "dry")

        self.assertEqual(self.commands()[-1], "import")
        self.assertIn("--dry-run", self.runner.calls[-1])

    def test_import_mode_off_never_runs_import(self) -> None:
        self.clock.hooks = [lambda: (self.deemix / "Mix.m3u8").write_text("x\n"),
                            self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30", "--import-mode", "off")

        self.assertEqual(self.commands(), ["migrate", "union", "migrate", "union"])

    def test_modes_come_from_the_environment(self) -> None:
        self.set_env("MIGRATE_MODE", "off")
        self.set_env("IMPORT_MODE", "off")

        self.run_watcher("--once")

        self.assertEqual(self.commands(), ["union"])

    def test_an_invalid_mode_is_misuse(self) -> None:
        self.run_watcher("--once", "--migrate-mode", "bogus", expect=2)


class RetryTest(WatcherTestCase):
    def test_failed_job_is_suppressed_until_the_cooldown(self) -> None:
        self.runner.results["migrate"] = [RunResult(0, "ok\n"), RunResult(1, "boom\nReport: /r/1\n"),
                                          RunResult(1, "boom\nReport: /r/2\n")]
        self.clock.hooks = [lambda: (self.deemix / "A - B").mkdir(), self.noop, self.noop,
                            self.assert_calls(3), self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30",
                         "--retry-cooldown", "100")

        self.assertEqual(self.commands(), ["migrate", "union", "migrate", "migrate"])

    def test_failed_migrate_skips_the_rest_of_the_batch(self) -> None:
        self.runner.results["migrate"] = [RunResult(0, "ok\n"), RunResult(1, "boom\n")]
        self.clock.hooks = [lambda: (self.deemix / "A - B").mkdir(), self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30",
                         "--retry-cooldown", "10000")

        # startup [migrate, union]; then the failing batch [migrate]; union stays held
        self.assertEqual(self.commands(), ["migrate", "union", "migrate"])

    def test_held_jobs_fire_once_migrate_recovers(self) -> None:
        self.runner.results["migrate"] = [RunResult(0, "ok\n"), RunResult(1, "boom\n"),
                                          RunResult(0, "ok\n")]
        self.clock.hooks = [lambda: (self.deemix / "A - B").mkdir(), self.noop,
                            lambda: (self.deemix / "C - D").mkdir(), self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30",
                         "--retry-cooldown", "10000")

        # new trigger set refires migrate early; it succeeds, so union follows in the same batch
        self.assertEqual(self.commands(), ["migrate", "union", "migrate", "migrate", "union"])

    def test_changed_trigger_set_refires_before_the_cooldown(self) -> None:
        self.runner.results["union"] = [RunResult(0, "ok\n"), RunResult(1, "boom\n"),
                                        RunResult(0, "ok\n")]
        self.clock.hooks = [lambda: (self.lidarr / "X" / "Y (2000)").mkdir(parents=True), self.noop,
                            lambda: (self.lidarr / "X" / "Z (2001)").mkdir(parents=True),
                            self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30",
                         "--retry-cooldown", "10000")

        # the failed union refires early because its trigger set changed
        self.assertEqual(self.commands(), ["migrate", "union", "union", "union"])

    def test_union_exit_2_suppresses_until_the_set_changes(self) -> None:
        self.runner.results["union"] = [RunResult(0, "ok\n"),
                                        RunResult(2, "error: bad overrides\n")]
        self.clock.hooks = [lambda: self.overrides.write_text("nonsense\n"), self.noop,
                            self.noop, self.noop, self.noop]

        self.run_watcher("--watch-interval", "30", "--quiet-period", "30", "--retry-cooldown", "60")

        # the cooldown passes without a refire because union's exit 2 suppresses until change
        self.assertEqual(self.commands(), ["migrate", "union", "union"])

    def test_failure_lines_and_report_paths_reach_the_log(self) -> None:
        self.runner.results["union"] = [RunResult(0, "ok\n"), RunResult(
            1, "union_library [LIVE]\nFailed actions (1)\n  'X': broke\n\nReport: /u/.union/runs/r/report.txt\n")]
        self.clock.hooks = [lambda: (self.lidarr / "X" / "Y (2000)").mkdir(parents=True),
                            self.noop, self.noop]

        out = self.run_watcher("--watch-interval", "30", "--quiet-period", "30")

        self.assertIn("'X': broke", out)
        self.assertIn("Report: /u/.union/runs/r/report.txt", out)


class NudgeTest(WatcherTestCase):
    def test_union_run_with_link_ops_nudges_jellyfin(self) -> None:
        self.runner.results["union"] = [RunResult(0, union_ops_report())]

        self.run_watcher("--once")

        self.assertEqual(self.jellyfin.scans_started, 1)

    def test_quiet_union_run_does_not_nudge(self) -> None:
        self.run_watcher("--once")

        self.assertEqual(self.jellyfin.scans_started, 0)


class StateTest(WatcherTestCase):
    def test_restart_does_not_reimport_a_processed_playlist(self) -> None:
        (self.deemix / "Mix.m3u8").write_text("x\n")

        self.run_watcher("--once")
        first = self.commands()

        self.run_watcher("--once")

        self.assertEqual(first, ["migrate", "union", "import"])
        self.assertEqual(self.commands()[len(first):], ["migrate", "union"])

    def test_state_file_records_attempted_jobs(self) -> None:
        self.run_watcher("--once")

        state = json.loads((self.deemix / ".reorganize" / "watcher-state.json").read_text())
        self.assertIn("migrate", state["jobs"])
        self.assertIn("union", state["jobs"])
        self.assertIn("hash", state["jobs"]["union"])


if __name__ == "__main__":
    unittest.main()
