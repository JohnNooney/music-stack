from __future__ import annotations

import json
import unittest

from tests.support import ToolTestCase


class MigratePlaylistPhaseTest(ToolTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.lib.flac("Daft Punk - Discovery/01 - One More Time.flac", title="One More Time", artist="Daft Punk",
                      album="Discovery", track=1, isrc="DP1")
        self.lib.flac("Playlists/Bussin/Daft Punk - One More Time.flac", title="One More Time",
                      artist="Daft Punk", album="Discovery", track=1, isrc="DP1")
        self.lib.flac("Playlists/Bussin/Nas - Halftime.flac", title="Halftime", artist="Nas", album="Illmatic",
                      track=5, isrc="NAS5")
        self.lib.flac("Playlists/Waves/Nas - Halftime.flac", title="Halftime", artist="Nas", album="Illmatic",
                      track=5, isrc="NAS5")
        self.lib.write("Playlists/Bussin/cover.jpg", b"bussin cover")
        self.lib.write("Bussin.m3u", "#EXTM3U\nPlaylists/Bussin/Nas - Halftime.flac\n"
                       "Playlists/Bussin/Daft Punk - One More Time.flac\n")
        self.lib.write("Waves.m3u", "#EXTM3U\nPlaylists/Waves/Nas - Halftime.flac\n")
        self.deezer.add("NAS5", album="Illmatic", artist="Nas", track_total=10)
        self.run_tool("migrate")
        self.jellyfin.mutations.clear()

    def test_creates_owned_playlists_in_order_with_covers(self) -> None:
        self.run_tool("migrate", "--phase", "playlists")

        pid, bussin = self.jellyfin.by_name("Bussin")
        self.assertEqual(bussin.owner, "user-john")
        self.assertEqual(self.jellyfin.playlist_paths(pid), ["Nas - Illmatic/05 - Halftime.flac",
                                                             "Daft Punk - Discovery/01 - One More Time.flac"])
        self.assertEqual(bussin.image, b"bussin cover")
        wid, _ = self.jellyfin.by_name("Waves")
        self.assertEqual(self.jellyfin.playlist_paths(wid), ["Nas - Illmatic/05 - Halftime.flac"])

    def test_writes_mapping_and_import_references_and_root_files_leave_the_library(self) -> None:
        self.run_tool("migrate", "--phase", "playlists")

        mapping = json.loads(self.lib.path(".playlists/map.json").read_text())
        self.assertEqual(mapping, {"Bussin": self.jellyfin.by_name("Bussin")[0],
                                   "Waves": self.jellyfin.by_name("Waves")[0]})
        reference = self.lib.path(".playlists/imports/Bussin.m3u8").read_text(encoding="utf-8")
        self.assertEqual([line for line in reference.splitlines() if not line.startswith("#")],
                         ["Nas - Illmatic/05 - Halftime.flac", "Daft Punk - Discovery/01 - One More Time.flac"])
        self.assertFalse(self.lib.path("Bussin.m3u").exists())
        self.assertFalse(self.lib.path("Waves.m3u").exists())

    def test_waits_for_the_library_scan_before_creating_playlists(self) -> None:
        self.run_tool("migrate", "--phase", "playlists")

        self.assertEqual(self.jellyfin.scans_started, 1)
        self.assertEqual(len(self.jellyfin.playlists), 2)

    def test_refuses_when_songs_are_not_in_jellyfin(self) -> None:
        self.lib.write("Ghost.m3u", "#EXTM3U\nNowhere - Missing/01 - Song.flac\n")

        out = self.run_tool("migrate", "--phase", "playlists", expect=1)

        self.assertIn("Nowhere - Missing/01 - Song.flac", out)
        self.assertEqual(self.jellyfin.playlists, {})
        self.assertTrue(self.lib.path("Bussin.m3u").exists())

    def test_dry_run_makes_no_changes(self) -> None:
        self.jellyfin.scan()
        before = self.lib.snapshot()

        self.run_tool("migrate", "--phase", "playlists", "--dry-run")

        self.assertEqual(self.lib.snapshot(), before)
        self.assertEqual(self.jellyfin.mutations, [])

    def test_missing_api_key_fails_with_a_clear_message(self) -> None:
        self.env.write_text("JELLYFIN_URL=http://localhost:8096\nJELLYFIN_API_KEY=\n")

        out = self.run_tool("migrate", "--phase", "playlists", real_jellyfin=True, expect=2)

        self.assertIn("JELLYFIN_API_KEY", out)
        self.assertIn(str(self.env), out)


if __name__ == "__main__":
    unittest.main()
