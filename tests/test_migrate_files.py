from __future__ import annotations

import unicodedata
import unittest

from reorganize_playlists.deezer import DeezerAlbum
from tests.support import ToolTestCase


class MigrateFilePhaseTest(ToolTestCase):
    def test_playlist_song_moves_to_its_deemix_path(self) -> None:
        self.lib.flac("Playlists/Bussin/Cymande - Dove.flac", title="Dove", artist="Cymande",
                      album="Listen", albumartist="Zashawn", track=6, isrc="GB8A91200030")
        self.deezer.add("GB8A91200030", album="Listen", artist="Zashawn", track_total=12)

        self.run_tool("migrate")

        self.assertTrue(self.lib.path("Zashawn - Listen/06 - Dove.flac").is_file())
        self.assertFalse(self.lib.path("Playlists/Bussin/Cymande - Dove.flac").exists())

    def test_multi_disc_album_gets_cd_subfolder(self) -> None:
        self.lib.flac("Playlists/Mix/Pink Floyd - Wish.flac", title="Wish", artist="Pink Floyd",
                      album="Pulse", track=3, disc=2, isrc="ISRC2")
        self.deezer.add("ISRC2", album="Pulse", artist="Pink Floyd", track_total=24, disc_total=2)

        self.run_tool("migrate")

        self.assertTrue(self.lib.path("Pink Floyd - Pulse/CD2/03 - Wish.flac").is_file())

    def test_album_with_more_than_99_tracks_pads_to_three_digits(self) -> None:
        self.lib.flac("Playlists/Mix/A - Song.flac", title="Song", artist="A", album="Box", track=7, isrc="ISRC3")
        self.deezer.add("ISRC3", album="Box", artist="A", track_total=120)

        self.run_tool("migrate")

        self.assertTrue(self.lib.path("A - Box/007 - Song.flac").is_file())

    def test_illegal_characters_are_replaced_like_deemix(self) -> None:
        self.lib.flac("Playlists/Mix/AC_DC - What_.flac", title='What? "Now"', artist="AC/DC",
                      album="Live: At <Donington>", track=1, isrc="ISRC4")
        self.deezer.add("ISRC4", album="Live: At <Donington>", artist="AC/DC", track_total=9)

        self.run_tool("migrate")

        self.assertTrue(self.lib.path("AC_DC - Live_ At _Donington_/01 - What_ _Now_.flac").is_file())

    def test_decomposed_unicode_names_end_up_composed(self) -> None:
        nfd = unicodedata.normalize("NFD", "Blue Öyster Cult - Burnin' For You.flac")
        self.lib.flac(f"Playlists/Mix/{nfd}", title=unicodedata.normalize("NFD", "Burnin' For Yöu"),
                      artist="Blue Öyster Cult", album="Fire Of Unknown Origin", track=4, isrc="ISRC5")
        self.deezer.add("ISRC5", album="Fire Of Unknown Origin", artist="Blue Öyster Cult", track_total=9)

        self.run_tool("migrate")

        self.assertIn("Blue Öyster Cult - Fire Of Unknown Origin/04 - Burnin' For Yöu.flac", self.lib.files())

    def test_unknown_on_deezer_falls_back_to_tags_and_is_reported(self) -> None:
        self.lib.flac("Playlists/Mix/Ghost - Rare.flac", title="Rare", artist="Ghost", album="Demo",
                      track=2, isrc="UNKNOWN1")

        out = self.run_tool("migrate")

        self.assertTrue(self.lib.path("Ghost - Demo/02 - Rare.flac").is_file())
        self.assertIn("Deezer lookup failed", out)
        self.assertIn("Playlists/Mix/Ghost - Rare.flac", out.split("Deezer lookup failed")[1])

    def test_missing_album_artist_tag_falls_back_to_track_artist(self) -> None:
        self.lib.flac("Playlists/Mix/Ghost - Rare.flac", title="Rare", artist="Ghost", album="Demo",
                      albumartist=None, track=2, isrc="UNKNOWN1")

        self.run_tool("migrate")

        self.assertTrue(self.lib.path("Ghost - Demo/02 - Rare.flac").is_file())

    def test_exact_release_is_found_by_barcode_before_isrc(self) -> None:
        self.lib.flac("Playlists/Mix/Queen - Bohemian Rhapsody.flac", title="Bohemian Rhapsody", artist="Queen",
                      album="A Night At The Opera", albumartist="Queen", track=11, isrc="GBUM7",
                      barcode="0602547288233")
        self.deezer.add("GBUM7", album="Songs You Need To Hear", artist="Various Artists", track_total=80)
        self.deezer.albums["upc:0602547288233"] = DeezerAlbum(
            id="9", title="A Night At The Opera", artist="Queen", track_total=12, disc_total=1)

        self.run_tool("migrate")

        self.assertTrue(self.lib.path("Queen - A Night At The Opera/11 - Bohemian Rhapsody.flac").is_file())

    def test_placeholder_barcode_written_by_deemix_is_not_looked_up(self) -> None:
        self.lib.flac("Playlists/Mix/Talking Heads - Happy Day.flac", title="Happy Day", artist="Talking Heads",
                      album="Talking Heads: 77", track=3, isrc="USWB1", barcode="Unknown")
        self.deezer.add("USWB1", album="Talking Heads: 77", artist="Talking Heads", track_total=11)

        self.run_tool("migrate")

        self.assertNotIn(("album", "upc:Unknown"), self.deezer.calls)
        self.assertTrue(self.lib.path("Talking Heads - Talking Heads_ 77/03 - Happy Day.flac").is_file())

    def test_report_lists_deezer_tag_disagreements_and_album_artist_mismatches(self) -> None:
        self.lib.flac("Playlists/Mix/Cymande - Dove.flac", title="Dove", artist="Cymande",
                      album="Listen", albumartist="Zashawn", track=6, isrc="GB8A9")
        self.deezer.add("GB8A9", album="Cymande", artist="Cymande", track_total=9)

        out = self.run_tool("migrate", "--dry-run")

        disagreements = out.split("Deezer metadata disagrees with tags")[1].split("\n\n")[0]
        self.assertIn("Playlists/Mix/Cymande - Dove.flac", disagreements)
        mismatches = out.split("Album artist differs from track artist")[1].split("\n\n")[0]
        self.assertIn("Playlists/Mix/Cymande - Dove.flac", mismatches)
        self.assertIn("Zashawn", mismatches)

    def trashed(self) -> set[str]:
        return {p.relative_to(next(self.trash.iterdir())).as_posix()
                for p in self.trash.rglob("*") if p.is_file()} if self.trash.exists() else set()

    def test_album_folder_copy_wins_and_playlist_copy_goes_to_trash(self) -> None:
        album = self.lib.flac("The Roots - Things Fall Apart/02 - Table Of Contents.flac", title="Table Of Contents",
                              artist="The Roots", album="Things Fall Apart", track=2, isrc="ROOTS2", size=10)
        self.lib.flac("Playlists/Old Skool/The Roots - Table Of Contents.flac", title="Table Of Contents",
                      artist="The Roots", album="Things Fall Apart", track=2, isrc="ROOTS2", size=5000)
        before = album.read_bytes()

        out = self.run_tool("migrate")

        self.assertEqual(album.read_bytes(), before)
        self.assertEqual(self.trashed(), {"Playlists/Old Skool/The Roots - Table Of Contents.flac"})
        self.assertEqual([f for f in self.lib.files() if f.endswith(".flac")],
                         ["The Roots - Things Fall Apart/02 - Table Of Contents.flac"])
        trash_lines = out.split("Trashed duplicate copies")[1].split("\n\n")[0]
        self.assertIn("canonical copy: The Roots - Things Fall Apart/02 - Table Of Contents.flac", trash_lines)

    def test_flac_beats_mp3_then_larger_file_wins_among_playlist_copies(self) -> None:
        self.lib.mp3("Playlists/A/Nas - Halftime.mp3", title="Halftime", artist="Nas", album="Illmatic",
                     track=5, isrc="NAS5", size=90000)
        self.lib.flac("Playlists/B/Nas - Halftime.flac", title="Halftime", artist="Nas", album="Illmatic",
                      track=5, isrc="NAS5", size=100)
        best = self.lib.flac("Playlists/C/Nas - Halftime.flac", title="Halftime", artist="Nas", album="Illmatic",
                             track=5, isrc="NAS5", size=200).read_bytes()
        self.deezer.add("NAS5", album="Illmatic", artist="Nas", track_total=10)

        self.run_tool("migrate")

        self.assertEqual(self.lib.path("Nas - Illmatic/05 - Halftime.flac").read_bytes(), best)
        self.assertEqual(self.trashed(), {"Playlists/A/Nas - Halftime.mp3", "Playlists/B/Nas - Halftime.flac"})

    def test_different_isrcs_are_different_songs(self) -> None:
        self.lib.flac("Playlists/A/Sabbath - Paranoid.flac", title="Paranoid", artist="Black Sabbath",
                      album="Paranoid", track=2, isrc="ORIG")
        self.lib.flac("Playlists/B/Sabbath - Paranoid.flac", title="Paranoid", artist="Black Sabbath",
                      album="Paranoid (Remaster)", track=2, isrc="REMASTER")
        self.deezer.add("ORIG", album="Paranoid", artist="Black Sabbath", track_total=8)
        self.deezer.add("REMASTER", album="Paranoid (Remaster)", artist="Black Sabbath", track_total=8)

        self.run_tool("migrate")

        self.assertTrue(self.lib.path("Black Sabbath - Paranoid/02 - Paranoid.flac").is_file())
        self.assertTrue(self.lib.path("Black Sabbath - Paranoid (Remaster)/02 - Paranoid.flac").is_file())
        self.assertEqual(self.trashed(), set())

    def test_songs_without_isrc_are_matched_by_artist_and_title(self) -> None:
        self.lib.flac("Playlists/A/x.flac", title="Dove!", artist="Cymande", album="Cymande", track=1)
        self.lib.mp3("Playlists/B/y.mp3", title="dove", artist="CYMANDE", album="Cymande", track=1)

        self.run_tool("migrate")

        self.assertTrue(self.lib.path("Cymande - Cymande/01 - Dove!.flac").is_file())
        self.assertEqual(self.trashed(), {"Playlists/B/y.mp3"})

    def test_lyrics_sidecar_follows_its_song(self) -> None:
        self.lib.flac("A$AP Ferg - Work.flac", title="Work", artist="A$AP Ferg", album="Trap Lord", track=3,
                      isrc="FERG3")
        self.lib.write("A$AP Ferg - Work.lrc", "[00:01.00]lyrics")
        self.deezer.add("FERG3", album="Trap Lord", artist="A$AP Ferg", track_total=14)

        self.run_tool("migrate")

        self.assertEqual(self.lib.path("A$AP Ferg - Trap Lord/03 - Work.lrc").read_text(), "[00:01.00]lyrics")
        self.assertTrue(self.lib.path("A$AP Ferg - Trap Lord/03 - Work.flac").is_file())

    def test_duplicate_sidecar_is_kept_only_when_canonical_copy_has_none(self) -> None:
        self.lib.flac("Album - X/01 - Song.flac", title="Song", artist="Album", album="X", isrc="S1")
        self.lib.mp3("Playlists/A/Album - Song.mp3", title="Song", artist="Album", album="X", isrc="S1")
        self.lib.write("Playlists/A/Album - Song.lrc", "dup lyrics")
        self.lib.flac("Album - X/02 - Other.flac", title="Other", artist="Album", album="X", track=2, isrc="S2")
        self.lib.write("Album - X/02 - Other.lrc", "own lyrics")
        self.lib.mp3("Playlists/A/Album - Other.mp3", title="Other", artist="Album", album="X", track=2, isrc="S2")
        self.lib.write("Playlists/A/Album - Other.lrc", "dup lyrics 2")

        self.run_tool("migrate")

        self.assertEqual(self.lib.path("Album - X/01 - Song.lrc").read_text(), "dup lyrics")
        self.assertEqual(self.lib.path("Album - X/02 - Other.lrc").read_text(), "own lyrics")
        self.assertEqual(self.trashed(), {"Playlists/A/Album - Song.mp3", "Playlists/A/Album - Other.mp3",
                                          "Playlists/A/Album - Other.lrc"})

    def test_song_is_merged_into_existing_album_folder_without_touching_it(self) -> None:
        self.lib.flac("Daft Punk - Discovery/01 - One More Time.flac", title="One More Time", artist="Daft Punk",
                      album="Discovery", track=1, isrc="DP1")
        existing_cover = self.lib.write("Daft Punk - Discovery/cover.jpg", b"original cover")
        self.lib.flac("Playlists/Mix/Daft Punk - Digital Love.flac", title="Digital Love", artist="Daft Punk",
                      album="Discovery", track=3, isrc="DP3")
        self.deezer.add("DP3", album="Discovery", artist="Daft Punk", track_total=14)

        out = self.run_tool("migrate")

        self.assertTrue(self.lib.path("Daft Punk - Discovery/03 - Digital Love.flac").is_file())
        self.assertEqual(existing_cover.read_bytes(), b"original cover")
        self.assertIn("Daft Punk - Discovery", out.split("Merges into existing album folders")[1].split("\n\n")[0])

    def test_new_album_folder_gets_cover_from_embedded_art(self) -> None:
        self.lib.flac("Playlists/Mix/Nas - Halftime.flac", title="Halftime", artist="Nas", album="Illmatic",
                      track=5, isrc="NAS5", art=b"\xff\xd8\xff\xe0nas-cover\xff\xd9")
        self.deezer.add("NAS5", album="Illmatic", artist="Nas", track_total=10)

        self.run_tool("migrate")

        self.assertEqual(self.lib.path("Nas - Illmatic/cover.jpg").read_bytes(), b"\xff\xd8\xff\xe0nas-cover\xff\xd9")

    def test_mp3_embedded_art_is_extracted_too(self) -> None:
        self.lib.mp3("Playlists/Mix/Nas - Halftime.mp3", title="Halftime", artist="Nas", album="Illmatic",
                     track=5, isrc="NAS5", art=b"\xff\xd8mp3-art\xff\xd9", version=4)
        self.deezer.add("NAS5", album="Illmatic", artist="Nas", track_total=10)

        self.run_tool("migrate")

        self.assertEqual(self.lib.path("Nas - Illmatic/cover.jpg").read_bytes(), b"\xff\xd8mp3-art\xff\xd9")
        self.assertTrue(self.lib.path("Nas - Illmatic/05 - Halftime.mp3").is_file())

    def test_different_recording_at_target_path_is_a_conflict_and_nothing_is_overwritten(self) -> None:
        existing = self.lib.flac("Nas - Illmatic/05 - Halftime.flac", title="Halftime", artist="Nas",
                                 album="Illmatic", track=5, isrc="NAS5-ALBUM")
        before = existing.read_bytes()
        self.lib.flac("Playlists/Mix/Nas - Halftime.flac", title="Halftime", artist="Nas", album="Illmatic",
                      track=5, isrc="NAS5-SINGLE")
        self.lib.write("Mix.m3u", "#EXTM3U\nPlaylists/Mix/Nas - Halftime.flac\n")
        self.deezer.add("NAS5-SINGLE", album="Illmatic", artist="Nas", track_total=10)

        out = self.run_tool("migrate")

        self.assertEqual(existing.read_bytes(), before)
        self.assertTrue(self.lib.path("Playlists/Mix/Nas - Halftime.flac").is_file())
        self.assertIn("Playlists/Mix/Nas - Halftime.flac", out.split("Conflicts")[1].split("\n\n")[0])
        self.assertIn("Playlists/Mix/Nas - Halftime.flac", self.lib.path("Mix.m3u").read_text())

    def test_root_playlist_files_are_rewritten_to_canonical_copies_in_order(self) -> None:
        self.lib.flac("The Roots - Things Fall Apart/02 - Table Of Contents.flac", title="Table Of Contents",
                      artist="The Roots", album="Things Fall Apart", track=2, isrc="ROOTS2")
        self.lib.flac("Playlists/Mix/The Roots - Table Of Contents.flac", title="Table Of Contents",
                      artist="The Roots", album="Things Fall Apart", track=2, isrc="ROOTS2")
        nfd_name = unicodedata.normalize("NFD", "Café - Tarde.flac")
        self.lib.flac(f"Playlists/Mix/{nfd_name}", title="Tarde", artist="Café", album="Días", track=1,
                      isrc="CAFE1")
        self.deezer.add("CAFE1", album="Días", artist="Café", track_total=3)
        self.lib.write("Mix.m3u", "#EXTM3U\r\nPlaylists/Mix/Café - Tarde.flac\r\n\r\n"
                       "Playlists/Mix/The Roots - Table Of Contents.flac\r\nPlaylists/Mix/Gone.flac\r\n")

        out = self.run_tool("migrate")

        lines = [line for line in self.lib.path("Mix.m3u").read_text(encoding="utf-8").splitlines()
                 if line and not line.startswith("#")]
        self.assertEqual(lines, ["Café - Días/01 - Tarde.flac",
                                 "The Roots - Things Fall Apart/02 - Table Of Contents.flac",
                                 "Playlists/Mix/Gone.flac"])
        self.assertIn("Playlists/Mix/Gone.flac", out.split("Dangling playlist entries")[1].split("\n\n")[0])

    def test_legacy_playlist_folders_are_emptied_archived_and_removed(self) -> None:
        self.lib.flac("Playlists/Bussin/Pouya - Void.flac", title="Void", artist="Pouya", album="Five Five",
                      track=1, isrc="P1")
        self.deezer.add("P1", album="Five Five", artist="Pouya", track_total=12)
        self.lib.write("Playlists/Bussin/Untitled.m3u", "#EXTM3U\r\nPouya - Void.flac\r\n", encoding="latin-1")
        self.lib.write("Playlists/Bussin/$uicideboy$ - 2nd Hand.m3u", "x\n")
        self.lib.write("Playlists/Bussin/cover.jpg", b"bussin cover")
        self.lib.write("Playlists/Bussin/errors.txt", "123 | Pouya - life | not available\n")
        self.lib.write("Playlists/Bussin/.DS_Store", b"junk")
        self.lib.write("Playlists/Что cлучилось/dedup_music.log", "log\n")
        self.lib.write("Playlists/.DS_Store", b"junk")
        self.lib.write("Satyricon - Volcano/errors.txt", "all failed\n")

        self.run_tool("migrate")

        self.assertFalse(self.lib.path("Playlists").exists())
        self.assertFalse(self.lib.path("Satyricon - Volcano").exists())
        self.assertEqual(self.lib.path(".artifacts/Bussin/cover.jpg").read_bytes(), b"bussin cover")
        self.assertIn("Pouya - life", self.lib.path(".artifacts/Bussin/errors.txt").read_text())
        self.assertEqual(self.lib.path(".artifacts/Satyricon - Volcano/errors.txt").read_text(), "all failed\n")
        self.assertTrue({"Playlists/Bussin/Untitled.m3u", "Playlists/Bussin/$uicideboy$ - 2nd Hand.m3u",
                         "Playlists/Что cлучилось/dedup_music.log"} <= self.trashed())

    def test_orphaned_lyrics_in_a_legacy_playlist_folder_are_archived(self) -> None:
        self.lib.write("Playlists/Hummers/DREAMS COME TRUE - Approach.lrc", "[00:01.00]lyrics")
        self.lib.write("Playlists/Hummers/errors.txt",
                       "123 | DREAMS COME TRUE - Approach | not available\n")

        self.run_tool("migrate")

        self.assertFalse(self.lib.path("Playlists").exists())
        self.assertEqual(
            self.lib.path(".artifacts/Hummers/DREAMS COME TRUE - Approach.lrc").read_text(),
            "[00:01.00]lyrics")

    def test_orphaned_lyrics_already_archived_are_trashed(self) -> None:
        self.lib.write("Playlists/Hummers/A - Song.lrc", "new lyrics")
        self.lib.write(".artifacts/Hummers/A - Song.lrc", "old lyrics")

        self.run_tool("migrate")

        self.assertFalse(self.lib.path("Playlists").exists())
        self.assertEqual(self.lib.path(".artifacts/Hummers/A - Song.lrc").read_text(), "old lyrics")
        self.assertIn("Playlists/Hummers/A - Song.lrc", self.trashed())

    def test_unexpected_files_keep_a_legacy_folder_in_place_and_are_reported(self) -> None:
        self.lib.write("Playlists/Mix/notes.pdf", b"%PDF")

        out = self.run_tool("migrate")

        self.assertTrue(self.lib.path("Playlists/Mix/notes.pdf").is_file())
        self.assertIn("Playlists/Mix/notes.pdf", out.split("Left in place")[1].split("\n\n")[0])

    def test_dedup_music_leftovers_in_the_library_are_retired_to_trash(self) -> None:
        self.lib.write("dedup_music.py", "print()\n")
        self.lib.write("dedup_music.log", "log\n")
        self.lib.write("dedup_manifest_20260610_145954.json", "{}")

        self.run_tool("migrate")

        self.assertEqual(self.trashed(), {"dedup_music.py", "dedup_music.log",
                                          "dedup_manifest_20260610_145954.json"})

    def small_messy_library(self) -> None:
        self.lib.flac("Daft Punk - Discovery/01 - One More Time.flac", title="One More Time", artist="Daft Punk",
                      album="Discovery", track=1, isrc="DP1")
        self.lib.flac("Playlists/A/Daft Punk - One More Time.flac", title="One More Time", artist="Daft Punk",
                      album="Discovery", track=1, isrc="DP1")
        self.lib.flac("Playlists/A/Nas - Halftime.flac", title="Halftime", artist="Nas", album="Illmatic",
                      track=5, isrc="NAS5")
        self.lib.mp3("Playlists/B/Nas - Halftime.mp3", title="Halftime", artist="Nas", album="Illmatic",
                     track=5, isrc="NAS5")
        self.lib.write("Playlists/A/cover.jpg", b"cover")
        self.lib.write("Playlists/A/Untitled.m3u", "x\n")
        self.lib.write("A.m3u", "#EXTM3U\nPlaylists/A/Nas - Halftime.flac\n")
        self.deezer.add("NAS5", album="Illmatic", artist="Nas", track_total=10)

    def test_dry_run_changes_nothing_and_makes_no_jellyfin_mutations(self) -> None:
        self.small_messy_library()
        before = self.lib.snapshot()

        out = self.run_tool("migrate", "--dry-run")

        self.assertEqual(self.lib.snapshot(), before)
        self.assertFalse(self.trash.exists())
        self.assertEqual(self.jellyfin.mutations, [])
        self.assertIn("Playlists/A/Nas - Halftime.flac -> Nas - Illmatic/05 - Halftime.flac", out)
        self.assertIn("DRY RUN", out)

    def test_live_run_refuses_while_jellyfin_is_scanning(self) -> None:
        self.small_messy_library()
        self.jellyfin.status = "scanning"
        before = self.lib.snapshot()

        out = self.run_tool("migrate", expect=2)

        self.assertIn("scanning", out)
        self.assertEqual(self.lib.snapshot(), before)

    def test_live_run_warns_when_jellyfin_is_running(self) -> None:
        self.small_messy_library()

        out = self.run_tool("migrate")

        self.assertIn("Jellyfin is running", out)

    def test_file_phase_and_dry_run_work_without_an_api_key(self) -> None:
        self.small_messy_library()
        self.env.write_text("JELLYFIN_URL=http://localhost:8096\nJELLYFIN_API_KEY=\n")

        self.run_tool("migrate", "--dry-run", real_jellyfin=True)
        self.run_tool("migrate", real_jellyfin=True)

        self.assertTrue(self.lib.path("Nas - Illmatic/05 - Halftime.flac").is_file())

    def test_reports_progress_of_deezer_lookups(self) -> None:
        self.small_messy_library()

        out = self.run_tool("migrate", "--dry-run")

        self.assertIn("Deezer lookups 1/1", out)

    def test_live_run_self_checks_song_counts_and_trash(self) -> None:
        self.small_messy_library()

        out = self.run_tool("migrate")

        self.assertIn("Self-check passed: 2 unique songs before and after; 2 trashed copies have a canonical copy",
                      out)


if __name__ == "__main__":
    unittest.main()
