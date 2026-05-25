#!/usr/bin/env python3
"""Repair music metadata and prepare Apple Music compatible imports."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import cast

from mutagen import MutagenError
from mutagen.flac import FLAC
from mutagen.id3 import COMM, ID3, TALB, TDRC, TIT2, TPE1, TPE2, TRCK, error as ID3Error
from mutagen.mp4 import MP4, MP4Cover

from scripts.audio_tags import read_audio_tags

PLACEHOLDER_ALBUMS = {"Online Media Skill YouTube Sources"}
YOUTUBE_REPAIR_COLUMNS = [
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
]
CONVERT_PLAN_COLUMNS = [
    "source_path",
    "output_path",
    "title",
    "artist",
    "album",
    "album_artist",
    "track",
    "year",
    "has_cover",
    "status",
    "message",
]
RESYNC_PLAN_COLUMNS = [
    "source_path",
    "target_path",
    "action",
    "status",
    "message",
]


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def ensure_id3(path: Path) -> ID3:
    if not path.exists():
        raise FileNotFoundError(f"MP3 target does not exist: {path}")
    try:
        return ID3(path)
    except (ID3Error, MutagenError):
        tags = ID3()
        tags.save(path)
        return ID3(path)


def write_mp3_tags(
    path: Path,
    *,
    title: str = "",
    artist: str = "",
    album: str = "",
    album_artist: str = "",
    track: str = "",
    year: str = "",
    comment: str = "",
) -> None:
    tags = ensure_id3(path)
    if title:
        tags.setall("TIT2", [TIT2(encoding=3, text=title)])
    if artist:
        tags.setall("TPE1", [TPE1(encoding=3, text=artist)])
    if album:
        tags.setall("TALB", [TALB(encoding=3, text=album)])
    if album_artist:
        tags.setall("TPE2", [TPE2(encoding=3, text=album_artist)])
    if track:
        tags.setall("TRCK", [TRCK(encoding=3, text=track)])
    if year:
        tags.setall("TDRC", [TDRC(encoding=3, text=year[:10])])
    if comment:
        tags.setall("COMM::eng", [COMM(encoding=3, lang="eng", desc="", text=comment)])
    tags.save(path)


def extract_flac_cover(path: Path) -> tuple[bytes, str] | None:
    audio = FLAC(path)
    if not audio.pictures:
        return None
    picture = audio.pictures[0]
    mime = picture.mime or "image/jpeg"
    return picture.data, mime


def mp4_cover_format(mime: str) -> int:
    return MP4Cover.FORMAT_PNG if "png" in mime.lower() else MP4Cover.FORMAT_JPEG


def write_m4a_tags(
    path: Path,
    *,
    title: str = "",
    artist: str = "",
    album: str = "",
    album_artist: str = "",
    track: str = "",
    year: str = "",
    genre: str = "",
    comment: str = "",
    cover: tuple[bytes, str] | None = None,
) -> None:
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    if title:
        audio["\xa9nam"] = [title]
    if artist:
        audio["\xa9ART"] = [artist]
    if album:
        audio["\xa9alb"] = [album]
    if album_artist:
        audio["aART"] = [album_artist]
    if track:
        first = track.split("/")[0].strip()
        if first.isdigit():
            audio["trkn"] = [(int(first), 0)]
    if year:
        audio["\xa9day"] = [year[:10]]
    if genre:
        audio["\xa9gen"] = [genre]
    if comment:
        audio["\xa9cmt"] = [comment]
    if cover is not None:
        data, mime = cover
        audio["covr"] = [MP4Cover(data, imageformat=mp4_cover_format(mime))]
    audio.save()


def valid_album(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and stripped not in PLACEHOLDER_ALBUMS


def under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def validate_youtube_repair_row(row: dict[str, str]) -> str:
    target = Path(row.get("target_path", ""))
    if not target.exists():
        return f"target missing: {target}"
    if not target.is_file():
        return f"target is not a file: {target}"
    if target.suffix.lower() != ".mp3":
        return f"target is not an mp3: {target}"
    if not valid_album(row.get("new_album", "")):
        return "new album is missing or still a workflow placeholder"

    planned_album = row.get("current_album", "")
    if not planned_album:
        return "current album missing in plan"
    actual_album = str(read_audio_tags(target).get("album") or "")
    if planned_album and actual_album != planned_album:
        return f"current album mismatch: planned={planned_album!r} actual={actual_album!r}"
    return ""


def cloudmusic_import_name(path: Path) -> str:
    return re.sub(r"^\d+\.\s+", "", path.name)


def cloudmusic_action_for_target(target: Path) -> str:
    if target.exists():
        return "skip_existing_m4a"
    if target.with_suffix(".flac").exists():
        return "replace_flac_with_m4a"
    return "copy_m4a"


def validate_tidal_convert_row(row: dict[str, str], source_root: Path, output_root: Path) -> str:
    if row.get("status") != "ready":
        return "row is not ready"
    source = Path(row.get("source_path", ""))
    destination = Path(row.get("output_path", ""))
    if not source.exists() or not source.is_file():
        return f"source missing: {source}"
    if source.suffix.lower() != ".flac":
        return f"source is not a flac: {source}"
    if not under_root(source, source_root):
        return f"source outside allowed root: {source}"
    if destination.suffix.lower() != ".m4a":
        return f"output is not an m4a: {destination}"
    if not under_root(destination, output_root):
        return f"output outside allowed root: {destination}"
    if destination.exists():
        return f"output already exists: {destination}"
    return ""


def validate_cloudmusic_resync_row(row: dict[str, str], source_root: Path, cloudmusic_root: Path) -> str:
    source = Path(row.get("source_path", ""))
    target = Path(row.get("target_path", ""))
    action = row.get("action", "")
    if row.get("status") != "ready":
        return "row is not ready"
    if action not in {"skip_existing_m4a", "replace_flac_with_m4a", "copy_m4a"}:
        return f"unsupported action: {action}"
    if not source.exists() or not source.is_file():
        return f"source missing: {source}"
    if source.suffix.lower() != ".m4a":
        return f"source is not an m4a: {source}"
    if not under_root(source, source_root):
        return f"source outside allowed root: {source}"
    if target.suffix.lower() != ".m4a":
        return f"target is not an m4a: {target}"
    if not under_root(target, cloudmusic_root):
        return f"target outside CloudMusic root: {target}"

    flac_target = target.with_suffix(".flac")
    if action == "replace_flac_with_m4a" and (not flac_target.exists() or not flac_target.is_file()):
        return f"matching flac missing for replace action: {flac_target}"
    expected_action = cloudmusic_action_for_target(target)
    if action != expected_action:
        return f"stale action: planned={action} actual={expected_action}"
    if action == "skip_existing_m4a" and not target.exists():
        return f"target m4a missing for skip action: {target}"
    if action == "skip_existing_m4a" and not target.is_file():
        return f"target m4a is not a file: {target}"
    if action in {"replace_flac_with_m4a", "copy_m4a"} and target.exists():
        return f"target m4a already exists: {target}"
    return ""


def command_plan_youtube_album(args: argparse.Namespace) -> int:
    candidates = read_csv(cast(Path, args.candidates))
    album_map_rows = read_csv(cast(Path, args.album_map)) if cast(Path | None, args.album_map) else []
    output = cast(Path, args.output)
    album_by_path = {row["target_path"]: row for row in album_map_rows if row.get("target_path")}
    rows: list[dict[str, str]] = []
    for row in candidates:
        target = Path(row["target_path"])
        tags = read_audio_tags(target)
        current_album = str(tags.get("album") or row.get("current_album") or "")
        mapped = album_by_path.get(row["target_path"], {})
        title = mapped.get("title") or row.get("title", str(tags.get("title") or ""))
        artist = mapped.get("artist") or row.get("artist", str(tags.get("artist") or ""))
        new_album = mapped.get("album", "").strip()
        if current_album in PLACEHOLDER_ALBUMS:
            status = "ready" if valid_album(new_album) else "needs_album"
            message = "album ready" if status == "ready" else "missing researched album"
        else:
            status = "already_ok" if valid_album(current_album) else "needs_album"
            message = "album already valid" if status == "already_ok" else "missing current album"
        rows.append(
            {
                "target_path": row["target_path"],
                "title": title,
                "artist": artist,
                "current_album": current_album,
                "new_album": new_album,
                "album_artist": mapped.get("album_artist") or artist,
                "year": mapped.get("year", "") or row.get("release_year", ""),
                "evidence_url": mapped.get("evidence_url", ""),
                "confidence": mapped.get("confidence", ""),
                "status": status,
                "message": message,
            }
        )
    write_csv(output, YOUTUBE_REPAIR_COLUMNS, rows)
    print(f"rows={len(rows)}")
    print(f"ready={sum(1 for row in rows if row['status'] == 'ready')}")
    print(f"already_ok={sum(1 for row in rows if row['status'] == 'already_ok')}")
    print(f"needs_album={sum(1 for row in rows if row['status'] == 'needs_album')}")
    print(f"plan_csv={output}")
    return 0


def command_apply_youtube_album(args: argparse.Namespace) -> int:
    plan_path = cast(Path, args.plan)
    output = cast(Path, args.output)
    dry_run = cast(bool, args.dry_run)
    rows_out: list[dict[str, str]] = []
    for row in read_csv(plan_path):
        message = row.get("message", "")
        if row.get("status") != "ready":
            rows_out.append({**row, "status": "skipped", "message": message or "not ready"})
            continue
        path = Path(row["target_path"])
        validation_error = validate_youtube_repair_row(row)
        if validation_error:
            rows_out.append({**row, "status": "error", "message": validation_error})
            continue
        if dry_run:
            rows_out.append({**row, "status": "would_update", "message": "dry run"})
            continue
        write_mp3_tags(
            path,
            title=row.get("title", ""),
            artist=row.get("artist", ""),
            album=row.get("new_album", ""),
            album_artist=row.get("album_artist", ""),
            year=row.get("year", ""),
            comment=f"album evidence: {row.get('evidence_url', '')}".strip(),
        )
        after = read_audio_tags(path)
        if str(after.get("album") or "") == row.get("new_album", ""):
            rows_out.append({**row, "status": "updated", "message": "album tag updated"})
        else:
            rows_out.append({**row, "status": "error", "message": "post-write album mismatch"})
    write_csv(output, YOUTUBE_REPAIR_COLUMNS, rows_out)
    print(f"rows={len(rows_out)}")
    print(f"updated={sum(1 for row in rows_out if row['status'] == 'updated')}")
    print(f"would_update={sum(1 for row in rows_out if row['status'] == 'would_update')}")
    print(f"log_csv={output}")
    return 1 if any(row["status"] == "error" for row in rows_out) else 0


def command_plan_tidal_alac(args: argparse.Namespace) -> int:
    library_dir = cast(Path, args.library_dir)
    output_dir = cast(Path, args.output_dir)
    output = cast(Path, args.output)
    rows: list[dict[str, str]] = []
    for source in sorted(library_dir.rglob("*.flac")):
        tags = read_audio_tags(source)
        destination = output_dir / f"{source.stem}.m4a"
        title = str(tags.get("title") or "")
        artist = str(tags.get("artist") or "")
        album = str(tags.get("album") or "")
        has_cover = str(tags.get("has_cover") is True).lower()
        ready = bool(title and artist and album and tags.get("has_cover") is True)
        rows.append(
            {
                "source_path": str(source),
                "output_path": str(destination),
                "title": title,
                "artist": artist,
                "album": album,
                "album_artist": str(tags.get("album_artist") or artist),
                "track": str(tags.get("track") or ""),
                "year": str(tags.get("year") or ""),
                "has_cover": has_cover,
                "status": "ready" if ready else "missing_metadata",
                "message": "ready for ALAC conversion" if ready else "missing title/artist/album/artwork",
            }
        )
    write_csv(output, CONVERT_PLAN_COLUMNS, rows)
    print(f"rows={len(rows)}")
    print(f"ready={sum(1 for row in rows if row['status'] == 'ready')}")
    print(f"missing_metadata={sum(1 for row in rows if row['status'] != 'ready')}")
    print(f"plan_csv={output}")
    return 0


def convert_flac_to_alac(source: Path, destination: Path, ffmpeg: str) -> subprocess.CompletedProcess[str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-i", str(source), "-map", "0:a", "-map", "0:v?", "-c:a", "alac", "-c:v", "copy", str(destination)]
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def command_convert_tidal_alac(args: argparse.Namespace) -> int:
    plan = cast(Path, args.plan)
    output = cast(Path, args.output)
    source_root = cast(Path, args.source_root)
    output_root = cast(Path, args.output_root)
    ffmpeg = cast(str, args.ffmpeg)
    dry_run = cast(bool, args.dry_run)
    rows_out: list[dict[str, str]] = []
    for row in read_csv(plan):
        validation_error = validate_tidal_convert_row(row, source_root, output_root)
        if validation_error:
            rows_out.append({**row, "status": "error" if row.get("status") == "ready" else "skipped", "message": validation_error})
            continue
        source = Path(row["source_path"])
        destination = Path(row["output_path"])
        if dry_run:
            rows_out.append({**row, "status": "would_convert", "message": "dry run"})
            continue
        proc = convert_flac_to_alac(source, destination, ffmpeg)
        if proc.returncode != 0:
            rows_out.append({**row, "status": "error", "message": proc.stdout[-500:]})
            continue
        source_tags = read_audio_tags(source)
        write_m4a_tags(
            destination,
            title=str(source_tags.get("title") or row.get("title") or ""),
            artist=str(source_tags.get("artist") or row.get("artist") or ""),
            album=str(source_tags.get("album") or row.get("album") or ""),
            album_artist=str(source_tags.get("album_artist") or row.get("album_artist") or row.get("artist") or ""),
            track=str(source_tags.get("track") or row.get("track") or ""),
            year=str(source_tags.get("year") or row.get("year") or ""),
            genre=str(source_tags.get("genre") or ""),
            comment=str(source_tags.get("comment") or f"converted from {source.name}"),
            cover=extract_flac_cover(source),
        )
        after = read_audio_tags(destination)
        ok = bool(after.get("title") and after.get("artist") and after.get("album") and after.get("has_cover") is True)
        rows_out.append({**row, "status": "converted" if ok else "error", "message": "converted to ALAC M4A" if ok else "post-conversion metadata incomplete"})
    write_csv(output, CONVERT_PLAN_COLUMNS, rows_out)
    print(f"rows={len(rows_out)}")
    print(f"converted={sum(1 for row in rows_out if row['status'] == 'converted')}")
    print(f"would_convert={sum(1 for row in rows_out if row['status'] == 'would_convert')}")
    print(f"log_csv={output}")
    return 1 if any(row["status"] == "error" for row in rows_out) else 0


def command_plan_cloudmusic_resync(args: argparse.Namespace) -> int:
    convert_log = cast(Path, args.convert_log)
    cloudmusic_dir = cast(Path, args.cloudmusic_dir)
    output = cast(Path, args.output)
    rows: list[dict[str, str]] = []
    for row in read_csv(convert_log):
        if row.get("status") not in {"converted", "ready"}:
            continue
        source = Path(row["output_path"])
        target = cloudmusic_dir / cloudmusic_import_name(source)
        flac_target = cloudmusic_dir / f"{Path(target).stem}.flac"
        if target.exists():
            action = "skip_existing_m4a"
        elif flac_target.exists():
            action = "replace_flac_with_m4a"
        else:
            action = "copy_m4a"
        rows.append({"source_path": str(source), "target_path": str(target), "action": action, "status": "ready", "message": "planned"})
    write_csv(output, RESYNC_PLAN_COLUMNS, rows)
    print(f"rows={len(rows)}")
    print(f"replace_flac_with_m4a={sum(1 for row in rows if row['action'] == 'replace_flac_with_m4a')}")
    print(f"copy_m4a={sum(1 for row in rows if row['action'] == 'copy_m4a')}")
    print(f"skip_existing_m4a={sum(1 for row in rows if row['action'] == 'skip_existing_m4a')}")
    print(f"plan_csv={output}")
    return 0


def command_apply_cloudmusic_resync(args: argparse.Namespace) -> int:
    plan = cast(Path, args.plan)
    output = cast(Path, args.output)
    source_root = cast(Path, args.source_root)
    cloudmusic_root = cast(Path, args.cloudmusic_dir)
    dry_run = cast(bool, args.dry_run)
    rows_out: list[dict[str, str]] = []
    for row in read_csv(plan):
        source = Path(row["source_path"])
        target = Path(row["target_path"])
        flac_target = target.with_suffix(".flac")
        action = row["action"]
        validation_error = validate_cloudmusic_resync_row(row, source_root, cloudmusic_root)
        if validation_error:
            rows_out.append({**row, "status": "error" if row.get("status") == "ready" else "skipped", "message": validation_error})
            continue
        if dry_run:
            rows_out.append({**row, "status": "would_apply", "message": "dry run"})
            continue
        if action == "skip_existing_m4a":
            rows_out.append({**row, "status": "skipped", "message": "target m4a already exists"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if action == "replace_flac_with_m4a" and flac_target.exists():
            flac_target.unlink()
        rows_out.append({**row, "status": "applied", "message": "copied m4a and removed matching flac when present"})
    write_csv(output, RESYNC_PLAN_COLUMNS, rows_out)
    print(f"rows={len(rows_out)}")
    print(f"applied={sum(1 for row in rows_out if row['status'] == 'applied')}")
    print(f"would_apply={sum(1 for row in rows_out if row['status'] == 'would_apply')}")
    print(f"log_csv={output}")
    return 1 if any(row["status"] == "error" for row in rows_out) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_youtube_plan = sub.add_parser("plan-youtube-albums", help="Plan MP3 album tag repairs from a researched album map")
    _ = p_youtube_plan.add_argument("--candidates", type=Path, default=Path("source_identification/youtube_album_tag_repair_candidates.csv"))
    _ = p_youtube_plan.add_argument("--album-map", type=Path)
    _ = p_youtube_plan.add_argument("--output", type=Path, default=Path("source_identification/youtube_album_repair_plan.csv"))
    p_youtube_plan.set_defaults(func=command_plan_youtube_album)

    p_youtube_apply = sub.add_parser("apply-youtube-albums", help="Apply a planned MP3 album tag repair")
    _ = p_youtube_apply.add_argument("--plan", type=Path, default=Path("source_identification/youtube_album_repair_plan.csv"))
    _ = p_youtube_apply.add_argument("--output", type=Path, default=Path("source_identification/youtube_album_repair_apply_log.csv"))
    _ = p_youtube_apply.add_argument("--apply", action="store_true", help="Write tags; omit for dry-run")
    p_youtube_apply.set_defaults(func=command_apply_youtube_album)

    p_tidal_plan = sub.add_parser("plan-tidal-alac", help="Plan Tidal FLAC to ALAC M4A conversion")
    _ = p_tidal_plan.add_argument("--library-dir", type=Path, default=Path("library/tidal"))
    _ = p_tidal_plan.add_argument("--output-dir", type=Path, default=Path("library/import_ready/tidal_m4a"))
    _ = p_tidal_plan.add_argument("--output", type=Path, default=Path("source_identification/tidal_alac_convert_plan.csv"))
    p_tidal_plan.set_defaults(func=command_plan_tidal_alac)

    p_tidal_convert = sub.add_parser("convert-tidal-alac", help="Convert planned FLAC files to ALAC M4A")
    _ = p_tidal_convert.add_argument("--plan", type=Path, default=Path("source_identification/tidal_alac_convert_plan.csv"))
    _ = p_tidal_convert.add_argument("--output", type=Path, default=Path("source_identification/tidal_alac_convert_log.csv"))
    _ = p_tidal_convert.add_argument("--source-root", type=Path, default=Path("library/tidal"))
    _ = p_tidal_convert.add_argument("--output-root", type=Path, default=Path("library/import_ready/tidal_m4a"))
    _ = p_tidal_convert.add_argument("--ffmpeg", default="ffmpeg")
    _ = p_tidal_convert.add_argument("--apply", action="store_true", help="Run ffmpeg; omit for dry-run")
    p_tidal_convert.set_defaults(func=command_convert_tidal_alac)

    p_resync_plan = sub.add_parser("plan-cloudmusic-resync", help="Plan CloudMusic replacement of FLAC files with M4A files")
    _ = p_resync_plan.add_argument("--convert-log", type=Path, default=Path("source_identification/tidal_alac_convert_log.csv"))
    _ = p_resync_plan.add_argument("--cloudmusic-dir", type=Path, default=Path.home() / "Music" / "CloudMusic")
    _ = p_resync_plan.add_argument("--output", type=Path, default=Path("source_identification/cloudmusic_m4a_resync_plan.csv"))
    p_resync_plan.set_defaults(func=command_plan_cloudmusic_resync)

    p_resync_apply = sub.add_parser("apply-cloudmusic-resync", help="Apply planned CloudMusic M4A resync")
    _ = p_resync_apply.add_argument("--plan", type=Path, default=Path("source_identification/cloudmusic_m4a_resync_plan.csv"))
    _ = p_resync_apply.add_argument("--output", type=Path, default=Path("source_identification/cloudmusic_m4a_resync_log.csv"))
    _ = p_resync_apply.add_argument("--source-root", type=Path, default=Path("library/import_ready/tidal_m4a"))
    _ = p_resync_apply.add_argument("--cloudmusic-dir", type=Path, default=Path.home() / "Music" / "CloudMusic")
    _ = p_resync_apply.add_argument("--apply", action="store_true", help="Copy M4A files and remove matching FLAC files; omit for dry-run")
    p_resync_apply.set_defaults(func=command_apply_cloudmusic_resync)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "apply"):
        args.dry_run = not cast(bool, args.apply)
    func = cast(object, getattr(args, "func"))
    if not callable(func):
        raise TypeError("parsed command is not callable")
    return cast(int, func(args))


if __name__ == "__main__":
    raise SystemExit(main())
