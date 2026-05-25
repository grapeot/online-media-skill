#!/usr/bin/env python3
"""Prepare deterministic media artifacts for agent-led source identification."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Iterable, Mapping
from typing import cast


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY = ROOT / "library"
DEFAULT_OUTPUT = ROOT / "source_identification"
DEFAULT_ASR_DIR = DEFAULT_OUTPUT / "asr"
DEFAULT_TRANSCRIBE = Path(os.environ.get("ONLINE_MEDIA_TRANSCRIBE_SCRIPT", ROOT / "scripts" / "transcribe.py"))
DEFAULT_ASR_PYTHON = Path(os.environ.get("ONLINE_MEDIA_ASR_PYTHON", sys.executable))
DEFAULT_MODEL = "Qwen/Qwen3-ASR-1.7B"

YEAR_PATTERN = re.compile(
    r"【(?:19\d{2}|20\d{2})[^】]*】|(?:19\d{2}|20\d{2})年前|(?:19\d{2}|20\d{2})那年|(?:19\d{2}|20\d{2})年的|人过了20\d{2}|把20\d{2}年的"
)
SEGMENT_PATTERN = re.compile(r"^\[(\d{2}:\d{2})-(\d{2}:\d{2})\]\s*(.*)$")



SOURCE_COLUMNS = [
    "order",
    "source_file",
    "asr_file",
    "start",
    "end",
    "song_title",
    "artist",
    "release_year",
    "lyric_evidence",
    "source_urls",
    "confidence",
    "needs_review",
    "notes",
]
DEDUPED_COLUMNS = [
    "order",
    "song_title",
    "artist",
    "release_year",
    "best_confidence",
    "needs_review",
    "occurrence_count",
    "source_files",
    "time_ranges",
    "lyric_evidence",
    "source_urls",
    "notes",
]
NEAR_DUPLICATE_COLUMNS = [
    "title_key",
    "song_title",
    "artists",
    "dedupe_orders",
    "occurrence_count",
    "notes",
]
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass
class SourceEntry:
    song_title: str
    artist: str
    release_year: str
    confidence: str
    needs_review: bool
    source_file: str
    start: str
    end: str
    lyric_evidence: str
    source_urls: list[str]
    notes: str


@dataclass
class DedupeGroup:
    song_title: str
    artist: str
    release_year: str = ""
    best_confidence: str = "low"
    needs_review: bool = False
    occurrences: list[SourceEntry] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    lyric_evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, entry: SourceEntry) -> None:
        self.occurrences.append(entry)
        if not self.release_year and entry.release_year:
            self.release_year = entry.release_year
        if CONFIDENCE_RANK.get(entry.confidence, 0) > CONFIDENCE_RANK.get(self.best_confidence, 0):
            self.best_confidence = entry.confidence
        self.needs_review = self.needs_review or entry.needs_review
        for url in entry.source_urls:
            if url and url not in self.source_urls:
                self.source_urls.append(url)
        if entry.lyric_evidence and entry.lyric_evidence not in self.lyric_evidence:
            self.lyric_evidence.append(entry.lyric_evidence)
        if entry.notes and entry.notes not in self.notes:
            self.notes.append(entry.notes)


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def split_multi_value(value: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s*/\s*", value) if part.strip()]
    return parts or [value.strip()]


def parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def parse_source_urls(value: str) -> list[str]:
    if not value.strip():
        return []
    loaded = cast(object, json.loads(value))
    if not isinstance(loaded, list):
        raise ValueError("source_urls must be a JSON array")
    items = cast(list[object], loaded)
    return [str(item) for item in items if str(item)]


def expand_source_row(row: Mapping[str, str]) -> list[SourceEntry]:
    title = row.get("song_title", "").strip()
    artist = row.get("artist", "").strip()
    if not title:
        return []
    titles = split_multi_value(title)
    artists = split_multi_value(artist) if artist else [""]
    entries: list[SourceEntry] = []
    for index, split_title in enumerate(titles):
        split_artist = artists[index] if len(artists) == len(titles) else artist
        entries.append(
            SourceEntry(
                song_title=split_title,
                artist=split_artist,
                release_year=row.get("release_year", "").strip(),
                confidence=row.get("confidence", "").strip().lower() or "low",
                needs_review=parse_bool(row.get("needs_review", "")),
                source_file=Path(row.get("source_file", "").strip()).name,
                start=row.get("start", "").strip(),
                end=row.get("end", "").strip(),
                lyric_evidence=row.get("lyric_evidence", "").strip(),
                source_urls=parse_source_urls(row.get("source_urls", "")),
                notes=row.get("notes", "").strip(),
            )
        )
    return entries


def read_source_entries(path: Path) -> list[SourceEntry]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != SOURCE_COLUMNS:
            raise ValueError(f"unexpected source CSV header: {reader.fieldnames}")
        rows = list(reader)
    entries: list[SourceEntry] = []
    for row in rows:
        entries.extend(expand_source_row(row))
    return entries


def dedupe_entries(entries: Iterable[SourceEntry]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    groups: dict[tuple[str, str], DedupeGroup] = {}
    for entry in entries:
        key = (normalize_key(entry.song_title), normalize_key(entry.artist))
        if key not in groups:
            groups[key] = DedupeGroup(song_title=entry.song_title, artist=entry.artist)
        groups[key].add(entry)

    sorted_groups = sorted(groups.values(), key=lambda group: (normalize_key(group.song_title), normalize_key(group.artist)))
    rows: list[dict[str, str]] = []
    title_to_orders: dict[str, list[int]] = {}
    title_to_artists: dict[str, set[str]] = {}
    for order, group in enumerate(sorted_groups, 1):
        title_key = normalize_key(group.song_title)
        title_to_orders.setdefault(title_key, []).append(order)
        title_to_artists.setdefault(title_key, set()).add(group.artist)
        source_files = sorted({entry.source_file for entry in group.occurrences if entry.source_file})
        time_ranges = [
            {
                "source_file": entry.source_file,
                "start": entry.start,
                "end": entry.end,
                "confidence": entry.confidence,
                "needs_review": entry.needs_review,
            }
            for entry in group.occurrences
        ]
        rows.append(
            {
                "order": str(order),
                "song_title": group.song_title,
                "artist": group.artist,
                "release_year": group.release_year,
                "best_confidence": group.best_confidence,
                "needs_review": "true" if group.needs_review else "false",
                "occurrence_count": str(len(group.occurrences)),
                "source_files": json.dumps(source_files, ensure_ascii=False),
                "time_ranges": json.dumps(time_ranges, ensure_ascii=False),
                "lyric_evidence": " | ".join(group.lyric_evidence[:3]),
                "source_urls": json.dumps(group.source_urls, ensure_ascii=False),
                "notes": " | ".join(group.notes[:3]),
            }
        )

    near_rows: list[dict[str, str]] = []
    for title_key, artists in sorted(title_to_artists.items()):
        if len(artists) <= 1:
            continue
        orders = title_to_orders[title_key]
        title = next(row["song_title"] for row in rows if int(row["order"]) == orders[0])
        near_rows.append(
            {
                "title_key": title_key,
                "song_title": title,
                "artists": json.dumps(sorted(artists), ensure_ascii=False),
                "dedupe_orders": json.dumps(orders),
                "occurrence_count": str(sum(int(rows[order - 1]["occurrence_count"]) for order in orders)),
                "notes": "Same normalized title appears with multiple artists; review before bulk download.",
            }
        )
    return rows, near_rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

@dataclass(frozen=True)
class Segment:
    start: str
    end: str
    text: str


@dataclass(frozen=True)
class QueryRecord:
    source_file: str
    asr_file: str
    segment_id: int
    start: str
    end: str
    text: str
    anchor: str
    query: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "source_file": self.source_file,
            "asr_file": self.asr_file,
            "segment_id": self.segment_id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "anchor": self.anchor,
            "query": self.query,
        }


def is_year_labeled(path: Path) -> bool:
    return path.suffix.lower() == ".m4a" and YEAR_PATTERN.search(path.stem) is not None


def list_year_files(library: Path) -> list[Path]:
    return sorted(p for p in library.glob("*.m4a") if is_year_labeled(p))


def safe_stem(path: Path) -> str:
    return re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", path.stem).strip("_")


def parse_segments(asr_markdown: str) -> list[Segment]:
    segments: list[Segment] = []
    for line in asr_markdown.splitlines():
        match = SEGMENT_PATTERN.match(line.strip())
        if not match:
            continue
        text = match.group(3).strip()
        if text:
            segments.append(Segment(match.group(1), match.group(2), text))
    return segments


def split_anchor_candidates(text: str, *, min_len: int = 5, max_len: int = 34) -> list[str]:
    normalized = re.sub(r"\s+", "", text)
    parts = [p for p in re.split(r"[。！？；;，,、]", normalized) if len(p) >= min_len]
    anchors: list[str] = []
    for part in parts:
        if len(part) <= max_len:
            anchors.append(part)
            continue
        for start in range(0, len(part), max_len):
            chunk = part[start : start + max_len]
            if len(chunk) >= min_len:
                anchors.append(chunk)
    return anchors


def pick_anchors(segment: Segment, limit: int = 2) -> list[str]:
    anchors = split_anchor_candidates(segment.text)
    anchors.sort(key=len, reverse=True)
    return anchors[:limit]


def build_query(anchor: str) -> str:
    return f'"{anchor}" 歌名'


def build_query_pack(source_file: Path, asr_file: Path, *, anchors_per_segment: int = 2) -> list[QueryRecord]:
    segments = parse_segments(asr_file.read_text(encoding="utf-8"))
    records: list[QueryRecord] = []
    for segment_id, segment in enumerate(segments, 1):
        for anchor in pick_anchors(segment, anchors_per_segment):
            records.append(
                QueryRecord(
                    source_file=str(source_file),
                    asr_file=str(asr_file),
                    segment_id=segment_id,
                    start=segment.start,
                    end=segment.end,
                    text=segment.text,
                    anchor=anchor,
                    query=build_query(anchor),
                )
            )
    return records


def write_jsonl(path: Path, records: Iterable[QueryRecord | Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            serializable = record.to_dict() if isinstance(record, QueryRecord) else record
            _ = fh.write(json.dumps(serializable, ensure_ascii=False) + "\n")


def transcribe_file(
    audio_file: Path,
    asr_file: Path,
    *,
    asr_python: Path = DEFAULT_ASR_PYTHON,
    transcribe_script: Path = DEFAULT_TRANSCRIBE,
    model: str = DEFAULT_MODEL,
    force: bool = False,
) -> None:
    if asr_file.exists() and not force:
        return
    asr_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(asr_python),
        str(transcribe_script),
        "--input",
        str(audio_file),
        "--output",
        str(asr_file),
        "--model",
        model,
        "--language",
        "auto",
        "--include-segments",
        "--title",
        audio_file.stem,
    ]
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ASR failed for {audio_file}")




def namespace_value(args: argparse.Namespace, name: str) -> object:
    values = cast(Mapping[str, object], vars(args))
    return values[name]

def namespace_path(args: argparse.Namespace, name: str) -> Path:
    value = namespace_value(args, name)
    if isinstance(value, Path):
        return value
    raise TypeError(f"{name} must be a Path")


def namespace_optional_path(args: argparse.Namespace, name: str) -> Path | None:
    value = namespace_value(args, name)
    if value is None or isinstance(value, Path):
        return value
    raise TypeError(f"{name} must be a Path or None")


def namespace_optional_int(args: argparse.Namespace, name: str) -> int | None:
    value = namespace_value(args, name)
    if value is None or isinstance(value, int):
        return value
    raise TypeError(f"{name} must be an int or None")


def namespace_str(args: argparse.Namespace, name: str) -> str:
    value = namespace_value(args, name)
    if isinstance(value, str):
        return value
    raise TypeError(f"{name} must be a str")


def namespace_bool(args: argparse.Namespace, name: str) -> bool:
    value = namespace_value(args, name)
    if isinstance(value, bool):
        return value
    raise TypeError(f"{name} must be a bool")

def command_list(args: argparse.Namespace) -> int:
    library = namespace_path(args, "library")
    output = namespace_optional_path(args, "output")
    files = list_year_files(library)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        _ = output.write_text("\n".join(str(p) for p in files) + "\n", encoding="utf-8")
    else:
        for path in files:
            print(path)
    return 0


def command_transcribe(args: argparse.Namespace) -> int:
    library = namespace_path(args, "library")
    asr_dir = namespace_path(args, "asr_dir")
    asr_python = namespace_path(args, "asr_python")
    transcribe_script = namespace_path(args, "transcribe_script")
    model = namespace_str(args, "model")
    limit = namespace_optional_int(args, "limit")
    force = namespace_bool(args, "force")
    files = list_year_files(library)
    if limit:
        files = files[:limit]
    for index, audio in enumerate(files, 1):
        out = asr_dir / f"{safe_stem(audio)}.md"
        print(f"[{index}/{len(files)}] ASR {audio.name} -> {out}")
        transcribe_file(
            audio,
            out,
            asr_python=asr_python,
            transcribe_script=transcribe_script,
            model=model,
            force=force,
        )
    return 0


def command_query_pack(args: argparse.Namespace) -> int:
    library = namespace_path(args, "library")
    asr_dir = namespace_path(args, "asr_dir")
    output = namespace_path(args, "output")
    anchors_per_segment = namespace_optional_int(args, "anchors_per_segment")
    if anchors_per_segment is None:
        raise TypeError("anchors_per_segment must be an int")
    limit = namespace_optional_int(args, "limit")
    files = list_year_files(library)
    if limit:
        files = files[:limit]
    records: list[QueryRecord] = []
    for index, audio in enumerate(files, 1):
        asr_file = asr_dir / f"{safe_stem(audio)}.md"
        if not asr_file.exists():
            print(f"skip missing ASR: {asr_file}", file=sys.stderr)
            continue
        print(f"[{index}/{len(files)}] query-pack {audio.name}")
        records.extend(build_query_pack(audio, asr_file, anchors_per_segment=anchors_per_segment))
    write_jsonl(output, records)
    print(f"Query pack saved: {output} ({len(records)} rows)")
    return 0


def command_dedupe_sources(args: argparse.Namespace) -> int:
    input_path = namespace_path(args, "input")
    output_path = namespace_path(args, "output")
    near_duplicates_path = namespace_path(args, "near_duplicates")
    entries = read_source_entries(input_path)
    deduped_rows, near_duplicate_rows = dedupe_entries(entries)
    write_csv(output_path, DEDUPED_COLUMNS, deduped_rows)
    write_csv(near_duplicates_path, NEAR_DUPLICATE_COLUMNS, near_duplicate_rows)
    print(f"identified_entries={len(entries)}")
    print(f"deduped_entries={len(deduped_rows)}")
    print(f"near_duplicate_groups={len(near_duplicate_rows)}")
    print(f"deduped_csv={output_path}")
    print(f"near_duplicates_csv={near_duplicates_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-year-files", help="List library audio files whose titles contain years")
    _ = p_list.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    _ = p_list.add_argument("--output", type=Path)
    p_list.set_defaults(func=command_list)

    p_asr = sub.add_parser("transcribe", help="Run Qwen ASR on year-labeled audio files")
    _ = p_asr.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    _ = p_asr.add_argument("--asr-dir", type=Path, default=DEFAULT_ASR_DIR)
    _ = p_asr.add_argument("--asr-python", type=Path, default=DEFAULT_ASR_PYTHON)
    _ = p_asr.add_argument("--transcribe-script", type=Path, default=DEFAULT_TRANSCRIBE)
    _ = p_asr.add_argument("--model", default=DEFAULT_MODEL)
    _ = p_asr.add_argument("--limit", type=int)
    _ = p_asr.add_argument("--force", action="store_true")
    p_asr.set_defaults(func=command_transcribe)

    p_query = sub.add_parser("query-pack", help="Export deterministic lyric anchor queries from ASR markdown")
    _ = p_query.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    _ = p_query.add_argument("--asr-dir", type=Path, default=DEFAULT_ASR_DIR)
    _ = p_query.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "anchor_queries.jsonl")
    _ = p_query.add_argument("--anchors-per-segment", type=int, default=2)
    _ = p_query.add_argument("--limit", type=int)
    p_query.set_defaults(func=command_query_pack)

    p_dedupe = sub.add_parser("dedupe-sources", help="Deduplicate identified medley source-song CSV rows")
    _ = p_dedupe.add_argument("--input", type=Path, default=DEFAULT_OUTPUT / "medley_sources.csv")
    _ = p_dedupe.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "medley_sources_deduped.csv")
    _ = p_dedupe.add_argument(
        "--near-duplicates",
        type=Path,
        default=DEFAULT_OUTPUT / "near_duplicates_for_review.csv",
    )
    p_dedupe.set_defaults(func=command_dedupe_sources)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = cast(Callable[[argparse.Namespace], int], getattr(args, "func"))
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
