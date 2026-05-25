#!/usr/bin/env python3
"""Download Bilibili audio and tag for iPhone Music import."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "library"
YTDLP = ROOT / ".venv" / "bin" / "yt-dlp"

# Bilibili DASH audio: 30280 (~214k) > 30232 (~104k) > 30216 (~66k)
BEST_AUDIO_FORMAT = "30280/bestaudio/best"


def run_ytdlp(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [str(YTDLP), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def dump_info(url: str) -> dict:
    proc = run_ytdlp(["--dump-single-json", "--no-download", url])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def sanitize_filename(name: str, max_len: int = 120) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return cleaned[:max_len] or "untitled"


def download_audio(url: str, out_dir: Path, playlist_index: int | None = None) -> tuple[Path, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    info = dump_info(url)
    video_id = info["id"]
    title = info.get("title") or video_id
    stem = sanitize_filename(f"{playlist_index:03d}_{title}" if playlist_index else title)
    audio_path = out_dir / f"{stem}.m4a"
    info_json = out_dir / f"{stem}.info.json"

    if audio_path.exists() and info_json.exists():
        return audio_path, json.loads(info_json.read_text())

    output_template = str(out_dir / f"{stem}.%(ext)s")
    args = [
        url,
        "-f",
        BEST_AUDIO_FORMAT,
        "--no-playlist",
        "-o",
        output_template,
        "--write-info-json",
        "--no-overwrites",
        "--sleep-interval",
        "2",
        "--max-sleep-interval",
        "5",
        "--retries",
        "5",
        "--fragment-retries",
        "5",
    ]
    proc = run_ytdlp(args)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())

    if not info_json.exists():
        raise FileNotFoundError(f"Missing info json: {info_json}")
    return audio_path, json.loads(info_json.read_text())


def fetch_cover(thumbnail_url: str) -> bytes:
    req = urllib.request.Request(
        thumbnail_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def tag_for_iphone(
    audio_path: Path,
    info: dict,
    *,
    album: str | None = None,
    track_number: int | None = None,
    total_tracks: int | None = None,
) -> None:
    mp4 = MP4(audio_path)
    title = info.get("title") or info.get("id")
    artist = info.get("uploader") or info.get("channel") or "Unknown Artist"
    upload_date = info.get("upload_date") or ""
    year = upload_date[:4] if len(upload_date) >= 4 else ""
    video_id = info.get("id", "")
    webpage = info.get("webpage_url") or ""

    mp4["\xa9nam"] = [title]
    mp4["\xa9ART"] = [artist]
    mp4["aART"] = [artist]
    if album:
        mp4["\xa9alb"] = [album]
    if year:
        mp4["\xa9day"] = [year]
    if track_number is not None:
        total = total_tracks or track_number
        mp4["trkn"] = [(track_number, total)]
    if webpage:
        mp4["\xa9cmt"] = [f"{video_id} | {webpage}"]

    tags = info.get("tags") or []
    if tags:
        mp4["\xa9gen"] = [tags[0]]

    thumbnail = info.get("thumbnail")
    if thumbnail:
        cover_data = fetch_cover(thumbnail)
        mp4["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]

    mp4.save()


def verify_tags(audio_path: Path) -> dict[str, str]:
    mp4 = MP4(audio_path)
    keys = {
        "title": "\xa9nam",
        "artist": "\xa9ART",
        "album": "\xa9alb",
        "album_artist": "aART",
        "date": "\xa9day",
        "comment": "\xa9cmt",
        "genre": "\xa9gen",
    }
    out: dict[str, str] = {}
    for label, key in keys.items():
        if key in mp4:
            val = mp4[key][0]
            out[label] = str(val)
    out["track"] = str(mp4.get("trkn", [None])[0])
    out["has_cover"] = str("covr" in mp4 and bool(mp4["covr"]))
    return out


def list_playlist(url: str) -> list[dict[str, str]]:
    proc = run_ytdlp(["--flat-playlist", "--dump-single-json", url])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    data = json.loads(proc.stdout)
    entries = data.get("entries") or []
    return [
        {
            "id": entry.get("id") or entry.get("url", "").split("/")[-1],
            "title": entry.get("title") or entry.get("id") or "unknown",
            "url": entry.get("url") or entry.get("webpage_url") or f"https://www.bilibili.com/video/{entry.get('id')}",
        }
        for entry in entries
        if entry.get("id") or entry.get("url")
    ]


def download_playlist(url: str, out_dir: Path, album: str | None = None) -> list[dict]:
    entries = list_playlist(url)
    if not entries:
        raise RuntimeError("playlist is empty")
    album_name = album or "Bilibili Collection"
    total = len(entries)
    results: list[dict] = []
    for index, entry in enumerate(entries, start=1):
        video_url = entry["url"]
        if not video_url.startswith("http"):
            video_url = f"https://www.bilibili.com/video/{entry['id']}"
        audio_path, info = download_audio(video_url, out_dir, index)
        tag_for_iphone(
            audio_path,
            info,
            album=album_name,
            track_number=index,
            total_tracks=total,
        )
        results.append(
            {
                "track": index,
                "file": str(audio_path),
                "tags": verify_tags(audio_path),
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="Bilibili video or collection URL")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--album", help="Album name for playlist imports")
    parser.add_argument("--track-number", type=int)
    parser.add_argument("--total-tracks", type=int)
    parser.add_argument("--playlist", action="store_true", help="Download every item in a collection URL")
    parser.add_argument("--list-only", action="store_true", help="Print playlist entries without downloading")
    parser.add_argument("--verify-only", type=Path, help="Verify tags on existing m4a")
    args = parser.parse_args()

    if args.verify_only:
        tags = verify_tags(args.verify_only)
        print(json.dumps(tags, ensure_ascii=False, indent=2))
        return 0

    if not args.url:
        parser.error("url is required unless --verify-only is used")

    if args.list_only:
        entries = list_playlist(args.url)
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0

    if args.playlist:
        results = download_playlist(args.url, args.out_dir, album=args.album)
        print(json.dumps({"count": len(results), "tracks": results}, ensure_ascii=False, indent=2))
        return 0

    audio_path, info = download_audio(args.url, args.out_dir, args.track_number)
    tag_for_iphone(
        audio_path,
        info,
        album=args.album,
        track_number=args.track_number,
        total_tracks=args.total_tracks,
    )
    tags = verify_tags(audio_path)
    print(json.dumps({"file": str(audio_path), "tags": tags}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
