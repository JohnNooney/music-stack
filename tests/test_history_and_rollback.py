from __future__ import annotations

import json
import unittest

from tests.support import ToolTestCase

HISTORY = (".git/", ".gitignore", ".inventory.tsv", ".playlists/jellyfin/")


class SmallLibrary(ToolTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.lib.flac("Daft Punk - Discovery/01 - One More Time.flac", title="One More Time", artist="Daft Punk",
                      album="Discovery", track=1, isrc="DP1", size=321)
        self.lib.flac("Playlists/Bussin/Daft Punk - One More Time.flac", title="One More Time",
                      artist="Daft Punk", album="Discovery", track=1, isrc="DP1")
        self.lib.flac("Playlists/Bussin/Nas - Halftime.flac", title="Halftime", artist="Nas", album="Illmatic",
                      track=5, isrc="NAS5")
        self.lib.write("Playlists/Bussin/cover.jpg", b"cover")
        self.lib.write("Playlists/Bussin/errors.txt", "1 | x | failed\n")
        self.lib.write("Bussin.m3u", "#EXTM3U\nPlaylists/Bussin/Nas - Halftime.flac\n"
                       "Playlists/Bussin/Daft Punk - One More Time.flac\n")
        self.deezer.add("NAS5", album="Illmatic", artist="Nas", track_total=10)

    def history_free_snapshot(self) -> dict[str, bytes]:
        return {k: v for k, v in self.lib.snapshot().items() if not k.startswith(HISTORY)}


class HistoryTest(SmallLibrary):
    def test_inventory_lists_every_audio_file(self) -> None:
        self.run_tool("migrate")

        rows = self.lib.path(".inventory.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[0], "path\tisrc\tsize\tartist\talbum\ttitle")
        self.assertIn("Daft Punk - Discovery/01 - One More Time.flac\tDP1\t"
                      f"{self.lib.path('Daft Punk - Discovery/01 - One More Time.flac').stat().st_size}\t"
                      "Daft Punk\tDiscovery\tOne More Time", rows)
        self.assertTrue(any(r.startswith("Nas - Illmatic/05 - Halftime.flac\tNAS5\t") for r in rows))
        self.assertEqual(len(rows), 3)

    def test_each_run_commits_only_allow_listed_text_files(self) -> None:
        self.run_tool("migrate")
        self.run_tool("migrate", "--phase", "playlists")

        tracked = set(self.git("ls-files").splitlines())
        self.assertEqual(tracked, {".gitignore", ".inventory.tsv", ".artifacts/Bussin/errors.txt",
                                   ".playlists/map.json", ".playlists/imports/Bussin.m3u8",
                                   ".playlists/jellyfin/Bussin.m3u8"})
        subjects = self.git("log", "--format=%s").splitlines()
        self.assertEqual(len(subjects), 2)
        self.assertTrue(subjects[1].startswith("migrate: 1 songs into album folders; 1 duplicate copies trashed"),
                        subjects)
        self.assertEqual(subjects[0], "migrate: created 1 Jellyfin playlists")
        self.assertEqual(self.git("remote").strip(), "")

    def test_exports_use_jellyfin_names_and_library_relative_paths(self) -> None:
        self.run_tool("migrate")
        self.run_tool("migrate", "--phase", "playlists")
        pid, playlist = self.jellyfin.by_name("Bussin")
        playlist.name = "Bussin: Remix"

        self.run_tool("export")

        self.assertFalse(self.lib.path(".playlists/jellyfin/Bussin.m3u8").exists())
        export = self.lib.path(".playlists/jellyfin/Bussin_ Remix.m3u8").read_text(encoding="utf-8")
        self.assertEqual([line for line in export.splitlines() if not line.startswith("#")],
                         ["Nas - Illmatic/05 - Halftime.flac", "Daft Punk - Discovery/01 - One More Time.flac"])
        self.assertIn("#EXTINF:-1,Nas - Halftime", export)
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(), "export: playlists and inventory")

    def test_import_commit_message_summarises_changes(self) -> None:
        self.run_tool("migrate")
        self.run_tool("migrate", "--phase", "playlists")
        self.lib.flac("Mobb Deep - The Infamous/03 - Survival.flac", title="Survival", artist="Mobb Deep",
                      album="The Infamous", track=3, isrc="MD3")
        self.lib.write("Bussin.m3u8", "Nas - Illmatic/05 - Halftime.flac\nMobb Deep - The Infamous/03 - Survival.flac\n")

        self.run_tool("import")

        self.assertEqual(self.git("log", "-1", "--format=%s").strip(),
                         "import: Bussin +1 songs; 1 dropped on Deezer")


class RollbackTest(SmallLibrary):
    def test_rollback_restores_the_file_phase_exactly(self) -> None:
        before = self.history_free_snapshot()
        self.run_tool("migrate")
        self.assertNotEqual(self.history_free_snapshot(), before)

        self.run_tool("rollback", str(self.latest_manifest()))

        self.assertEqual(self.history_free_snapshot(), before)
        self.assertTrue(self.lib.path("Playlists/Bussin/cover.jpg").is_file())

    def test_rollback_of_playlist_phase_deletes_created_playlists_and_restores_files(self) -> None:
        self.run_tool("migrate")
        after_files = self.history_free_snapshot()
        self.run_tool("migrate", "--phase", "playlists")

        self.run_tool("rollback", str(self.latest_manifest()))

        self.assertEqual(self.jellyfin.playlists, {})
        self.assertEqual(self.history_free_snapshot(), after_files)

    def test_rollback_of_import_removes_appended_songs_only(self) -> None:
        self.run_tool("migrate")
        self.run_tool("migrate", "--phase", "playlists")
        pid, _ = self.jellyfin.by_name("Bussin")
        before_import = self.jellyfin.playlist_paths(pid)
        self.lib.flac("Mobb Deep - The Infamous/03 - Survival.flac", title="Survival", artist="Mobb Deep",
                      album="The Infamous", track=3, isrc="MD3")
        self.lib.write("Bussin.m3u8", "Nas - Illmatic/05 - Halftime.flac\nMobb Deep - The Infamous/03 - Survival.flac\n")
        mapping = self.lib.path(".playlists/map.json").read_text()
        self.run_tool("import")
        self.assertEqual(len(self.jellyfin.playlist_paths(pid)), 3)

        self.run_tool("rollback", str(self.latest_manifest()))

        self.assertEqual(self.jellyfin.playlist_paths(pid), before_import)
        self.assertTrue(self.lib.path("Bussin.m3u8").is_file())
        self.assertEqual(json.loads(self.lib.path(".playlists/map.json").read_text()), json.loads(mapping))


if __name__ == "__main__":
    unittest.main()
