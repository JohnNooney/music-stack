from __future__ import annotations

import unittest

from reorganize_playlists.deezer import DeezerAlbum
from reorganize_playlists.tags import read_art, read_tags
from tests.support import JPEG, ToolTestCase


class RetagTest(ToolTestCase):
    def trashed(self) -> dict[str, bytes]:
        if not self.trash.exists():
            return {}
        run = next(self.trash.iterdir())
        return {p.relative_to(run).as_posix(): p.read_bytes()
                for p in run.rglob("*") if p.is_file()}
    def test_dry_run_reports_field_diffs_and_changes_nothing(self) -> None:
        self.lib.flac("Janis Joplin - Pearl (Legacy Edition)/CD1/03 - Me and Bobby McGee.flac",
                      title="Me and Bobby McGee",
                      artist=["Janis Joplin", "Pearl Pearl", "Vince Mitchell"],
                      album="Collections", albumartist="Janis Joplin", track=3, disc=1,
                      isrc="USJAN1")
        self.deezer.add("USJAN1", album="Pearl (Legacy Edition)", artist="Janis Joplin",
                        track_total=10, disc_total=2, contributors=["Janis Joplin"])
        before = self.lib.snapshot()

        out = self.run_tool("retag", "--dry-run")

        self.assertEqual(self.lib.snapshot(), before)
        self.assertFalse(self.trash.exists())
        self.assertEqual(self.jellyfin.mutations, [])
        self.assertIn("DRY RUN", out)
        retagged = out.split("Retagged")[1].split("\n\n")[0]
        self.assertIn("03 - Me and Bobby McGee.flac", retagged)
        self.assertIn("Collections", retagged)
        self.assertIn("Pearl (Legacy Edition)", retagged)
        self.assertIn("Pearl Pearl", retagged)

    def test_live_run_rewrites_tags_preserves_the_rest_and_commits(self) -> None:
        rel = "Janis Joplin - Pearl (Legacy Edition)/CD1/03 - Me and Bobby McGee.flac"
        path = self.lib.flac(rel, title="Me and Bobby McGee",
                             artist=["Janis Joplin", "Pearl Pearl", "Vince Mitchell"],
                             album="Collections", albumartist="Janis Joplin", track=3, disc=1,
                             isrc="USJAN1", barcode="0500001")
        original = path.read_bytes()
        self.deezer.add("USJAN1", album="Pearl (Legacy Edition)", artist="Janis Joplin",
                        track_total=10, disc_total=2, contributors=["Janis Joplin"])

        out = self.run_tool("retag", real_jellyfin=True)

        tags = read_tags(path)
        self.assertEqual((tags.artists, tags.album, tags.album_artists),
                         (["Janis Joplin"], "Pearl (Legacy Edition)", ["Janis Joplin"]))
        self.assertEqual((tags.title, tags.isrc, tags.track_number, tags.disc_number),
                         ("Me and Bobby McGee", "USJAN1", 3, 1))
        art = read_art(path)
        assert art is not None
        self.assertEqual(art.data, JPEG)
        self.assertTrue(path.read_bytes().endswith(original[-110:]))  # audio tail untouched
        self.assertEqual(self.trashed(), {rel: original})
        self.assertIn("Self-check passed: 1 files re-read and verified", out)
        rows = self.lib.path(".inventory.tsv").read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(r.startswith(f"{rel}\tUSJAN1\t") and "Pearl (Legacy Edition)" in r
                            for r in rows), rows)
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(),
                         "retag: 1 files retagged; 0 misplaced; 0 cosmetic differences; "
                         "0 Deezer lookups failed")

    def test_mp3_v23_and_v24_rewrites_keep_version_art_and_multi_artists(self) -> None:
        p3 = self.lib.mp3("Steely Dan - Aja/03 - Haitian Divorce.mp3", title="Haitian Divorce",
                          artist="Steely Dan", album="The Royal Scam", albumartist="Steely Dan",
                          isrc="USSD1", version=3)
        p4 = self.lib.mp3("Kraan - Kraan/05 - Song.mp3", title="Song", artist="Kraan\x00Zashawn",
                          album="Kraan", albumartist="Kraan", track=5, isrc="KRN5", version=4)
        self.deezer.add("USSD1", album="Aja", artist="Steely Dan", track_total=7)
        self.deezer.add("KRN5", album="Kraan", artist="Kraan", track_total=6,
                        contributors=["Kraan", "Guest"])

        self.run_tool("retag")

        self.assertEqual(p3.read_bytes()[3], 3)  # ID3 version kept
        self.assertEqual(p4.read_bytes()[3], 4)
        tags3 = read_tags(p3)
        self.assertEqual((tags3.artists, tags3.album, tags3.album_artists),
                         (["Steely Dan"], "Aja", ["Steely Dan"]))
        tags4 = read_tags(p4)
        self.assertEqual(tags4.artists, ["Kraan", "Guest"])
        art = read_art(p3)
        assert art is not None
        self.assertEqual(art.data, JPEG)
        self.assertEqual((tags4.title, tags4.isrc, tags4.track_number), ("Song", "KRN5", 5))

    def test_cosmetic_only_differences_are_reported_but_not_written(self) -> None:
        path = self.lib.flac("Lil' Keke - Album/01 - Song.flac", title="Song", artist="Lil' Keke",
                             album="Album", albumartist="Lil' KeKe", isrc="LK1")
        self.deezer.add("LK1", album="Album", artist="Lil' Keke", track_total=10)
        before = path.read_bytes()

        out = self.run_tool("retag")

        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.trashed(), {})
        cosmetic = out.split("Cosmetic differences (not rewritten)")[1].split("\n\n")[0]
        self.assertIn("Lil' KeKe", cosmetic)
        self.assertIn("Lil' Keke", cosmetic)

    def test_substantive_diff_in_any_field_rewrites_all_three(self) -> None:
        path = self.lib.flac("Nas - Illmatic/05 - Halftime.flac", title="Halftime",
                             artist=["Nas", "Zashawn"], album="Illmatic",
                             albumartist=["Nas", "DJ Guest"], track=5, isrc="NAS5")
        self.deezer.add("NAS5", album="Illmatic", artist="Nas", track_total=10,
                        contributors=["Nas"])

        self.run_tool("retag")

        tags = read_tags(path)
        self.assertEqual((tags.artists, tags.album, tags.album_artists),
                         (["Nas"], "Illmatic", ["Nas"]))

    def test_empty_albumartist_filled_and_track_artists_kept_on_compilation(self) -> None:
        path = self.lib.flac("Verschiedene Interpreten - Habibi Funk 015/01 - Song.flac",
                             title="Song", artist=["Artist A", "Artist B"], album="Habibi Funk 015",
                             albumartist=None, isrc="HF1")
        self.deezer.add("HF1", album="Habibi Funk 015", artist="Verschiedene Interpreten",
                        track_total=15, contributors=["Artist A", "Artist B"])

        self.run_tool("retag")

        tags = read_tags(path)
        self.assertEqual(tags.album_artists, ["Verschiedene Interpreten"])
        self.assertEqual(tags.artists, ["Artist A", "Artist B"])

    def test_misplaced_file_is_reported_and_untouched(self) -> None:
        path = self.lib.flac("Steely Dan - Aja/03 - Haitian Divorce.flac", title="Haitian Divorce",
                             artist="Steely Dan", album="The Royal Scam", albumartist="Steely Dan",
                             isrc="USSD9")
        self.deezer.add("USSD9", album="The Royal Scam", artist="Steely Dan", track_total=7)
        before = path.read_bytes()

        out = self.run_tool("retag")

        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.trashed(), {})
        misplaced = out.split("Misplaced (tag agrees with Deezer)")[1].split("\n\n")[0]
        self.assertIn("Steely Dan - Aja/03 - Haitian Divorce.flac", misplaced)
        self.assertIn("The Royal Scam", misplaced)

    def test_misplaced_file_with_dirty_fields_is_still_retagged(self) -> None:
        rel = "Steely Dan - Aja/03 - Haitian Divorce.flac"
        path = self.lib.flac(rel, title="Haitian Divorce", artist=["Steely Dan", "Zashawn"],
                             album="The Royal Scam", albumartist=["Steely Dan", "DJ Guest"],
                             isrc="USSD9")
        self.deezer.add("USSD9", album="The Royal Scam", artist="Steely Dan", track_total=7,
                        contributors=["Steely Dan"])

        out = self.run_tool("retag")

        tags = read_tags(path)
        self.assertEqual((tags.artists, tags.album, tags.album_artists),
                         (["Steely Dan"], "The Royal Scam", ["Steely Dan"]))
        misplaced = out.split("Misplaced (tag agrees with Deezer)")[1].split("\n\n")[0]
        self.assertIn(rel, misplaced)
        retagged = out.split("Retagged")[1].split("\n\n")[0]
        self.assertIn(rel, retagged)

    def test_lookup_failure_falls_back_to_folder_and_keeps_artist(self) -> None:
        path = self.lib.flac("Ghost - Demo/02 - Rare.flac", title="Rare", artist="Ghost",
                             album="Wrong Album", albumartist="Wrong Artist", isrc="UNKNOWN1")

        out = self.run_tool("retag")

        tags = read_tags(path)
        self.assertEqual((tags.artists, tags.album, tags.album_artists),
                         (["Ghost"], "Demo", ["Ghost"]))
        failed = out.split("Deezer lookup failed")[1].split("\n\n")[0]
        self.assertIn("Ghost - Demo/02 - Rare.flac", failed)
        self.assertIn("artist kept", failed)

    def test_barcode_resolves_the_exact_release_before_isrc(self) -> None:
        path = self.lib.flac("Queen - A Night At The Opera/11 - Bohemian Rhapsody.flac",
                             title="Bohemian Rhapsody", artist="Queen", album="Bo Rhap",
                             albumartist="Queen", track=11, isrc="GBUM7",
                             barcode="0602547288233")
        self.deezer.add("GBUM7", album="Songs You Need To Hear", artist="Various Artists",
                        track_total=80)
        self.deezer.albums["upc:0602547288233"] = DeezerAlbum(
            id="9", title="A Night At The Opera", artist="Queen", track_total=12, disc_total=1)

        self.run_tool("retag")

        self.assertEqual(read_tags(path).album, "A Night At The Opera")
        self.assertIn(("album", "upc:0602547288233"), self.deezer.calls)

    def test_legacy_playlist_folder_files_are_retagged_from_deezer(self) -> None:
        path = self.lib.flac("Playlists/Mix/Nas - Halftime.flac", title="Halftime", artist="Nas",
                             album="Wrong", isrc="NAS9")
        self.deezer.add("NAS9", album="Illmatic", artist="Nas", track_total=10)

        self.run_tool("retag")

        tags = read_tags(path)
        self.assertEqual((tags.artists, tags.album, tags.album_artists),
                         (["Nas"], "Illmatic", ["Nas"]))

    def test_file_without_ids_uses_the_folder_fallback(self) -> None:
        path = self.lib.flac("Ghost - Demo/02 - Rare.flac", title="Rare", artist="Ghost",
                             album="Demo")

        out = self.run_tool("retag")

        self.assertEqual(read_tags(path).album_artists, ["Ghost"])
        failed = out.split("Deezer lookup failed")[1].split("\n\n")[0]
        self.assertIn("Ghost - Demo/02 - Rare.flac", failed)

    def test_deemix_mangled_folder_name_is_not_misplaced(self) -> None:
        path = self.lib.flac("Funkadelic - Who's a Funkadelic_/02 - You'll Like it Too.flac",
                             title="You'll Like it Too", artist="Funkadelic",
                             album="Who's a Funkadelic?", albumartist="Funkadelic", isrc="FNK1")
        self.deezer.add("FNK1", album="Who's a Funkadelic?", artist="Funkadelic", track_total=12)
        before = path.read_bytes()

        out = self.run_tool("retag")

        self.assertEqual(path.read_bytes(), before)
        self.assertNotIn("Misplaced (", out)

    def test_folder_fallback_keeps_unmangled_tag_values(self) -> None:
        path = self.lib.flac("Tom Petty - Anthology_ Through The Years/01 - Song.flac",
                             title="Song", artist="Tom Petty",
                             album="Anthology: Through The Years", isrc="UNKNOWN9")

        self.run_tool("retag")

        tags = read_tags(path)
        self.assertEqual(tags.album, "Anthology: Through The Years")  # not 'Anthology_ ...'
        self.assertEqual(tags.album_artists, ["Tom Petty"])

    def test_second_run_on_a_clean_library_is_a_noop(self) -> None:
        path = self.lib.flac("Nas - Illmatic/05 - Halftime.flac", title="Halftime",
                             artist=["Nas", "Zashawn"], album="Illmatic", isrc="NAS5")
        self.deezer.add("NAS5", album="Illmatic", artist="Nas", track_total=10)
        self.run_tool("retag")
        after = {k: v for k, v in self.lib.snapshot().items() if not k.startswith(".git")}

        out = self.run_tool("retag")

        self.assertEqual({k: v for k, v in self.lib.snapshot().items() if not k.startswith(".git")},
                         after)
        self.assertNotIn("Retagged (", out)
        self.assertNotIn("Misplaced (", out)
        self.assertNotIn("Cosmetic differences (", out)
        self.assertIn("run a library scan in Jellyfin", out)

    def test_rollback_restores_the_original_bytes(self) -> None:
        rel = "Nas - Illmatic/05 - Halftime.flac"
        path = self.lib.flac(rel, title="Halftime", artist=["Nas", "Zashawn"], album="Illmatic",
                             albumartist=["Nas", "DJ Guest"], isrc="NAS5")
        original = path.read_bytes()
        self.deezer.add("NAS5", album="Illmatic", artist="Nas", track_total=10)
        self.run_tool("retag")
        self.assertNotEqual(path.read_bytes(), original)

        self.run_tool("rollback", str(self.latest_manifest()))

        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.trashed(), {})


if __name__ == "__main__":
    unittest.main()
