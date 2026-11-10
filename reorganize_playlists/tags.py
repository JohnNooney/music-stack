"""Read-only tag reader for FLAC (Vorbis comments, PICTURE) and MP3 (ID3v2.3/2.4, APIC)."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO


@dataclass(frozen=True)
class Tags:
    title: str = ""
    artists: list[str] = field(default_factory=list)
    album: str = ""
    album_artists: list[str] = field(default_factory=list)
    track_number: int | None = None
    track_total: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    isrc: str = ""
    barcode: str = ""
    date: str = ""
    has_art: bool = False

    @property
    def artist(self) -> str:
        return self.artists[0] if self.artists else ""

    @property
    def album_artist(self) -> str:
        return self.album_artists[0] if self.album_artists else ""


@dataclass(frozen=True)
class Art:
    mime: str
    data: bytes


def read_tags(path: Path) -> Tags:
    return _read(path)[0]


def read_art(path: Path) -> Art | None:
    return _read(path, want_art=True)[1]


def _read(path: Path, want_art: bool = False) -> tuple[Tags, Art | None]:
    try:
        with path.open("rb") as f:
            head = f.read(10)
            f.seek(0)
            if head[:4] == b"fLaC":
                return _read_flac(_flac_metadata(f), want_art)
            if head[:3] == b"ID3":
                return _read_id3(f.read(10 + _id3_size(head)), want_art)
    except (OSError, struct.error, IndexError, ValueError):
        pass
    return Tags(), None


def _split_number(value: str) -> tuple[int | None, int | None]:
    number, _, total = value.partition("/")
    return _int(number), _int(total)


def _int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value.isdigit() else None


def _build(values: dict[str, list[str]], has_art: bool) -> Tags:
    def first(key: str) -> str:
        return values.get(key, [""])[0].strip()

    track, track_total = _split_number(first("TRACKNUMBER"))
    disc, disc_total = _split_number(first("DISCNUMBER"))
    return Tags(
        title=first("TITLE"),
        artists=[v for v in values.get("ARTIST", []) if v],
        album=first("ALBUM"),
        album_artists=[v for v in values.get("ALBUMARTIST", []) if v],
        track_number=track,
        track_total=track_total or _int(first("TRACKTOTAL") or first("TOTALTRACKS")),
        disc_number=disc,
        disc_total=disc_total or _int(first("DISCTOTAL") or first("TOTALDISCS")),
        isrc=first("ISRC").upper(),
        barcode=next((b for b in (first("BARCODE"), first("UPC")) if b and b.isdigit()), ""),
        date=first("DATE"),
        has_art=has_art,
    )


def _flac_metadata(f: BinaryIO) -> bytes:
    """Read only the metadata blocks, not the audio frames."""
    data = f.read(4)
    while True:
        header = f.read(4)
        if len(header) < 4:
            return data
        data += header + f.read(int.from_bytes(header[1:], "big"))
        if header[0] & 0x80:
            return data


def _read_flac(data: bytes, want_art: bool) -> tuple[Tags, Art | None]:
    values: dict[str, list[str]] = {}
    art: Art | None = None
    has_art = False
    pos = 4
    while pos + 4 <= len(data):
        header = data[pos]
        size = int.from_bytes(data[pos + 1:pos + 4], "big")
        body = data[pos + 4:pos + 4 + size]
        kind = header & 0x7F
        if kind == 4:
            vendor_len = struct.unpack_from("<I", body, 0)[0]
            i = 4 + vendor_len
            count = struct.unpack_from("<I", body, i)[0]
            i += 4
            for _ in range(count):
                length = struct.unpack_from("<I", body, i)[0]
                key, _, value = body[i + 4:i + 4 + length].decode("utf-8", "replace").partition("=")
                values.setdefault(key.upper(), []).append(value)
                i += 4 + length
        elif kind == 6:
            has_art = True
            if want_art and art is None:
                mime_len = struct.unpack_from(">I", body, 4)[0]
                mime = body[8:8 + mime_len].decode("ascii", "replace")
                i = 8 + mime_len
                desc_len = struct.unpack_from(">I", body, i)[0]
                i += 4 + desc_len + 16
                data_len = struct.unpack_from(">I", body, i)[0]
                art = Art(mime=mime, data=body[i + 4:i + 4 + data_len])
        pos += 4 + size
        if header & 0x80:
            break
    return _build(values, has_art), art


ID3_FRAMES = {
    "TIT2": "TITLE", "TPE1": "ARTIST", "TALB": "ALBUM", "TPE2": "ALBUMARTIST",
    "TRCK": "TRACKNUMBER", "TPOS": "DISCNUMBER", "TSRC": "ISRC", "TDRC": "DATE", "TYER": "DATE",
}


def _id3_size(header: bytes) -> int:
    if len(header) < 10 or header[:3] != b"ID3":
        return 0
    return _unsynchsafe(header[6:10]) + (10 if header[5] & 0x10 else 0)


def _unsynchsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _deunsync(data: bytes) -> bytes:
    return data.replace(b"\xff\x00", b"\xff")


def _decode_text(payload: bytes) -> list[str]:
    if not payload:
        return []
    enc, raw = payload[0], payload[1:]
    if enc == 1:
        text = raw.decode("utf-16", "replace")
    elif enc == 2:
        text = raw.decode("utf-16-be", "replace")
    elif enc == 3:
        text = raw.decode("utf-8", "replace")
    else:
        text = raw.decode("latin-1")
    return [v for v in text.split("\x00") if v]


def _split_terminated(raw: bytes, enc: int) -> tuple[bytes, bytes]:
    """Split `raw` at the first encoding-appropriate NUL terminator."""
    if enc in (1, 2):
        for i in range(0, len(raw) - 1, 2):
            if raw[i:i + 2] == b"\x00\x00":
                return raw[:i], raw[i + 2:]
        return raw, b""
    head, _, tail = raw.partition(b"\x00")
    return head, tail


def _read_id3(data: bytes, want_art: bool) -> tuple[Tags, Art | None]:
    version, flags = data[3], data[5]
    body = data[10:]
    if flags & 0x80 and version == 3:
        body = _deunsync(body)
    if flags & 0x40:  # extended header
        ext = _unsynchsafe(body[:4]) if version == 4 else struct.unpack(">I", body[:4])[0] + 4
        body = body[ext:]
    values: dict[str, list[str]] = {}
    art: Art | None = None
    has_art = False
    pos = 0
    while pos + 10 <= len(body) and body[pos] != 0:
        frame_id = body[pos:pos + 4].decode("latin-1")
        size_bytes = body[pos + 4:pos + 8]
        size = _unsynchsafe(size_bytes) if version == 4 else struct.unpack(">I", size_bytes)[0]
        frame_flags = body[pos + 9]
        payload = body[pos + 10:pos + 10 + size]
        pos += 10 + size
        if version == 4:
            if frame_flags & 0x02:
                payload = _deunsync(payload)
            if frame_flags & 0x01:
                payload = payload[4:]
        if frame_id in ID3_FRAMES:
            values.setdefault(ID3_FRAMES[frame_id], []).extend(_decode_text(payload))
        elif frame_id == "APIC":
            has_art = True
            if want_art and art is None:
                enc = payload[0]
                mime, rest = payload[1:].split(b"\x00", 1)
                _, image = _split_terminated(rest[1:], enc)
                art = Art(mime=mime.decode("latin-1") or "image/jpeg", data=image)
    if "DATE" in values:
        values["DATE"] = values["DATE"][:1]
    return _build(values, has_art), art
