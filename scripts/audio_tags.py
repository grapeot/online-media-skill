"""Read audio metadata tags from local media files."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".aac", ".wma"}
SKIP_EXTENSIONS = {".ncm", ".lrc", ".jpg", ".jpeg", ".png", ".tif", ".ini", ".strings"}

INVENTORY_COLUMNS = [
    "library",
    "full_path",
    "relative_path",
    "filename",
    "extension",
    "bytes",
    "title",
    "artist",
    "album",
    "album_artist",
    "track",
    "year",
    "genre",
    "comment",
    "duration_sec",
    "has_tag_title",
    "has_tag_artist",
    "has_cover",
    "tag_source",
    "title_key",
    "artist_key",
    "read_error",
]


@dataclass(frozen=True)
class AudioTagRecord:
    library: str
    full_path: str
    relative_path: str
    filename: str
    extension: str
    bytes: int
    title: str
    artist: str
    album: str
    album_artist: str
    track: str
    year: str
    genre: str
    comment: str
    duration_sec: str
    has_tag_title: str
    has_tag_artist: str
    has_cover: str
    tag_source: str
    title_key: str
    artist_key: str
    read_error: str

    def to_row(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def normalize_key(value: str) -> str:
    return re.sub(
        r"[\s\-—_·・（）()《》〈〉\[\]【】,，.。!！?？:：;；\"'’“”&＋+]+",
        "",
        value,
    ).casefold()


def first_text(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        return first_text(value[0])
    if isinstance(value, tuple):
        if not value:
            return ""
        return first_text(value[0])
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def first_tag(tags: Mapping[object, object], keys: Sequence[object]) -> str:
    for key in keys:
        if key in tags and tags[key]:
            text = first_text(tags[key])
            if text:
                return text
    return ""


def parse_filename(path: Path) -> tuple[str, str]:
    stem = path.stem
    stem = re.sub(r"^\d+\s*[-_.]\s*", "", stem)
    stem = re.sub(r"^\d+\s+", "", stem)
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return title.strip(), artist.strip()
    return stem.strip(), path.parent.name.strip()


def _payload_from_id3(id3: ID3) -> dict[str, str]:
    return {
        "title": first_tag(id3, ["TIT2"]),
        "artist": first_tag(id3, ["TPE1"]),
        "album": first_tag(id3, ["TALB"]),
        "album_artist": first_tag(id3, ["TPE2"]),
        "track": first_tag(id3, ["TRCK"]),
        "year": first_tag(id3, ["TDRC", "TYER"]),
        "genre": first_tag(id3, ["TCON"]),
        "comment": first_tag(id3, ["COMM::eng", "COMM"]),
    }


def _read_mp3_tags(path: Path) -> tuple[dict[str, str], bool, float | None, str]:
    duration: float | None = None
    try:
        audio = MP3(path)
        duration = audio.info.length if audio.info else None
        tags = audio.tags
        if tags is None:
            id3 = ID3(path)
            payload = _payload_from_id3(id3)
            has_cover = any(str(key).startswith("APIC") for key in id3.keys())
            return payload, has_cover, duration, "id3"

        payload = _payload_from_id3(cast(ID3, tags))
        has_cover = any(str(key).startswith("APIC") for key in tags.keys())
        return payload, has_cover, duration, "id3"
    except Exception:
        id3 = ID3(path)
        payload = _payload_from_id3(id3)
        has_cover = any(str(key).startswith("APIC") for key in id3.keys())
        return payload, has_cover, duration, "id3"


def _read_mp4_tags(path: Path) -> tuple[dict[str, str], bool, float | None, str]:
    audio = MP4(path)
    tags = audio.tags or {}
    track = ""
    if "trkn" in tags and tags["trkn"]:
        track = first_text(tags["trkn"][0][0])
    payload = {
        "title": first_tag(tags, ["\xa9nam"]),
        "artist": first_tag(tags, ["\xa9ART"]),
        "album": first_tag(tags, ["\xa9alb"]),
        "album_artist": first_tag(tags, ["aART"]),
        "track": track,
        "year": first_tag(tags, ["\xa9day"]),
        "genre": first_tag(tags, ["\xa9gen"]),
        "comment": first_tag(tags, ["\xa9cmt"]),
    }
    has_cover = bool(tags.get("covr"))
    return payload, has_cover, audio.info.length if audio.info else None, "mp4"


def _read_flac_tags(path: Path) -> tuple[dict[str, str], bool, float | None, str]:
    audio = FLAC(path)
    tags = audio.tags or {}
    payload = {
        "title": first_tag(tags, ["title"]),
        "artist": first_tag(tags, ["artist"]),
        "album": first_tag(tags, ["album"]),
        "album_artist": first_tag(tags, ["albumartist"]),
        "track": first_tag(tags, ["tracknumber"]),
        "year": first_tag(tags, ["date"]),
        "genre": first_tag(tags, ["genre"]),
        "comment": first_tag(tags, ["comment"]),
    }
    has_cover = bool(audio.pictures)
    return payload, has_cover, audio.info.length if audio.info else None, "vorbis"


def read_audio_tags(path: Path) -> dict[str, str | bool | float | None]:
    extension = path.suffix.lower()
    payload: dict[str, str] = {
        "title": "",
        "artist": "",
        "album": "",
        "album_artist": "",
        "track": "",
        "year": "",
        "genre": "",
        "comment": "",
    }
    has_cover = False
    duration: float | None = None
    tag_source = "none"
    error = ""

    try:
        if extension == ".mp3":
            payload, has_cover, duration, tag_source = _read_mp3_tags(path)
        elif extension in {".m4a", ".mp4", ".aac"}:
            payload, has_cover, duration, tag_source = _read_mp4_tags(path)
        elif extension == ".flac":
            payload, has_cover, duration, tag_source = _read_flac_tags(path)
        else:
            media = MutagenFile(path, easy=True)
            if media is not None and media.tags is not None:
                easy_tags = cast(Mapping[object, object], media.tags)
                payload["title"] = first_tag(easy_tags, ["title"])
                payload["artist"] = first_tag(easy_tags, ["artist"])
                payload["album"] = first_tag(easy_tags, ["album"])
                payload["track"] = first_tag(easy_tags, ["tracknumber"])
                payload["year"] = first_tag(easy_tags, ["date"])
                payload["genre"] = first_tag(easy_tags, ["genre"])
                tag_source = "easy"
            if media is not None and media.info is not None:
                duration = media.info.length
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:500]

    filename_title, filename_artist = parse_filename(path)
    has_tag_title = bool(payload["title"])
    has_tag_artist = bool(payload["artist"])
    title = payload["title"] or filename_title
    artist = payload["artist"] or filename_artist
    if not has_tag_title and title:
        tag_source = "filename_fallback" if tag_source == "none" else f"{tag_source}+filename"

    return {
        **payload,
        "title": title,
        "artist": artist,
        "duration_sec": round(duration, 1) if duration is not None else None,
        "has_tag_title": has_tag_title,
        "has_tag_artist": has_tag_artist,
        "has_cover": has_cover,
        "tag_source": tag_source,
        "read_error": error,
    }


def iter_audio_files(roots: Sequence[Path]) -> Iterator[tuple[str, Path]]:
    for root in roots:
        library = root.name.lower().replace(" ", "_")
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.suffix.lower() in SKIP_EXTENSIONS:
                continue
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            yield library, path


def inventory_record(library: str, root: Path, path: Path) -> AudioTagRecord:
    tags = read_audio_tags(path)
    relative = path.relative_to(root) if path.is_relative_to(root) else path.name
    duration = tags["duration_sec"]
    return AudioTagRecord(
        library=library,
        full_path=str(path),
        relative_path=str(relative),
        filename=path.name,
        extension=path.suffix.lower(),
        bytes=path.stat().st_size,
        title=str(tags["title"]),
        artist=str(tags["artist"]),
        album=str(tags["album"]),
        album_artist=str(tags["album_artist"]),
        track=str(tags["track"]),
        year=str(tags["year"]),
        genre=str(tags["genre"]),
        comment=str(tags["comment"]),
        duration_sec="" if duration is None else str(duration),
        has_tag_title="true" if tags["has_tag_title"] else "false",
        has_tag_artist="true" if tags["has_tag_artist"] else "false",
        has_cover="true" if tags["has_cover"] else "false",
        tag_source=str(tags["tag_source"]),
        title_key=normalize_key(str(tags["title"])),
        artist_key=normalize_key(str(tags["artist"])),
        read_error=str(tags["read_error"]),
    )


def extract_cover_art(path: Path, output_path: Path) -> bool:
    extension = path.suffix.lower()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if extension == ".mp3":
            id3 = ID3(path)
            for key in id3.keys():
                if str(key).startswith("APIC"):
                    frame = id3[key]
                    data = getattr(frame, "data", b"")
                    if data:
                        output_path.write_bytes(data)
                        return True
        elif extension == ".flac":
            audio = FLAC(path)
            if audio.pictures:
                output_path.write_bytes(audio.pictures[0].data)
                return True
        elif extension in {".m4a", ".mp4", ".aac"}:
            audio = MP4(path)
            covers = audio.tags.get("covr") if audio.tags else None
            if covers:
                output_path.write_bytes(covers[0])
                return True
    except Exception:
        return False
    return False
