"""Tag reader/writer for FLAC (Vorbis comments, PICTURE) and MP3 (ID3v2.3/2.4, APIC)."""

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


# --- writer: rewrite only ARTIST / ALBUM / ALBUMARTIST, preserving everything else ---

_VORBIS_KEYS = ("ARTIST", "ALBUM", "ALBUMARTIST")
_ID3_KEYS = {"ARTIST": "TPE1", "ALBUM": "TALB", "ALBUMARTIST": "TPE2"}


def write_tags(path: Path, *, artists: list[str], album: str, album_artists: list[str]) -> bytes:
    """The file's new bytes with only the three attribution fields rewritten."""
    data = path.read_bytes()
    if data[:4] == b"fLaC":
        return _write_flac(data, artists=artists, album=album, album_artists=album_artists)
    if len(data) >= 10 and data[:3] == b"ID3":
        return _write_id3(data, artists=artists, album=album, album_artists=album_artists)
    if path.suffix.lower() == ".mp3":  # no ID3 tag at all: add a v2.4 one
        return _new_id3(artists=artists, album=album, album_artists=album_artists) + data
    raise ValueError(f"unsupported audio container: {path.name}")


def _rewrite_vorbis(body: bytes, values: dict[str, list[str]]) -> bytes:
    """Rebuild a VORBIS_COMMENT body: same vendor, same other comments, replaced fields."""
    vendor = b""
    comments: list[bytes] = []
    try:
        vendor_len = struct.unpack_from("<I", body, 0)[0]
        i = 4 + vendor_len
        vendor = body[4:i]
        count = struct.unpack_from("<I", body, i)[0]
        i += 4
        for _ in range(count):
            length = struct.unpack_from("<I", body, i)[0]
            entry = body[i + 4:i + 4 + length]
            if entry.split(b"=", 1)[0].decode("utf-8", "replace").upper() not in values:
                comments.append(entry)
            i += 4 + length
    except (struct.error, IndexError):
        vendor, comments = b"", []
    for key in _VORBIS_KEYS:
        comments += [f"{key}={value}".encode("utf-8") for value in values[key] if value]
    out = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(comments))
    return out + b"".join(struct.pack("<I", len(comment)) + comment for comment in comments)


def _write_flac(data: bytes, *, artists: list[str], album: str, album_artists: list[str]) -> bytes:
    pos = 4
    blocks: list[tuple[int, bytes]] = []
    while pos + 4 <= len(data):
        header = data[pos]
        size = int.from_bytes(data[pos + 1:pos + 4], "big")
        blocks.append((header & 0x7F, data[pos + 4:pos + 4 + size]))
        pos += 4 + size
        if header & 0x80:
            break
    audio = data[pos:]
    values = {"ARTIST": artists, "ALBUM": [album], "ALBUMARTIST": album_artists}
    if not any(kind == 4 for kind, _ in blocks):
        blocks.insert(1 if blocks else 0, (4, b""))  # after STREAMINFO
    out = bytearray(b"fLaC")
    for i, (kind, body) in enumerate(blocks):
        if kind == 4:
            body = _rewrite_vorbis(body, values)
        last = 0x80 if i == len(blocks) - 1 else 0
        out += bytes([last | kind]) + len(body).to_bytes(3, "big") + body
    return bytes(out) + audio


def _synchsafe(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def _unsync(data: bytes) -> bytes:
    """Inverse of `_deunsync`: 0x00 after every 0xFF that precedes 0x00 or >= 0xE0."""
    out = bytearray()
    for i, byte in enumerate(data):
        out.append(byte)
        if byte == 0xFF and (i + 1 == len(data) or data[i + 1] == 0 or data[i + 1] >= 0xE0):
            out.append(0)
    return bytes(out)


def _encode_text(values: list[str], version: int, orig_enc: int | None) -> bytes:
    """A text-frame payload: NUL-separated values, the original encoding when it still fits."""
    text = "\x00".join(values)
    candidates = ([orig_enc] if orig_enc in (0, 1, 2) or (version == 4 and orig_enc == 3) else [])
    candidates += [3] if version == 4 else [1]
    for enc in candidates:
        try:
            if enc == 0:
                return b"\x00" + text.encode("latin-1")
            if enc == 2:
                return b"\x02" + text.encode("utf-16-be")
            if enc == 3:
                return b"\x03" + text.encode("utf-8")
            return b"\x01" + text.encode("utf-16")
        except UnicodeEncodeError:
            continue
    raise AssertionError("unreachable")


def _text_frame(frame_id: str, values: list[str], version: int, orig_enc: int | None,
                unsync: bool) -> bytes:
    payload = _encode_text(values, version, orig_enc)
    flags = 0
    if unsync:
        payload = _unsync(payload)
        flags = 0x02
    size = _synchsafe(len(payload)) if version == 4 else struct.pack(">I", len(payload))
    return frame_id.encode("latin-1") + size + bytes([0, flags]) + payload


def _new_id3(*, artists: list[str], album: str, album_artists: list[str]) -> bytes:
    frames = b"".join(_text_frame(_ID3_KEYS[key], values, 4, None, False)
                      for key, values in (("ARTIST", artists), ("ALBUM", [album]),
                                          ("ALBUMARTIST", album_artists)) if any(values))
    return b"ID3\x04\x00\x00" + _synchsafe(len(frames)) + frames


def _write_id3(data: bytes, *, artists: list[str], album: str, album_artists: list[str]) -> bytes:
    version, flags = data[3], data[5]
    tag_size = _unsynchsafe(data[6:10])
    has_footer = version == 4 and bool(flags & 0x10)
    audio = data[10 + tag_size + (10 if has_footer else 0):]
    body = data[10:10 + tag_size]
    if flags & 0x80 and version == 3:
        body = _deunsync(body)
    ext = b""
    if flags & 0x40 and len(body) >= 4:  # extended header, kept verbatim
        ext_len = _unsynchsafe(body[:4]) if version == 4 else struct.unpack(">I", body[:4])[0] + 4
        ext, body = body[:ext_len], body[ext_len:]

    raw_frames: list[tuple[str, bytes]] = []  # (frame id, stored bytes incl. the 10-byte header)
    pos = 0
    while pos + 10 <= len(body) and body[pos] != 0:
        frame_id = body[pos:pos + 4].decode("latin-1")
        size = (_unsynchsafe(body[pos + 4:pos + 8]) if version == 4
                else struct.unpack(">I", body[pos + 4:pos + 8])[0])
        raw_frames.append((frame_id, body[pos:pos + 10 + size]))
        pos += 10 + size

    values = {"TPE1": artists, "TALB": [album], "TPE2": album_artists}
    whole_tag_unsync = version == 4 and bool(flags & 0x80)
    emitted: set[str] = set()
    frames = bytearray()
    for frame_id, raw in raw_frames:
        if frame_id not in values:
            frames += raw
            continue
        if frame_id in emitted:
            continue  # drop duplicate copies of a frame we own
        emitted.add(frame_id)
        if any(values[frame_id]):
            frames += _text_frame(frame_id, values[frame_id], version,
                                  orig_enc=raw[10] if len(raw) > 10 else None,
                                  unsync=whole_tag_unsync or (version == 4 and bool(raw[9] & 0x02)))
    for frame_id, new_values in values.items():
        if frame_id not in emitted and any(new_values):
            frames += _text_frame(frame_id, new_values, version, None, whole_tag_unsync)

    new_body = ext + bytes(frames) + b"\x00" * max(0, len(body) - len(frames))
    if flags & 0x80 and version == 3:
        new_body = _unsync(new_body)
    tag = b"ID3" + bytes([version, 0, flags]) + _synchsafe(len(new_body)) + new_body
    if has_footer:
        tag += b"3DI" + data[3:6] + _synchsafe(len(new_body))
    return tag + audio
