#!/usr/bin/env python3
"""Prepare and download Tidal candidates from a reviewed source-song CSV.

The workflow is intentionally three-stage:
1. `search-candidates` calls streamrip search and writes candidate rows.
2. An AI or human reviews candidates and marks `decision=approved`.
3. `download-approved` downloads only approved Tidal track IDs.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4


DEFAULT_INPUT = Path("source_identification/medley_sources_download_queue.csv")
DEFAULT_CANDIDATES = Path("source_identification/tidal_candidates.csv")
DEFAULT_DOWNLOAD_DIR = Path("library/tidal")
DEFAULT_CACHE_DIR = Path("source_identification/tidal_search_cache")
DEFAULT_LOG = Path("source_identification/tidal_download_log.csv")
CANDIDATE_COLUMNS = [
    "source_order",
    "song_title",
    "artist",
    "query",
    "candidate_rank",
    "tidal_id",
    "tidal_desc",
    "desc_title",
    "desc_artist",
    "title_match",
    "artist_match",
    "mechanical_score",
    "decision",
    "review_notes",
]
LOG_COLUMNS = ["source_order", "song_title", "artist", "status", "tidal_id", "tidal_desc", "message"]
TAG_REPORT_COLUMNS = ["path", "extension", "has_title", "has_artist", "has_cover", "status"]


class Id3Tags(Protocol):
    def get(self, key: str, default: object | None = None) -> object | None: ...

    def getall(self, key: str) -> list[object]: ...


def normalize(value: str) -> str:
    return re.sub(r"[\s\-—_·・（）()《》〈〉\[\]【】,，.。!！?？:：;；\"'’“”&＋+]+", "", value).casefold()


def artist_match_keys(artist: str) -> list[str]:
    parts = re.split(r"\s+(?:feat\.?|ft\.?|featuring)\s+|[,，/&、]|\band\b", artist, flags=re.IGNORECASE)
    keys = [normalize(artist)]
    for part in parts:
        key = normalize(part)
        if key and key not in keys:
            keys.append(key)
    return keys


def desc_title_artist(desc: str) -> tuple[str, str]:
    if " by " not in desc:
        return desc, ""
    title, artist = desc.rsplit(" by ", 1)
    return title, artist


def candidate_score(song_title: str, artist: str, desc: str) -> tuple[bool, bool, int, str, str]:
    desc_title, desc_artist = desc_title_artist(desc)
    title_key = normalize(song_title)
    desc_title_key = normalize(desc_title)
    desc_artist_key = normalize(desc_artist)
    title_match = bool(title_key and title_key in desc_title_key)
    artist_match = any(key and key in desc_artist_key for key in artist_match_keys(artist))
    score = (70 if title_match else 0) + (30 if artist_match else 0)
    return title_match, artist_match, score, desc_title, desc_artist


def run_command(cmd: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=timeout)


def search_tidal(rip: Path, cache_dir: Path, order: str, artist: str, title: str, results: int) -> tuple[str, list[dict[str, str]]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = cache_dir / f"{int(order):04d}.json"
    query = f"{artist} {title}".strip()
    proc = run_command([str(rip), "search", "tidal", "track", query, "-n", str(results), "-o", str(output)], timeout=90)
    if proc.returncode != 0 or not output.exists():
        raise RuntimeError(proc.stdout.strip()[:1000])
    loaded = cast(object, json.loads(output.read_text(encoding="utf-8")))
    if not isinstance(loaded, list):
        raise RuntimeError("streamrip search output was not a list")
    items = cast(list[object], loaded)
    return query, [cast(dict[str, str], item) for item in items]


def write_rows(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_log(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LOG_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def command_search_candidates(args: argparse.Namespace) -> int:
    input_path = cast(Path, args.input)
    output_path = cast(Path, args.output)
    cache_dir = cast(Path, args.cache_dir)
    rip = cast(Path, args.rip)
    results = cast(int, args.results)
    limit = cast(int | None, args.limit)
    sleep_seconds = cast(float, args.sleep)
    rows_out: list[dict[str, str]] = []
    with input_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    attempted = 0
    for row in rows:
        if limit is not None and attempted >= limit:
            break
        order = row["order"]
        title = row["song_title"].strip()
        artist = row["artist"].strip()
        if not title or not artist:
            continue
        attempted += 1
        try:
            query, candidates = search_tidal(rip, cache_dir, order, artist, title, results)
            for rank, item in enumerate(candidates, 1):
                desc = str(item.get("desc", ""))
                title_match, artist_match, score, desc_title, desc_artist = candidate_score(title, artist, desc)
                rows_out.append(
                    {
                        "source_order": order,
                        "song_title": title,
                        "artist": artist,
                        "query": query,
                        "candidate_rank": str(rank),
                        "tidal_id": str(item.get("id", "")),
                        "tidal_desc": desc,
                        "desc_title": desc_title,
                        "desc_artist": desc_artist,
                        "title_match": "true" if title_match else "false",
                        "artist_match": "true" if artist_match else "false",
                        "mechanical_score": str(score),
                        "decision": "",
                        "review_notes": "",
                    }
                )
        except Exception as exc:
            rows_out.append(
                {
                    "source_order": order,
                    "song_title": title,
                    "artist": artist,
                    "query": f"{artist} {title}".strip(),
                    "candidate_rank": "",
                    "tidal_id": "",
                    "tidal_desc": "",
                    "desc_title": "",
                    "desc_artist": "",
                    "title_match": "false",
                    "artist_match": "false",
                    "mechanical_score": "0",
                    "decision": "search_error",
                    "review_notes": str(exc)[:1000],
                }
            )
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    write_rows(output_path, CANDIDATE_COLUMNS, rows_out)
    print(f"candidate_rows={len(rows_out)}")
    print(f"candidate_csv={output_path}")
    return 0


def download_tidal(rip: Path, download_dir: Path, tidal_id: str, quality: int) -> str:
    download_dir.mkdir(parents=True, exist_ok=True)
    proc = run_command(
        [str(rip), "--no-progress", "-ndb", "-f", str(download_dir), "-q", str(quality), "id", "tidal", "track", tidal_id],
        timeout=240,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout.strip()[:1000])
    return proc.stdout.strip()[-1000:]


def completed_ids(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    with log_path.open(newline="", encoding="utf-8") as fh:
        return {row["tidal_id"] for row in csv.DictReader(fh) if row.get("status") == "downloaded" and row.get("tidal_id")}


def command_download_approved(args: argparse.Namespace) -> int:
    candidates_path = cast(Path, args.candidates)
    download_dir = cast(Path, args.download_dir)
    log_path = cast(Path, args.log)
    rip = cast(Path, args.rip)
    quality = cast(int, args.quality)
    limit = cast(int | None, args.limit)
    sleep_seconds = cast(float, args.sleep)
    resume = cast(bool, args.resume)
    done: set[str] = completed_ids(log_path) if resume else set()
    with candidates_path.open(newline="", encoding="utf-8") as fh:
        rows = [row for row in csv.DictReader(fh) if row.get("decision", "").strip().lower() == "approved"]
    attempted = 0
    for row in rows:
        if limit is not None and attempted >= limit:
            break
        tidal_id = row["tidal_id"].strip()
        if not tidal_id or tidal_id in done:
            continue
        attempted += 1
        try:
            message = download_tidal(rip, download_dir, tidal_id, quality)
            append_log(
                log_path,
                {
                    "source_order": row["source_order"],
                    "song_title": row["song_title"],
                    "artist": row["artist"],
                    "status": "downloaded",
                    "tidal_id": tidal_id,
                    "tidal_desc": row["tidal_desc"],
                    "message": message,
                },
            )
            print(f"downloaded {row['source_order']}: {row['song_title']} - {row['artist']} -> {tidal_id}")
        except Exception as exc:
            append_log(
                log_path,
                {
                    "source_order": row["source_order"],
                    "song_title": row["song_title"],
                    "artist": row["artist"],
                    "status": "error",
                    "tidal_id": tidal_id,
                    "tidal_desc": row["tidal_desc"],
                    "message": str(exc)[:1000],
                },
            )
            print(f"error {row['source_order']}: {row['song_title']} - {row['artist']}: {exc}")
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return 0


def inspect_media_tags(path: Path) -> dict[str, str]:
    has_title = False
    has_artist = False
    has_cover = False
    extension = path.suffix.lower()
    if extension == ".flac":
        audio = FLAC(path)
        flac_tags = cast(Mapping[str, object], cast(object, audio))
        pictures = cast(Sequence[object], audio.pictures)
        has_title = bool(flac_tags.get("title"))
        has_artist = bool(flac_tags.get("artist"))
        has_cover = bool(pictures)
    elif extension == ".mp3":
        audio = MP3(path)
        tags = cast(Id3Tags | None, audio.tags)
        has_title = bool(tags and tags.get("TIT2"))
        has_artist = bool(tags and tags.get("TPE1"))
        has_cover = bool(tags and tags.getall("APIC"))
    elif extension == ".m4a":
        audio = MP4(path)
        tags = cast(Mapping[str, object] | None, audio.tags)
        has_title = bool(tags and tags.get("\xa9nam"))
        has_artist = bool(tags and tags.get("\xa9ART"))
        has_cover = bool(tags and tags.get("covr"))
    ok = has_title and has_artist and has_cover
    return {
        "path": str(path),
        "extension": extension,
        "has_title": "true" if has_title else "false",
        "has_artist": "true" if has_artist else "false",
        "has_cover": "true" if has_cover else "false",
        "status": "ok" if ok else "missing_metadata",
    }


def command_verify_tags(args: argparse.Namespace) -> int:
    library_dir = cast(Path, args.library_dir)
    output_path = cast(Path | None, args.output)
    extensions = {".flac", ".mp3", ".m4a"}
    rows = [inspect_media_tags(path) for path in sorted(library_dir.rglob("*")) if path.is_file() and path.suffix.lower() in extensions]
    if output_path is not None:
        write_rows(output_path, TAG_REPORT_COLUMNS, rows)
    missing = [row for row in rows if row["status"] != "ok"]
    print(f"files={len(rows)}")
    print(f"ok={len(rows) - len(missing)}")
    print(f"missing_metadata={len(missing)}")
    if output_path is not None:
        print(f"tag_report={output_path}")
    for row in missing[:20]:
        print(f"missing {row['path']}: title={row['has_title']} artist={row['has_artist']} cover={row['has_cover']}")
    return 1 if missing else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search-candidates", help="Search Tidal and write candidates for AI/human review")
    _ = p_search.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    _ = p_search.add_argument("--output", type=Path, default=DEFAULT_CANDIDATES)
    _ = p_search.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    _ = p_search.add_argument("--rip", type=Path, default=Path(".venv/bin/rip"))
    _ = p_search.add_argument("--results", type=int, default=8)
    _ = p_search.add_argument("--sleep", type=float, default=3.0)
    _ = p_search.add_argument("--limit", type=int)
    p_search.set_defaults(func=command_search_candidates)

    p_download = sub.add_parser("download-approved", help="Download only reviewed candidates with decision=approved")
    _ = p_download.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    _ = p_download.add_argument("--download-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    _ = p_download.add_argument("--log", type=Path, default=DEFAULT_LOG)
    _ = p_download.add_argument("--rip", type=Path, default=Path(".venv/bin/rip"))
    _ = p_download.add_argument("--quality", type=int, default=2)
    _ = p_download.add_argument("--sleep", type=float, default=5.0)
    _ = p_download.add_argument("--limit", type=int)
    _ = p_download.add_argument("--resume", action="store_true")
    p_download.set_defaults(func=command_download_approved)

    p_verify = sub.add_parser("verify-tags", help="Verify downloaded audio has title, artist, and cover artwork")
    _ = p_verify.add_argument("--library-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    _ = p_verify.add_argument("--output", type=Path)
    p_verify.set_defaults(func=command_verify_tags)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    func = cast(object, getattr(args, "func"))
    if not callable(func):
        raise TypeError("parsed command is not callable")
    return cast(int, func(args))


if __name__ == "__main__":
    raise SystemExit(main())
