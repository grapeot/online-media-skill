from __future__ import annotations

import csv
from pathlib import Path

from mutagen.id3 import APIC, COMM, ID3, TALB, TIT2, TPE1

from scripts import audio_tags
from scripts.audio_tags import (
    INVENTORY_COLUMNS,
    iter_audio_files,
    inventory_record,
    normalize_key,
    parse_filename,
    read_audio_tags,
)
from scripts.music_library_dedup import command_read_tags


def write_id3_mp3(path: Path, *, title: str = "", artist: str = "", album: str = "", with_cover: bool = False) -> None:
    tags = ID3()
    if title:
        tags.add(TIT2(encoding=3, text=title))
    if artist:
        tags.add(TPE1(encoding=3, text=artist))
    if album:
        tags.add(TALB(encoding=3, text=album))
    tags.add(COMM(encoding=3, lang="eng", desc="", text="demo comment"))
    if with_cover:
        tags.add(
            APIC(
                encoding=3,
                mime="image/jpeg",
                type=3,
                desc="Cover",
                data=b"fakecover",
            )
        )
    tags.save(path)


def test_normalize_key() -> None:
    assert normalize_key("七里香 - 周杰伦") == normalize_key("七里香周杰伦")


def test_parse_filename() -> None:
    title, artist = parse_filename(Path("/tmp/周杰伦 - 七里香.mp3"))
    assert title == "七里香"
    assert artist == "周杰伦"

    numbered_title, numbered_artist = parse_filename(Path("/tmp/01. Demo Artist - Demo Song.mp3"))
    assert numbered_title == "Demo Song"
    assert numbered_artist == "Demo Artist"


def test_read_mp3_tags(tmp_path: Path) -> None:
    audio_path = tmp_path / "01. Demo Artist - Demo Song.mp3"
    write_id3_mp3(audio_path, title="Demo Song", artist="Demo Artist", album="Demo Album", with_cover=True)

    tags = read_audio_tags(audio_path)
    assert tags["title"] == "Demo Song"
    assert tags["artist"] == "Demo Artist"
    assert tags["album"] == "Demo Album"
    assert tags["has_tag_title"] is True
    assert tags["has_tag_artist"] is True
    assert tags["has_cover"] is True
    assert tags["tag_source"] == "id3"


def test_read_flac_tags_uses_flac_reader(tmp_path: Path, monkeypatch) -> None:
    audio_path = tmp_path / "Demo Artist - Demo Song.flac"
    audio_path.write_bytes(b"placeholder")

    def fake_read_flac(path: Path) -> tuple[dict[str, str], bool, float | None, str]:
        assert path == audio_path
        return (
            {
                "title": "Demo Song",
                "artist": "Demo Artist",
                "album": "Demo Album",
                "album_artist": "",
                "track": "1",
                "year": "2020",
                "genre": "Pop",
                "comment": "",
            },
            True,
            201.5,
            "vorbis",
        )

    monkeypatch.setattr(audio_tags, "_read_flac_tags", fake_read_flac)
    tags = read_audio_tags(audio_path)
    assert tags["title"] == "Demo Song"
    assert tags["artist"] == "Demo Artist"
    assert tags["has_cover"] is True
    assert tags["tag_source"] == "vorbis"
    assert tags["duration_sec"] == 201.5


def test_read_m4a_tags_uses_mp4_reader(tmp_path: Path, monkeypatch) -> None:
    audio_path = tmp_path / "Demo Artist - Demo Song.m4a"
    audio_path.write_bytes(b"placeholder")

    def fake_read_mp4(path: Path) -> tuple[dict[str, str], bool, float | None, str]:
        assert path == audio_path
        return (
            {
                "title": "Demo Song",
                "artist": "Demo Artist",
                "album": "Demo Album",
                "album_artist": "Demo Artist",
                "track": "2",
                "year": "2021",
                "genre": "Pop",
                "comment": "source-id",
            },
            True,
            180.0,
            "mp4",
        )

    monkeypatch.setattr(audio_tags, "_read_mp4_tags", fake_read_mp4)
    tags = read_audio_tags(audio_path)
    assert tags["title"] == "Demo Song"
    assert tags["artist"] == "Demo Artist"
    assert tags["has_cover"] is True
    assert tags["tag_source"] == "mp4"


def test_inventory_record_uses_filename_fallback(tmp_path: Path) -> None:
    audio_path = tmp_path / "Fallback Artist - Fallback Title.mp3"
    write_id3_mp3(audio_path)

    record = inventory_record("CloudMusic", tmp_path, audio_path)
    assert record.title == "Fallback Title"
    assert record.artist == "Fallback Artist"
    assert record.has_tag_title == "false"
    assert record.has_tag_artist == "false"
    assert record.title_key == normalize_key("Fallback Title")
    assert record.library == "CloudMusic"
    assert record.relative_path == audio_path.name


def test_iter_audio_files_skips_non_audio(tmp_path: Path) -> None:
    library = tmp_path / "CloudMusic"
    library.mkdir()
    write_id3_mp3(library / "Artist - Song.mp3", title="Song", artist="Artist")
    (library / "notes.lrc").write_text("skip me", encoding="utf-8")
    (library / "cover.jpg").write_bytes(b"skip")

    files = list(iter_audio_files([library]))
    assert len(files) == 1
    assert files[0][1].name == "Artist - Song.mp3"


def test_read_tags_command_writes_inventory_csv(tmp_path: Path) -> None:
    library = tmp_path / "CloudMusic"
    library.mkdir()
    write_id3_mp3(library / "Artist A - Song A.mp3", title="Song A", artist="Artist A")
    write_id3_mp3(library / "Artist B - Song B.mp3", title="Song B", artist="Artist B", with_cover=True)

    output_path = tmp_path / "inventory.csv"
    args = type(
        "Args",
        (),
        {
            "roots": [library],
            "output": output_path,
        },
    )()
    exit_code = command_read_tags(args)

    assert exit_code == 0
    assert output_path.exists()
    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert set(rows[0].keys()) == set(INVENTORY_COLUMNS)
    assert {row["title"] for row in rows} == {"Song A", "Song B"}
    assert all(row["library"] == "CloudMusic" for row in rows)
