from __future__ import annotations

import csv
from argparse import Namespace
from pathlib import Path

from mutagen.id3 import ID3, TIT2, TPE1

from scripts.metadata_resync import (
    build_parser,
    command_apply_cloudmusic_resync,
    command_apply_youtube_album,
    command_convert_tidal_alac,
    command_plan_youtube_album,
    mp4_cover_format,
    valid_album,
    write_mp3_tags,
)


def test_parser_has_plan_commands() -> None:
    parser = build_parser()

    args = parser.parse_args(["plan-youtube-albums", "--output", "plan.csv"])
    assert args.command == "plan-youtube-albums"
    assert args.output == Path("plan.csv")

    convert_args = parser.parse_args(["plan-tidal-alac", "--output", "convert.csv"])
    assert convert_args.command == "plan-tidal-alac"
    assert convert_args.output == Path("convert.csv")


def test_valid_album_rejects_placeholder() -> None:
    assert valid_album("Real Album") is True
    assert valid_album("Online Media Skill YouTube Sources") is False
    assert valid_album("") is False


def test_write_mp3_tags_updates_album(tmp_path: Path) -> None:
    path = tmp_path / "Artist - Song.mp3"
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Song"))
    tags.add(TPE1(encoding=3, text="Artist"))
    tags.save(path)

    write_mp3_tags(path, title="Song", artist="Artist", album="Real Album", album_artist="Artist", year="2020")

    written = ID3(path)
    assert written["TALB"].text == ["Real Album"]
    assert written["TPE2"].text == ["Artist"]
    assert str(written["TDRC"].text[0]) == "2020"


def test_write_mp3_tags_refuses_missing_target(tmp_path: Path) -> None:
    missing = tmp_path / "Missing Artist - Missing Song.mp3"

    try:
        write_mp3_tags(missing, title="Missing Song", artist="Missing Artist", album="Missing Album")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing target should raise FileNotFoundError")

    assert not missing.exists()


def test_plan_youtube_album_uses_album_map(tmp_path: Path) -> None:
    audio_path = tmp_path / "Artist - Song.mp3"
    audio_path.write_bytes(b"")
    write_mp3_tags(audio_path, title="Song", artist="Artist", album="Online Media Skill YouTube Sources")
    candidates = tmp_path / "candidates.csv"
    album_map = tmp_path / "album_map.csv"
    output = tmp_path / "plan.csv"

    with candidates.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target_path", "title", "artist", "current_album", "release_year"])
        writer.writeheader()
        writer.writerow(
            {
                "target_path": str(audio_path),
                "title": "Song",
                "artist": "Artist",
                "current_album": "Online Media Skill YouTube Sources",
                "release_year": "2020",
            }
        )
    with album_map.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target_path", "album", "album_artist", "year", "evidence_url", "confidence"])
        writer.writeheader()
        writer.writerow(
            {
                "target_path": str(audio_path),
                "album": "Real Album",
                "album_artist": "Artist",
                "year": "2020",
                "evidence_url": "https://example.com/album",
                "confidence": "high",
            }
        )

    args = Namespace(candidates=candidates, album_map=album_map, output=output)
    exit_code = command_plan_youtube_album(args)

    assert exit_code == 0
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "ready"
    assert rows[0]["new_album"] == "Real Album"


def test_plan_youtube_album_allows_researched_title_artist(tmp_path: Path) -> None:
    audio_path = tmp_path / "Unknown - Wrong.mp3"
    audio_path.write_bytes(b"")
    write_mp3_tags(audio_path, title="Wrong", artist="Unknown", album="Online Media Skill YouTube Sources")
    candidates = tmp_path / "candidates.csv"
    album_map = tmp_path / "album_map.csv"
    output = tmp_path / "plan.csv"

    with candidates.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target_path", "title", "artist", "current_album", "release_year"])
        writer.writeheader()
        writer.writerow(
            {
                "target_path": str(audio_path),
                "title": "Wrong",
                "artist": "Unknown",
                "current_album": "Online Media Skill YouTube Sources",
                "release_year": "",
            }
        )
    with album_map.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target_path", "title", "artist", "album", "album_artist", "year", "evidence_url", "confidence"])
        writer.writeheader()
        writer.writerow(
            {
                "target_path": str(audio_path),
                "title": "Correct Song",
                "artist": "Correct Artist",
                "album": "Correct Album",
                "album_artist": "Correct Artist",
                "year": "2024",
                "evidence_url": "https://example.com/correct",
                "confidence": "high",
            }
        )

    args = Namespace(candidates=candidates, album_map=album_map, output=output)
    exit_code = command_plan_youtube_album(args)

    assert exit_code == 0
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["title"] == "Correct Song"
    assert rows[0]["artist"] == "Correct Artist"
    assert rows[0]["album_artist"] == "Correct Artist"


def test_plan_youtube_album_marks_existing_album_ok(tmp_path: Path) -> None:
    audio_path = tmp_path / "Artist - Song.mp3"
    audio_path.write_bytes(b"")
    write_mp3_tags(audio_path, title="Song", artist="Artist", album="Existing Album")
    candidates = tmp_path / "candidates.csv"
    output = tmp_path / "plan.csv"

    with candidates.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target_path", "title", "artist", "current_album", "release_year"])
        writer.writeheader()
        writer.writerow(
            {
                "target_path": str(audio_path),
                "title": "Song",
                "artist": "Artist",
                "current_album": "Online Media Skill YouTube Sources",
                "release_year": "2020",
            }
        )

    args = Namespace(candidates=candidates, album_map=None, output=output)
    exit_code = command_plan_youtube_album(args)

    assert exit_code == 0
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "already_ok"
    assert rows[0]["message"] == "album already valid"


def test_apply_youtube_album_rejects_stale_plan_album(tmp_path: Path) -> None:
    audio_path = tmp_path / "Artist - Song.mp3"
    audio_path.write_bytes(b"")
    write_mp3_tags(audio_path, title="Song", artist="Artist", album="Actual Album")
    plan = tmp_path / "plan.csv"
    output = tmp_path / "apply_log.csv"

    with plan.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "target_path",
                "title",
                "artist",
                "current_album",
                "new_album",
                "album_artist",
                "year",
                "evidence_url",
                "confidence",
                "status",
                "message",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "target_path": str(audio_path),
                "title": "Song",
                "artist": "Artist",
                "current_album": "Online Media Skill YouTube Sources",
                "new_album": "New Album",
                "album_artist": "Artist",
                "year": "2020",
                "evidence_url": "https://example.com/album",
                "confidence": "high",
                "status": "ready",
                "message": "album ready",
            }
        )

    exit_code = command_apply_youtube_album(Namespace(plan=plan, output=output, dry_run=False))

    assert exit_code == 1
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "error"
    assert "current album mismatch" in rows[0]["message"]
    assert ID3(audio_path)["TALB"].text == ["Actual Album"]


def test_apply_youtube_album_rejects_blank_current_album(tmp_path: Path) -> None:
    audio_path = tmp_path / "Artist - Song.mp3"
    audio_path.write_bytes(b"")
    write_mp3_tags(audio_path, title="Song", artist="Artist", album="Online Media Skill YouTube Sources")
    plan = tmp_path / "plan.csv"
    output = tmp_path / "apply_log.csv"

    with plan.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "target_path",
                "title",
                "artist",
                "current_album",
                "new_album",
                "album_artist",
                "year",
                "evidence_url",
                "confidence",
                "status",
                "message",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "target_path": str(audio_path),
                "title": "Song",
                "artist": "Artist",
                "current_album": "",
                "new_album": "New Album",
                "album_artist": "Artist",
                "year": "2020",
                "evidence_url": "https://example.com/album",
                "confidence": "high",
                "status": "ready",
                "message": "album ready",
            }
        )

    exit_code = command_apply_youtube_album(Namespace(plan=plan, output=output, dry_run=False))

    assert exit_code == 1
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "error"
    assert rows[0]["message"] == "current album missing in plan"
    assert ID3(audio_path)["TALB"].text == ["Online Media Skill YouTube Sources"]


def test_convert_tidal_alac_rejects_existing_output(tmp_path: Path) -> None:
    source_root = tmp_path / "tidal"
    output_root = tmp_path / "m4a"
    source_root.mkdir()
    output_root.mkdir()
    source = source_root / "Source.flac"
    destination = output_root / "Source.m4a"
    source.write_bytes(b"placeholder flac")
    destination.write_bytes(b"existing m4a")
    plan = tmp_path / "convert_plan.csv"
    output = tmp_path / "convert_log.csv"

    with plan.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_path", "output_path", "title", "artist", "album", "album_artist", "track", "year", "has_cover", "status", "message"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "source_path": str(source),
                "output_path": str(destination),
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "album_artist": "Artist",
                "track": "1",
                "year": "2020",
                "has_cover": "true",
                "status": "ready",
                "message": "ready for ALAC conversion",
            }
        )

    exit_code = command_convert_tidal_alac(
        Namespace(plan=plan, output=output, source_root=source_root, output_root=output_root, ffmpeg="false", dry_run=False)
    )

    assert exit_code == 1
    assert destination.read_bytes() == b"existing m4a"
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "error"
    assert "output already exists" in rows[0]["message"]


def test_apply_cloudmusic_resync_rejects_missing_matching_flac(tmp_path: Path) -> None:
    source_root = tmp_path / "import_ready"
    cloudmusic_dir = tmp_path / "CloudMusic"
    source_root.mkdir()
    source = source_root / "Source.m4a"
    target = cloudmusic_dir / "Source.m4a"
    source.write_bytes(b"placeholder m4a")
    plan = tmp_path / "resync_plan.csv"
    output = tmp_path / "resync_log.csv"

    with plan.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_path", "target_path", "action", "status", "message"])
        writer.writeheader()
        writer.writerow(
            {
                "source_path": str(source),
                "target_path": str(target),
                "action": "replace_flac_with_m4a",
                "status": "ready",
                "message": "planned",
            }
        )

    exit_code = command_apply_cloudmusic_resync(Namespace(plan=plan, output=output, source_root=source_root, cloudmusic_dir=cloudmusic_dir, dry_run=False))

    assert exit_code == 1
    assert not target.exists()
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "error"
    assert "matching flac missing" in rows[0]["message"]


def test_apply_cloudmusic_resync_rejects_copy_when_flac_exists(tmp_path: Path) -> None:
    source_root = tmp_path / "import_ready"
    cloudmusic_dir = tmp_path / "CloudMusic"
    source_root.mkdir()
    cloudmusic_dir.mkdir()
    source = source_root / "Source.m4a"
    target = cloudmusic_dir / "Source.m4a"
    flac_target = cloudmusic_dir / "Source.flac"
    source.write_bytes(b"placeholder m4a")
    flac_target.write_bytes(b"existing flac")
    plan = tmp_path / "resync_plan.csv"
    output = tmp_path / "resync_log.csv"

    with plan.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_path", "target_path", "action", "status", "message"])
        writer.writeheader()
        writer.writerow(
            {
                "source_path": str(source),
                "target_path": str(target),
                "action": "copy_m4a",
                "status": "ready",
                "message": "planned",
            }
        )

    exit_code = command_apply_cloudmusic_resync(Namespace(plan=plan, output=output, source_root=source_root, cloudmusic_dir=cloudmusic_dir, dry_run=False))

    assert exit_code == 1
    assert not target.exists()
    assert flac_target.exists()
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "error"
    assert "stale action" in rows[0]["message"]


def test_apply_cloudmusic_resync_rejects_outside_target_root(tmp_path: Path) -> None:
    source_root = tmp_path / "import_ready"
    cloudmusic_dir = tmp_path / "CloudMusic"
    outside_dir = tmp_path / "Outside"
    source_root.mkdir()
    cloudmusic_dir.mkdir()
    outside_dir.mkdir()
    source = source_root / "Source.m4a"
    target = outside_dir / "Source.m4a"
    source.write_bytes(b"placeholder m4a")
    plan = tmp_path / "resync_plan.csv"
    output = tmp_path / "resync_log.csv"

    with plan.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_path", "target_path", "action", "status", "message"])
        writer.writeheader()
        writer.writerow(
            {
                "source_path": str(source),
                "target_path": str(target),
                "action": "copy_m4a",
                "status": "ready",
                "message": "planned",
            }
        )

    exit_code = command_apply_cloudmusic_resync(Namespace(plan=plan, output=output, source_root=source_root, cloudmusic_dir=cloudmusic_dir, dry_run=False))

    assert exit_code == 1
    assert not target.exists()
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "error"
    assert "target outside CloudMusic root" in rows[0]["message"]


def test_mp4_cover_format() -> None:
    assert mp4_cover_format("image/png") == 14
    assert mp4_cover_format("image/jpeg") == 13
