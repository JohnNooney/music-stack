"""Replicates Deemix's path generation (bambanah/deemix `utils/pathtemplates.ts`) for album-folder tracks."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_ILLEGAL = re.compile(r'[\0/\\:*?"<>|]')


@dataclass(frozen=True)
class DeemixSettings:
    album_name_template: str = "%artist% - %album%"
    track_name_template: str = "%tracknumber% - %title%"
    playlist_track_name_template: str = "%tracknumber% - %title%"
    create_cd_folder: bool = True
    create_structure_playlist: bool = True
    create_playlist_folder: bool = False
    pad_tracks: bool = True
    pad_single_digit: bool = True
    padding_size: int = 0
    illegal_character_replacer: str = "_"

    @classmethod
    def load(cls, path: Path | None) -> DeemixSettings:
        if path is None or not path.is_file():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        default = cls()
        return cls(
            album_name_template=raw.get("albumNameTemplate", default.album_name_template),
            track_name_template=raw.get("albumTracknameTemplate", default.track_name_template),
            playlist_track_name_template=raw.get("playlistTracknameTemplate",
                                                 default.playlist_track_name_template),
            create_cd_folder=raw.get("createCDFolder", default.create_cd_folder),
            create_structure_playlist=raw.get("createStructurePlaylist", default.create_structure_playlist),
            create_playlist_folder=raw.get("createPlaylistFolder", default.create_playlist_folder),
            pad_tracks=raw.get("padTracks", default.pad_tracks),
            pad_single_digit=raw.get("padSingleDigit", default.pad_single_digit),
            padding_size=int(raw.get("paddingSize", default.padding_size)),
            illegal_character_replacer=raw.get("illegalCharacterReplacer", default.illegal_character_replacer),
        )

    def warnings(self) -> list[str]:
        out = []
        if not self.create_structure_playlist or self.create_playlist_folder:
            out.append("Deemix config is not in structure-playlist mode (createStructurePlaylist=true, "
                       "createPlaylistFolder=false); new playlist downloads will not land in album folders.")
        if self.playlist_track_name_template != self.track_name_template:
            out.append(f"Deemix playlistTracknameTemplate {self.playlist_track_name_template!r} differs from "
                       f"albumTracknameTemplate {self.track_name_template!r}; future playlist downloads "
                       "will not find migrated songs.")
        return out


@dataclass(frozen=True)
class TrackMeta:
    """What Deemix knows about a track when it builds the path."""
    title: str
    artist: str
    album: str
    album_artist: str
    track_number: int
    track_total: int
    disc_number: int
    disc_total: int
    isrc: str = ""


def fix_name(text: str, replacer: str) -> str:
    return unicodedata.normalize("NFC", _ILLEGAL.sub(replacer, text))


def _js_slice(text: str, length: int) -> str:
    """`String.prototype.slice(0, length)`: counts UTF-16 code units, not code points."""
    encoded = text.encode("utf-16-le")
    if len(encoded) <= length * 2:
        return text
    return encoded[:length * 2].decode("utf-16-le", "ignore")


def _fix_long_name(name: str) -> str:
    return "/".join(_js_slice(part, 200) for part in name.split("/"))


def _anti_dot(text: str) -> str:
    text = text.rstrip(". \n")
    return text or "dot"


def pad(number: int, max_value: int, settings: DeemixSettings) -> str:
    if not settings.pad_tracks:
        return str(number)
    size = settings.padding_size or len(str(max_value))
    if settings.pad_single_digit and size == 1:
        size = 2
    return str(number).rjust(size, "0")


def album_folder(meta: TrackMeta, settings: DeemixSettings) -> str:
    c = settings.illegal_character_replacer
    name = (settings.album_name_template
            .replace("%album%", fix_name(meta.album, c))
            .replace("%artist%", fix_name(meta.album_artist, c))
            .replace("%root_artist%", fix_name(meta.album_artist, c))
            .replace("%tracktotal%", str(meta.track_total))
            .replace("%disctotal%", str(meta.disc_total)))
    return _anti_dot(_fix_long_name(name.replace("\\", "/")))


def track_filename(meta: TrackMeta, settings: DeemixSettings) -> str:
    c = settings.illegal_character_replacer
    name = (settings.track_name_template
            .replace("%title%", fix_name(meta.title, c))
            .replace("%artist%", fix_name(meta.artist, c))
            .replace("%album%", fix_name(meta.album, c))
            .replace("%albumartist%", fix_name(meta.album_artist, c))
            .replace("%tracknumber%", pad(meta.track_number, meta.track_total, settings))
            .replace("%position%", pad(meta.track_number, meta.track_total, settings))
            .replace("%tracktotal%", str(meta.track_total))
            .replace("%disctotal%", str(meta.disc_total))
            .replace("%discnumber%", str(meta.disc_number))
            .replace("%isrc%", meta.isrc))
    return _anti_dot(_fix_long_name(name.replace("\\", "/")))


def deemix_path(meta: TrackMeta, extension: str, settings: DeemixSettings) -> str:
    """Library-relative POSIX path Deemix writes for this track as part of an album structure."""
    parts = [album_folder(meta, settings)]
    if meta.disc_total > 1 and settings.create_cd_folder:
        parts.append(f"CD{meta.disc_number}")
    parts.append(track_filename(meta, settings) + extension)
    return "/".join(parts)
