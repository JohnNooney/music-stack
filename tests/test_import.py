from __future__ import annotations

import json
import os
import unittest

from tests.support import ToolTestCase

A = "Nas - Illmatic/01 - The Genesis.flac"
B = "Nas - Illmatic/02 - N.Y. State Of Mind.flac"
C = "Mobb Deep - The Infamous/03 - Survival Of The Fittest.flac"
D = "Wu-Tang Clan - Enter The Wu-Tang (36 Chambers)/04 - C.R.E.A.M..flac"


class ImportTest(ToolTestCase):
    def setUp(self) -> None:
        super().setUp()
        for i, path in enumerate([A, B, C, D]):
            artist, title = path.split(" - ")[0], path.rsplit(" - ", 1)[1][:-5]
            self.lib.flac(path, title=title, artist=artist, album="X", track=i + 1, isrc=f"I{i}")

    def seed(self, name: str, reference: list[str], current: list[str], on_disk_now: list[str]) -> str:
        """State after an earlier import: reference file, mapping, and the Jellyfin playlist as curated."""
        for path in [A, B, C, D]:
            if path not in on_disk_now:
                os.rename(self.lib.path(path), self.lib.path(path + ".later"))
        self.jellyfin.scan()
        for path in [A, B, C, D]:
            if path not in on_disk_now:
                os.rename(self.lib.path(path + ".later"), self.lib.path(path))
        pid = self.jellyfin.add_playlist(name, current)
        self.lib.write(".playlists/map.json", json.dumps({name: pid}))
        self.lib.write(f".playlists/imports/{name}.m3u8", "#EXTM3U\n" + "".join(p + "\n" for p in reference))
        return pid

    def deemix_writes(self, name: str, entries: list[str]) -> None:
        self.lib.write(f"{name}.m3u8", "".join(e + "\n" for e in entries))

    def test_new_deezer_songs_are_appended_at_the_end_without_reordering(self) -> None:
        pid = self.seed("Bussin", reference=[A, B], current=[B, A], on_disk_now=[A, B])
        self.deemix_writes("Bussin", [A, C, B, D])

        self.run_tool("import")

        self.assertEqual(self.jellyfin.playlist_paths(pid), [B, A, C, D])
        self.assertEqual(self.jellyfin.scans_started, 1)

    def test_songs_removed_by_hand_stay_removed(self) -> None:
        pid = self.seed("Bussin", reference=[A, B], current=[A], on_disk_now=[A, B])
        self.deemix_writes("Bussin", [A, B])

        self.run_tool("import")

        self.assertEqual(self.jellyfin.playlist_paths(pid), [A])

    def test_songs_dropped_on_deezer_are_reported_not_removed(self) -> None:
        pid = self.seed("Bussin", reference=[A, B], current=[A, B], on_disk_now=[A, B])
        self.deemix_writes("Bussin", [A])

        out = self.run_tool("import")

        self.assertEqual(self.jellyfin.playlist_paths(pid), [A, B])
        self.assertIn(f"Bussin: {B}", out.split("Dropped on Deezer")[1].split("\n\n")[0])

    def test_unmapped_deezer_playlist_becomes_a_new_owned_playlist(self) -> None:
        self.seed("Bussin", reference=[A], current=[A], on_disk_now=[A, B, C, D])
        self.deemix_writes("Waves", [C, D])

        self.run_tool("import")

        pid, waves = self.jellyfin.by_name("Waves")
        self.assertEqual(waves.owner, "user-john")
        self.assertEqual(self.jellyfin.playlist_paths(pid), [C, D])
        self.assertEqual(json.loads(self.lib.path(".playlists/map.json").read_text())["Waves"], pid)

    def test_playlist_renamed_in_jellyfin_is_still_matched_by_id(self) -> None:
        pid = self.seed("Bussin", reference=[A], current=[A], on_disk_now=[A, B])
        self.jellyfin.playlists[pid].name = "Bussin (my edit)"
        self.deemix_writes("Bussin", [A, B])

        self.run_tool("import")

        self.assertEqual(len(self.jellyfin.playlists), 1)
        self.assertEqual(self.jellyfin.playlist_paths(pid), [A, B])

    def test_blank_entries_for_failed_tracks_are_ignored(self) -> None:
        pid = self.seed("Bussin", reference=[A], current=[A], on_disk_now=[A, B])
        self.lib.write("Bussin.m3u8", f"{A}\n\n\n{B}\n\n")

        self.run_tool("import")

        self.assertEqual(self.jellyfin.playlist_paths(pid), [A, B])
        reference = self.lib.path(".playlists/imports/Bussin.m3u8").read_text()
        self.assertEqual([line for line in reference.splitlines() if line and not line.startswith("#")], [A, B])

    def test_imported_file_leaves_the_root_and_becomes_the_next_reference(self) -> None:
        self.seed("Bussin", reference=[A], current=[A], on_disk_now=[A, B])
        self.deemix_writes("Bussin", [A, B])

        self.run_tool("import")

        self.assertFalse(self.lib.path("Bussin.m3u8").exists())
        reference = self.lib.path(".playlists/imports/Bussin.m3u8").read_text()
        self.assertEqual([line for line in reference.splitlines() if line and not line.startswith("#")], [A, B])

    def test_root_errors_and_cover_are_archived_and_cover_uploaded(self) -> None:
        pid = self.seed("Bussin", reference=[A], current=[A], on_disk_now=[A, B])
        self.lib.write(".artifacts/Bussin/errors.txt", "old errors\n")
        self.deemix_writes("Bussin", [A, B])
        self.lib.write("errors.txt", "123 | Pouya - life | not available\n")
        self.lib.write("cover.jpg", b"new playlist cover")

        self.run_tool("import")

        self.assertFalse(self.lib.path("errors.txt").exists())
        self.assertFalse(self.lib.path("cover.jpg").exists())
        self.assertIn("Pouya - life", self.lib.path(".artifacts/Bussin/errors.txt").read_text())
        self.assertEqual(self.lib.path(".artifacts/Bussin/cover.jpg").read_bytes(), b"new playlist cover")
        self.assertEqual(self.jellyfin.playlists[pid].image, b"new playlist cover")

    def test_dry_run_changes_nothing(self) -> None:
        pid = self.seed("Bussin", reference=[A], current=[A], on_disk_now=[A, B])
        self.deemix_writes("Bussin", [A, B])
        self.lib.write("cover.jpg", b"cover")
        before = self.lib.snapshot()

        out = self.run_tool("import", "--dry-run")

        self.assertEqual(self.lib.snapshot(), before)
        self.assertEqual(self.jellyfin.playlist_paths(pid), [A])
        self.assertEqual(self.jellyfin.mutations, [])
        self.assertIn("DRY RUN", out)

    def test_import_requires_an_api_key(self) -> None:
        self.env.write_text("JELLYFIN_API_KEY=\n")
        self.deemix_writes("Bussin", [A])

        out = self.run_tool("import", real_jellyfin=True, expect=2)

        self.assertIn("JELLYFIN_API_KEY is not set", out)


if __name__ == "__main__":
    unittest.main()
