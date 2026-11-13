from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from union_library.cli import main


class UnionTestCase(unittest.TestCase):
    """Real temp `Deemix/` + `Lidarr/media/music/` source trees and an empty union dir."""

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
        self.output = ""

    def deemix_album(self, name: str) -> Path:
        path = self.deemix / name
        path.mkdir()
        (path / "01 - Song.flac").write_bytes(b"fake")
        return path

    def lidarr_album(self, artist: str, album: str) -> Path:
        path = self.lidarr / artist / album
        path.mkdir(parents=True, exist_ok=True)
        (path / "01 - Song.flac").write_bytes(b"fake")
        return path

    def run_tool(self, *args: str, expect: int = 0) -> str:
        argv = ["--union", str(self.union), "--deemix", str(self.deemix),
                "--lidarr", str(self.lidarr), "--overrides", str(self.overrides), *args]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        self.output = out.getvalue() + err.getvalue()
        self.assertEqual(code, expect, self.output)
        return self.output

    def entries(self) -> dict[str, str]:
        """Union entry name -> readlink target, for every symlink in the union root."""
        return {e.name: os.readlink(self.union / e.name) for e in os.scandir(self.union)
                if e.is_symlink()}


class BasicLinkingTest(UnionTestCase):
    def test_deemix_album_is_linked_verbatim(self) -> None:
        self.deemix_album("Herbie Hancock - Takin' Off")

        out = self.run_tool()

        self.assertEqual(self.entries(), {"Herbie Hancock - Takin' Off": "../Deemix/Herbie Hancock - Takin' Off"})
        self.assertIn("Herbie Hancock - Takin' Off -> ../Deemix/", out)

    def test_lidarr_album_gets_constructed_entry_name(self) -> None:
        self.lidarr_album("Herbie Hancock", "Thrust (1974)")

        self.run_tool()

        self.assertEqual(self.entries(),
                         {"Herbie Hancock - Thrust (1974)": "../Lidarr/media/music/Herbie Hancock/Thrust (1974)"})

    def test_links_resolve_to_the_real_album_dirs(self) -> None:
        deemix_dir = self.deemix_album("A - B")
        lidarr_dir = self.lidarr_album("C", "D (2001)")

        self.run_tool()

        self.assertEqual((self.union / "A - B").resolve(), deemix_dir.resolve())
        self.assertEqual((self.union / "C - D (2001)").resolve(), lidarr_dir.resolve())

    def test_dry_run_creates_no_links_and_still_reports(self) -> None:
        self.deemix_album("A - B")
        self.lidarr_album("C", "D (2001)")

        out = self.run_tool("--dry-run")

        self.assertEqual(self.entries(), {})
        self.assertIn("DRY RUN", out)
        self.assertIn("A - B", out)

    def test_second_run_is_an_empty_plan(self) -> None:
        self.deemix_album("A - B")
        self.run_tool()

        out = self.run_tool()

        self.assertNotIn("Linked (new)", out)
        self.assertEqual(self.entries(), {"A - B": "../Deemix/A - B"})

    def test_first_live_run_creates_the_union_root_and_links(self) -> None:
        self.deemix_album("A - B")
        self.union.rmdir()

        self.run_tool()

        self.assertEqual(self.entries(), {"A - B": "../Deemix/A - B"})


class MatchingTest(UnionTestCase):
    def test_confident_match_keeps_deemix_name_but_targets_lidarr(self) -> None:
        self.deemix_album("Herbie Hancock - Head Hunters")
        self.lidarr_album("Herbie Hancock", "Head Hunters (1973)")

        self.run_tool()

        self.assertEqual(self.entries(),
                         {"Herbie Hancock - Head Hunters": "../Lidarr/media/music/Herbie Hancock/Head Hunters (1973)"})

    def test_match_normalises_case_punctuation_and_year(self) -> None:
        self.deemix_album("Willie Colón - Tiempo pa' Matar")
        self.lidarr_album("Willie Colón", "Tiempo pa' matar (1984)")

        self.run_tool()

        self.assertEqual(self.entries(),
                         {"Willie Colón - Tiempo pa' Matar":
                          "../Lidarr/media/music/Willie Colón/Tiempo pa' matar (1984)"})

    def test_remaster_named_albums_do_not_match(self) -> None:
        self.deemix_album("Metallica - Kill 'Em All (Remastered)")
        self.lidarr_album("Metallica", "Kill 'Em All (1983)")

        self.run_tool()

        self.assertEqual(self.entries(), {
            "Metallica - Kill 'Em All (Remastered)": "../Deemix/Metallica - Kill 'Em All (Remastered)",
            "Metallica - Kill 'Em All (1983)": "../Lidarr/media/music/Metallica/Kill 'Em All (1983)",
        })

    def test_existing_deemix_link_is_retargeted_to_lidarr(self) -> None:
        self.deemix_album("Herbie Hancock - Head Hunters")
        self.lidarr_album("Herbie Hancock", "Head Hunters (1973)")
        os.symlink("../Deemix/Herbie Hancock - Head Hunters", self.union / "Herbie Hancock - Head Hunters")

        out = self.run_tool()

        self.assertEqual(os.readlink(self.union / "Herbie Hancock - Head Hunters"),
                         "../Lidarr/media/music/Herbie Hancock/Head Hunters (1973)")
        self.assertIn("Relinked (Deemix → Lidarr)", out)

    def test_multiple_lidarr_candidates_are_ambiguous_and_deemix_is_kept(self) -> None:
        self.deemix_album("Willie Colón - Asalto navideño")
        self.lidarr_album("Willie Colón", "Asalto navideño (1972)")
        self.lidarr_album("Willie Colón", "Asalto navideño (1992)")

        out = self.run_tool()

        self.assertEqual(self.entries(),
                         {"Willie Colón - Asalto navideño": "../Deemix/Willie Colón - Asalto navideño"})
        self.assertIn("Ambiguous matches", out)
        self.assertIn("Asalto navideño (1972)", out)
        self.assertIn("Asalto navideño (1992)", out)


class OverridesTest(UnionTestCase):
    def write_overrides(self, text: str) -> None:
        self.overrides.write_text(text, encoding="utf-8")

    def test_match_override_dedupes_a_name_the_normaliser_cannot_settle(self) -> None:
        self.deemix_album("Eek-A-Mouse - The Mouse And The Man")
        self.lidarr_album("Eek‐A‐Mouse", "The Mouse & The Man (1983)")
        self.write_overrides("match Eek-A-Mouse - The Mouse And The Man = "
                             "Eek‐A‐Mouse/The Mouse & The Man (1983)\n")

        out = self.run_tool()

        self.assertEqual(self.entries(), {"Eek-A-Mouse - The Mouse And The Man":
                                         "../Lidarr/media/music/Eek‐A‐Mouse/The Mouse & The Man (1983)"})
        self.assertIn("Overridden", out)

    def test_match_override_resolves_an_ambiguity_and_frees_the_other_candidate(self) -> None:
        self.deemix_album("Willie Colón - Asalto navideño")
        self.lidarr_album("Willie Colón", "Asalto navideño (1972)")
        self.lidarr_album("Willie Colón", "Asalto navideño (1992)")
        self.write_overrides("match Willie Colón - Asalto navideño = Willie Colón/Asalto navideño (1992)\n")

        self.run_tool()

        self.assertEqual(self.entries(), {
            "Willie Colón - Asalto navideño": "../Lidarr/media/music/Willie Colón/Asalto navideño (1992)",
            "Willie Colón - Asalto navideño (1972)": "../Lidarr/media/music/Willie Colón/Asalto navideño (1972)",
        })

    def test_prefer_deemix_override_matches_but_keeps_the_deemix_target(self) -> None:
        self.deemix_album("Herbie Hancock - Head Hunters")
        self.lidarr_album("Herbie Hancock", "Head Hunters (1973)")
        self.write_overrides("prefer-deemix Herbie Hancock - Head Hunters = "
                             "Herbie Hancock/Head Hunters (1973)\n")

        self.run_tool()

        self.assertEqual(self.entries(),
                         {"Herbie Hancock - Head Hunters": "../Deemix/Herbie Hancock - Head Hunters"})

    def test_keep_both_override_suppresses_the_dedupe_and_emits_both(self) -> None:
        self.deemix_album("Herbie Hancock - Head Hunters")
        self.lidarr_album("Herbie Hancock", "Head Hunters (1973)")
        self.write_overrides("keep-both Herbie Hancock - Head Hunters = "
                             "Herbie Hancock/Head Hunters (1973)\n")

        self.run_tool()

        self.assertEqual(self.entries(), {
            "Herbie Hancock - Head Hunters": "../Deemix/Herbie Hancock - Head Hunters",
            "Herbie Hancock - Head Hunters (1973)": "../Lidarr/media/music/Herbie Hancock/Head Hunters (1973)",
        })

    def test_override_for_a_missing_album_is_reported_unused(self) -> None:
        self.deemix_album("A - B")
        self.write_overrides("match A - B = C/Gone (2000)\nprefer-deemix Z - Q = C/Gone (2000)\n")

        out = self.run_tool()

        self.assertIn("unused", out)
        self.assertIn("no such Lidarr album", out)
        self.assertIn("no such Deemix album folder", out)
        self.assertEqual(self.entries(), {"A - B": "../Deemix/A - B"})

    def test_malformed_override_line_fails(self) -> None:
        self.write_overrides("match A - B\n")

        self.run_tool(expect=2)

    def test_comments_and_blank_lines_are_ignored(self) -> None:
        self.deemix_album("A - B")
        self.write_overrides("# resolved pairs\n\n   \n")

        self.run_tool(expect=0)


class LooseRootAndExcludesTest(UnionTestCase):
    def test_loose_root_items_are_mirrored_verbatim(self) -> None:
        self.deemix_album("A - B")
        (self.deemix / "Mix.m3u8").write_text("A - B/01 - Song.flac\n")
        (self.deemix / ".gitignore").write_text("*.log\n")
        (self.deemix / "notes.txt").write_text("hi\n")
        (self.deemix / "StrayDir").mkdir()

        out = self.run_tool()

        self.assertEqual(self.entries(), {
            "A - B": "../Deemix/A - B",
            "Mix.m3u8": "../Deemix/Mix.m3u8",
            ".gitignore": "../Deemix/.gitignore",
            "notes.txt": "../Deemix/notes.txt",
            "StrayDir": "../Deemix/StrayDir",
        })
        self.assertIn("Loose-root items mirrored", out)

    def test_internal_dirs_are_excluded_and_reported(self) -> None:
        for name in ("Config", "_duplicates_trash", ".git", ".reorganize"):
            (self.deemix / name).mkdir()

        out = self.run_tool()

        self.assertEqual(self.entries(), {})
        self.assertIn("Excluded", out)
        self.assertIn("Config", out)

    def test_exclude_flag_extends_the_list(self) -> None:
        (self.deemix / "Scratch").mkdir()

        self.run_tool("--exclude", "Scratch")

        self.assertEqual(self.entries(), {})

    def test_loose_entries_stay_correct_on_rerun(self) -> None:
        (self.deemix / "Mix.m3u8").write_text("x\n")
        self.run_tool()

        out = self.run_tool()

        self.assertNotIn("Loose-root items mirrored", out)
        self.assertEqual(self.entries(), {"Mix.m3u8": "../Deemix/Mix.m3u8"})


class UnionRootMaintenanceTest(UnionTestCase):
    def test_dangling_link_is_pruned_and_reported(self) -> None:
        self.deemix_album("A - B")
        self.run_tool()
        (self.deemix / "A - B").rename(self.deemix / "A - B Renamed")

        out = self.run_tool()

        self.assertEqual(self.entries(), {"A - B Renamed": "../Deemix/A - B Renamed"})
        self.assertIn("Pruned dangling links", out)
        self.assertIn("A - B", out)

    def test_foreign_entries_are_left_alone_and_reported(self) -> None:
        self.deemix_album("A - B")
        (self.union / "hand-made.txt").write_text("x")
        (self.union / "hand-dir").mkdir()
        other = self.deemix / ".."
        os.symlink(os.path.relpath(other.resolve(), self.union), self.union / "hand-link")

        out = self.run_tool()

        self.assertTrue((self.union / "hand-made.txt").is_file())
        self.assertTrue((self.union / "hand-dir").is_dir())
        self.assertIn("Foreign entries (untouched)", out)
        self.assertIn("hand-made.txt", out)
        self.assertIn("hand-dir", out)
        self.assertIn("hand-link", out)

    def test_constructed_name_colliding_with_an_existing_entry_is_skipped(self) -> None:
        self.lidarr_album("Herbie Hancock", "Thrust (1974)")
        (self.union / "Herbie Hancock - Thrust (1974)").mkdir()

        out = self.run_tool(expect=1)

        self.assertEqual(self.entries(), {})
        self.assertTrue((self.union / "Herbie Hancock - Thrust (1974)").is_dir())

    def test_foreign_symlink_with_a_wanted_name_is_never_overwritten(self) -> None:
        self.deemix_album("A - B")
        outside = self.deemix.parent / "elsewhere"
        outside.mkdir()
        os.symlink(os.path.relpath(outside, self.union), self.union / "A - B")

        out = self.run_tool(expect=1)

        self.assertEqual(os.readlink(self.union / "A - B"), os.path.relpath(outside, self.union))
        self.assertIn("foreign symlink", out)

    def test_dangling_dot_link_is_pruned(self) -> None:
        (self.deemix / ".gitignore").write_text("x\n")
        self.run_tool()
        (self.deemix / ".gitignore").unlink()

        out = self.run_tool()

        self.assertEqual(self.entries(), {})
        self.assertIn("Pruned dangling links", out)

    def test_non_disc_music_subfolder_is_reported(self) -> None:
        vinyl = self.lidarr_album("Metallica", "St. Anger (2003)")
        for sub in ("12 Vinyl 01", "12 Vinyl 02"):
            (vinyl / sub).mkdir()
            (vinyl / sub / "01 - Song.flac").write_bytes(b"x")
        (self.deemix / "A - B" / "Bonus").mkdir(parents=True)
        (self.deemix / "A - B" / "Bonus" / "01 - Extra.flac").write_bytes(b"x")
        (self.deemix / "A - B" / "CD2").mkdir()
        (self.deemix / "A - B" / "CD2" / "01 - Extra.flac").write_bytes(b"x")
        (self.deemix / "A - B" / "Scans").mkdir()
        (self.deemix / "A - B" / "Scans" / "cover.jpg").write_bytes(b"x")

        out = self.run_tool()

        section = out.split("Non-disc subfolders")[1].split("\n\n")[0]
        self.assertIn("12 Vinyl 01", section)
        self.assertIn("12 Vinyl 02", section)
        self.assertIn("Deemix/A - B", section)
        self.assertNotIn("CD2", section)
        self.assertNotIn("Scans", section)

    def test_union_root_holds_only_symlinks_and_state(self) -> None:
        self.deemix_album("A - B")
        self.lidarr_album("C", "D (2001)")
        (self.deemix / "Mix.m3u8").write_text("x\n")

        self.run_tool()

        non_links = [e.name for e in os.scandir(self.union)
                     if not e.is_symlink() and not e.name.startswith(".")]
        self.assertEqual(non_links, [])

    def test_source_trees_are_never_modified(self) -> None:
        self.deemix_album("A - B")
        self.lidarr_album("C", "D (2001)")
        (self.deemix / "Mix.m3u8").write_text("x\n")
        before = {p.relative_to(self.deemix).as_posix() for p in self.deemix.rglob("*")}, \
            {p.relative_to(self.lidarr).as_posix() for p in self.lidarr.rglob("*")}

        self.run_tool()

        after = {p.relative_to(self.deemix).as_posix() for p in self.deemix.rglob("*")}, \
            {p.relative_to(self.lidarr).as_posix() for p in self.lidarr.rglob("*")}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
