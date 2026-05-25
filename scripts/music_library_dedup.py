#!/usr/bin/env python3
"""Inventory and deduplicate local music libraries from tag metadata."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import cast

from scripts.audio_tags import INVENTORY_COLUMNS, extract_cover_art, iter_audio_files, inventory_record
from scripts.dedup_logic import (
    NEAR_DUPLICATE_COLUMNS,
    REVIEW_COLUMNS,
    InventoryRow,
    artwork_cache_path,
    attach_artwork_paths,
    cluster_inventory,
    read_inventory,
    render_review_html,
    summarize_review_rows,
    write_csv,
    write_review_json,
)

DEFAULT_OUTPUT = Path("source_identification/music_library_inventory.csv")
DEFAULT_SURVEY = Path("source_identification/music_library_survey.md")
DEFAULT_REVIEW_CSV = Path("source_identification/music_library_dedup_review.csv")
DEFAULT_REVIEW_JSON = Path("source_identification/music_library_dedup_review.json")
DEFAULT_NEAR_CSV = Path("source_identification/music_library_near_duplicates.csv")
DEFAULT_HTML = Path("source_identification/music_library_dedup_review.html")
DEFAULT_ARTWORK = Path("source_identification/artwork_cache/dedup")
DEFAULT_CLOUDMUSIC = Path.home() / "Music" / "CloudMusic"
DEFAULT_MUSIC = Path.home() / "Music" / "Music"


def command_read_tags(args: argparse.Namespace) -> int:
    roots = cast(list[Path], args.roots)
    output_path = cast(Path, args.output)
    rows: list[dict[str, str]] = []
    errors = 0
    for root in roots:
        library = root.name
        if not root.exists():
            print(f"missing_root={root}")
            continue
        for _, path in iter_audio_files([root]):
            record = inventory_record(library, root, path)
            if record.read_error:
                errors += 1
            rows.append(record.to_row())
            if len(rows) % 250 == 0:
                print(f"scanned={len(rows)}")

    write_csv(output_path, INVENTORY_COLUMNS, rows)
    stats = Counter((row["library"], row["extension"]) for row in rows)
    missing_title = sum(1 for row in rows if row["has_tag_title"] == "false")
    missing_artist = sum(1 for row in rows if row["has_tag_artist"] == "false")
    missing_cover = sum(1 for row in rows if row["has_cover"] == "false")

    print(f"files={len(rows)}")
    print(f"read_errors={errors}")
    print(f"missing_tag_title={missing_title}")
    print(f"missing_tag_artist={missing_artist}")
    print(f"missing_cover={missing_cover}")
    for (library, extension), count in sorted(stats.items()):
        print(f"library={library} ext={extension} count={count}")
    print(f"inventory_csv={output_path}")
    return 1 if errors else 0


def survey_library_layout(root: Path) -> dict[str, object]:
    layout: Counter[str] = Counter()
    extensions: Counter[str] = Counter()
    audio_count = 0
    if not root.exists():
        return {"root": str(root), "exists": False, "audio_files": 0, "layout": {}, "extensions": {}}

    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in {".mp3", ".m4a", ".flac", ".aac", ".wma"}:
            continue
        audio_count += 1
        extensions[path.suffix.lower()] += 1
        relative = path.relative_to(root)
        bucket = relative.parts[0] if len(relative.parts) > 1 else "(root)"
        layout[bucket] += 1

    return {
        "root": str(root),
        "exists": True,
        "audio_files": audio_count,
        "layout": dict(layout.most_common(20)),
        "extensions": dict(extensions),
    }


def command_survey(args: argparse.Namespace) -> int:
    inventory_path = cast(Path, args.inventory)
    output_path = cast(Path, args.output)
    roots = cast(list[Path], args.roots)
    if not inventory_path.exists():
        print(f"missing_inventory={inventory_path}")
        return 1

    rows = read_inventory(inventory_path)
    total = len(rows)
    missing_title = sum(1 for row in rows if not row.has_tag_title)
    missing_artist = sum(1 for row in rows if not row.has_tag_artist)
    missing_cover = sum(1 for row in rows if not row.has_cover)
    read_errors = sum(1 for row in rows if row.read_error)
    tag_sources = Counter(row.tag_source for row in rows)
    libraries = Counter(row.library for row in rows)

    layouts = [survey_library_layout(root) for root in roots]
    lines = [
        "# Music Library Survey",
        "",
        "Generated from tag inventory and directory layout scans.",
        "",
        "## Scope",
        "",
    ]
    for root in roots:
        lines.append(f"- `{root}`")
    lines.extend(
        [
            "",
            "## Inventory Summary",
            "",
            f"- Total audio files: **{total}**",
            f"- Read errors: **{read_errors}**",
            f"- Missing embedded title: **{missing_title}**",
            f"- Missing embedded artist: **{missing_artist}**",
            f"- Missing cover art: **{missing_cover}**",
            "",
            "### Files by library",
            "",
        ]
    )
    for library, count in sorted(libraries.items()):
        lines.append(f"- `{library}`: {count}")
    lines.extend(["", "### Tag sources", ""])
    for source, count in sorted(tag_sources.items()):
        lines.append(f"- `{source}`: {count}")

    for layout in layouts:
        lines.extend(
            [
                "",
                f"## Layout: `{layout['root']}`",
                "",
                f"- Audio files: **{layout['audio_files']}**",
                "",
                "### Top-level buckets",
                "",
            ]
        )
        for bucket, count in cast(dict[str, int], layout.get("layout", {})).items():
            lines.append(f"- `{bucket}`: {count}")
        lines.extend(["", "### Extensions", ""])
        for ext, count in cast(dict[str, int], layout.get("extensions", {})).items():
            lines.append(f"- `{ext}`: {count}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"survey_md={output_path}")
    print(f"files={total}")
    return 0


def command_build_review(args: argparse.Namespace) -> int:
    inventory_path = cast(Path, args.inventory)
    review_csv = cast(Path, args.review_csv)
    review_json = cast(Path, args.review_json)
    near_csv = cast(Path, args.near_csv)
    html_path = cast(Path, args.html)
    artwork_dir = cast(Path, args.artwork_dir)

    if not inventory_path.exists():
        print(f"missing_inventory={inventory_path}")
        return 1

    inventory_rows = read_inventory(inventory_path)
    review_rows, near_rows = cluster_inventory(inventory_rows)
    summary = summarize_review_rows(review_rows)

    unique_paths = {row["full_path"] for row in review_rows}
    extracted = 0
    for full_path in sorted(unique_paths):
        source = Path(full_path)
        cache_path = artwork_cache_path(artwork_dir, full_path)
        if cache_path.exists():
            continue
        if source.exists() and extract_cover_art(source, cache_path):
            extracted += 1

    attach_artwork_paths(review_rows, artwork_dir)
    write_csv(review_csv, REVIEW_COLUMNS, review_rows)
    write_csv(near_csv, NEAR_DUPLICATE_COLUMNS, near_rows)
    write_review_json(review_json, review_rows, summary)
    render_review_html(review_rows, summary, html_path, review_csv)

    print(f"duplicate_clusters={summary['duplicate_clusters']}")
    print(f"duplicate_files={summary['duplicate_files']}")
    print(f"pending_non_canonical={summary['pending_non_canonical']}")
    print(f"needs_review_clusters={summary['needs_review_clusters']}")
    print(f"near_duplicate_groups={len(near_rows)}")
    print(f"artwork_extracted={extracted}")
    print(f"review_csv={review_csv}")
    print(f"review_json={review_json}")
    print(f"near_duplicates_csv={near_csv}")
    print(f"review_html={html_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    read_tags = sub.add_parser("read-tags", help="Scan local audio directories and write a tag inventory CSV")
    _ = read_tags.add_argument(
        "--roots",
        type=Path,
        nargs="+",
        default=[DEFAULT_CLOUDMUSIC, DEFAULT_MUSIC],
        help="Library roots to scan (default: ~/Music/CloudMusic and ~/Music/Music)",
    )
    _ = read_tags.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    read_tags.set_defaults(func=command_read_tags)

    survey = sub.add_parser("survey", help="Write folder-structure and tag-coverage survey markdown")
    _ = survey.add_argument("--inventory", type=Path, default=DEFAULT_OUTPUT)
    _ = survey.add_argument("--roots", type=Path, nargs="+", default=[DEFAULT_CLOUDMUSIC, DEFAULT_MUSIC])
    _ = survey.add_argument("--output", type=Path, default=DEFAULT_SURVEY)
    survey.set_defaults(func=command_survey)

    build_review = sub.add_parser(
        "build-review",
        help="Cluster duplicates, choose canonical files, and write CSV/JSON/HTML review artifacts",
    )
    _ = build_review.add_argument("--inventory", type=Path, default=DEFAULT_OUTPUT)
    _ = build_review.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV)
    _ = build_review.add_argument("--review-json", type=Path, default=DEFAULT_REVIEW_JSON)
    _ = build_review.add_argument("--near-csv", type=Path, default=DEFAULT_NEAR_CSV)
    _ = build_review.add_argument("--html", type=Path, default=DEFAULT_HTML)
    _ = build_review.add_argument("--artwork-dir", type=Path, default=DEFAULT_ARTWORK)
    build_review.set_defaults(func=command_build_review)
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
