#!/usr/bin/env python3
"""Deterministic artifacts for agent-led bilingual subtitle workflows."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any


TIMESTAMP_TOKEN = r"(?:(?:\d{2,}):)?\d{2}:\d{2}[.,]\d{3}"
TIMING_RE = re.compile(rf"^(?P<start>{TIMESTAMP_TOKEN})\s+-->\s+(?P<end>{TIMESTAMP_TOKEN})(?:\s+.*)?$")
SRT_TIMESTAMP_TOKEN = r"\d{2,}:\d{2}:\d{2},\d{3}"
SRT_TIMING_RE = re.compile(
    rf"^(?P<start>{SRT_TIMESTAMP_TOKEN})\s+-->\s+(?P<end>{SRT_TIMESTAMP_TOKEN})$"
)
SPEAKER_RE = re.compile(r"^[^:\n]{1,80}:\s+")
VOICE_RE = re.compile(r"^<v(?:\.[^ >]+)*\s+([^>]+)>(.*?)(?:</v>)?$", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
SCHEMA_VERSION = 1


def parse_timestamp(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    if len(parts) == 2:
        hours = 0
        minutes_text, seconds_text = parts
    elif len(parts) == 3:
        hours_text, minutes_text, seconds_text = parts
        hours = int(hours_text)
    else:
        raise ValueError(f"invalid timestamp: {value}")
    minutes = int(minutes_text)
    seconds = float(seconds_text)
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60 or not math.isfinite(seconds):
        raise ValueError(f"invalid timestamp: {value}")
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def parse_vtt(path: Path) -> list[dict[str, Any]]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig"))
    cues: list[dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((index for index, line in enumerate(lines) if TIMING_RE.match(line)), None)
        if timing_index is None:
            first = lines[0] if lines else ""
            if first.startswith(("WEBVTT", "NOTE", "STYLE", "REGION", "X-TIMESTAMP-MAP")):
                continue
            if lines:
                raise ValueError(f"unrecognized VTT cue block: {block[:120]!r}")
            continue
        match = TIMING_RE.match(lines[timing_index])
        if match is None:
            continue
        raw_text = " ".join(lines[timing_index + 1 :]).strip()
        voice_match = VOICE_RE.match(raw_text)
        voice_speaker = html.unescape(TAG_RE.sub("", voice_match.group(1))).strip() if voice_match else ""
        voice_text = voice_match.group(2) if voice_match else raw_text
        text = html.unescape(TAG_RE.sub("", voice_text)).strip()
        if not text:
            continue
        speaker_match = SPEAKER_RE.match(text)
        speaker = voice_speaker or (text[: text.find(":")] if speaker_match else "")
        cues.append(
            {
                "cue_id": len(cues) + 1,
                "start": parse_timestamp(match.group("start")),
                "end": parse_timestamp(match.group("end")),
                "speaker": speaker,
                "source_text": text if voice_speaker else SPEAKER_RE.sub("", text),
            }
        )
    return cues


def select_cues(cues: Iterable[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    """Assign boundary-spanning cues by start time so adjacent packets do not overlap."""
    return [cue for cue in cues if start <= float(cue["start"]) < end]


def read_jsonl(paths: Sequence[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                loaded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            if not isinstance(loaded, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            records.append(loaded)
    return records


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def require_distinct_paths(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("input, output, source, and manifest paths must be distinct")


def source_ids(record: dict[str, Any]) -> list[int]:
    ids = record.get("source_cue_ids")
    if ids is None and isinstance(record.get("cue_id"), int):
        ids = [record["cue_id"]]
    if (
        not isinstance(ids, list)
        or not ids
        or any(not isinstance(item, int) or isinstance(item, bool) for item in ids)
    ):
        raise ValueError("record must contain cue_id or a non-empty integer source_cue_ids array")
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValueError(f"source_cue_ids must be ordered and unique: {ids}")
    return ids


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    source_vtt_path: Path,
    source_jsonl_path: Path,
    line_1_language: str,
    line_2_language: str,
) -> dict[str, Any]:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_vtt_file": source_vtt_path.name,
        "source_vtt_sha256": file_sha256(source_vtt_path),
        "source_jsonl_file": source_jsonl_path.name,
        "source_jsonl_sha256": file_sha256(source_jsonl_path),
        "line_1_language": line_1_language.strip(),
        "line_2_language": line_2_language.strip(),
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {manifest.get('schema_version')}")
    for field in ("source_vtt_file", "source_jsonl_file", "line_1_language", "line_2_language"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"manifest {field} must be a non-empty string")
    if manifest["line_1_language"] == manifest["line_2_language"]:
        raise ValueError("line_1_language and line_2_language must differ")
    for field in ("source_vtt_sha256", "source_jsonl_sha256"):
        value = manifest.get(field)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"manifest {field} must be a SHA-256 hex digest")
    reviewed = manifest.get("reviewed_artifacts")
    if reviewed is not None:
        if not isinstance(reviewed, list) or not reviewed:
            raise ValueError("manifest reviewed_artifacts must be a non-empty array")
        for item in reviewed:
            if not isinstance(item, dict) or set(item) != {"file", "sha256"}:
                raise ValueError("each reviewed artifact must contain file and sha256")
            if not isinstance(item["file"], str) or re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"])) is None:
                raise ValueError("invalid reviewed artifact manifest entry")
    if "srt_file" in manifest or "srt_sha256" in manifest:
        if not isinstance(manifest.get("srt_file"), str) or not manifest["srt_file"]:
            raise ValueError("manifest srt_file must be a non-empty string")
        if re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("srt_sha256", ""))) is None:
            raise ValueError("manifest srt_sha256 must be a SHA-256 hex digest")


def read_manifest(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("manifest must be a JSON object")
    validate_manifest(loaded)
    return loaded


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    validate_manifest(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_source_matches_manifest(manifest: dict[str, Any], source_path: Path) -> None:
    if source_path.name != manifest["source_jsonl_file"]:
        raise ValueError("source JSONL filename does not match manifest")
    if file_sha256(source_path) != manifest["source_jsonl_sha256"]:
        raise ValueError("source JSONL hash does not match manifest")


def record_times(record: dict[str, Any], ids: list[int]) -> tuple[float, float]:
    start = record.get("start")
    end = record.get("end")
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        raise ValueError(f"cue group {ids} must have numeric start and end")
    start_float = float(start)
    end_float = float(end)
    if not math.isfinite(start_float) or not math.isfinite(end_float) or end_float <= start_float:
        raise ValueError(f"cue group {ids} has invalid timing")
    return start_float, end_float


def segment_times(segment: dict[str, Any], ids: list[int], index: int) -> tuple[float, float]:
    line_1 = segment.get("line_1")
    line_2 = segment.get("line_2")
    if not isinstance(line_1, str) or not line_1.strip():
        raise ValueError(f"cue group {ids} segment {index} line_1 must be a non-empty string")
    if not isinstance(line_2, str) or not line_2.strip():
        raise ValueError(f"cue group {ids} segment {index} line_2 must be a non-empty string")
    start = segment.get("start")
    end = segment.get("end")
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        raise ValueError(f"cue group {ids} segment {index} must have numeric start and end")
    start_float = float(start)
    end_float = float(end)
    if not math.isfinite(start_float) or not math.isfinite(end_float) or end_float <= start_float:
        raise ValueError(f"cue group {ids} segment {index} has invalid timing")
    return start_float, end_float


def verify_work(source: Sequence[dict[str, Any]], work: Sequence[dict[str, Any]]) -> tuple[int, int]:
    if not source:
        raise ValueError("source cue list is empty")
    if not work:
        raise ValueError("reviewed work is empty")
    source_by_id: dict[int, dict[str, Any]] = {}
    for record in source:
        cue_id = record.get("cue_id")
        if not isinstance(cue_id, int) or isinstance(cue_id, bool):
            raise ValueError("source cue_id values must be integers")
        source_by_id[cue_id] = record
    if len(source_by_id) != len(source):
        raise ValueError("source contains duplicate cue_id values")
    covered: dict[int, dict[str, Any]] = {}
    segment_count = 0
    errors: list[str] = []

    sorted_work = sorted(work, key=lambda record: source_ids(record)[0])
    for record in sorted_work:
        try:
            ids = source_ids(record)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for cue_id in ids:
            if cue_id in covered:
                errors.append(f"duplicate source cue_id {cue_id}")
            covered[cue_id] = record
            if cue_id not in source_by_id:
                errors.append(f"unexpected source cue_id {cue_id}")
        if any(cue_id not in source_by_id for cue_id in ids):
            continue
        if ids != list(range(ids[0], ids[-1] + 1)):
            errors.append(f"cue group {ids} is not consecutive")
        try:
            record_start, record_end = record_times(record, ids)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if abs(record_start - float(source_by_id[ids[0]]["start"])) > 0.0005:
            errors.append(f"cue group {ids} changed start")
        if abs(record_end - float(source_by_id[ids[-1]]["end"])) > 0.0005:
            errors.append(f"cue group {ids} changed end")
        segments = record.get("segments")
        if not isinstance(segments, list) or not segments:
            errors.append(f"cue group {ids} has no segments")
            continue
        segment_count += len(segments)
        previous_segment_end = record_start
        for index, segment in enumerate(segments, 1):
            if not isinstance(segment, dict):
                errors.append(f"cue group {ids} segment {index} is not an object")
                continue
            try:
                segment_start, segment_end = segment_times(segment, ids, index)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if segment_start < record_start - 0.0005 or segment_end > record_end + 0.0005:
                errors.append(f"cue group {ids} segment {index} falls outside the group timing")
            if segment_start < previous_segment_end - 0.0005:
                errors.append(f"cue group {ids} segment {index} overlaps the previous segment")
            previous_segment_end = segment_end

    missing = sorted(set(source_by_id) - set(covered))
    if missing:
        errors.append(f"missing source cue_ids: {missing}")
    if sorted(covered) != list(source_by_id):
        errors.append("work records do not form an ordered partition of source cues")
    if errors:
        raise ValueError("\n".join(errors))
    return len(covered), segment_count


def render_srt(work: Sequence[dict[str, Any]]) -> str:
    if not work:
        raise ValueError("reviewed work is empty")
    records = sorted(work, key=lambda record: source_ids(record)[0])
    output: list[str] = []
    subtitle_index = 1
    previous_source_id = 0
    previous_end = 0.0

    for record in records:
        ids = source_ids(record)
        if ids[0] <= previous_source_id:
            raise ValueError(f"source cue order is not increasing at {ids}")
        start, cue_end = record_times(record, ids)
        if start < previous_end - 0.0005 or cue_end <= start:
            raise ValueError(f"invalid or overlapping time range for cue group {ids}")
        segments = record.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ValueError(f"cue group {ids} has no segments")
        previous_segment_end = start
        for index, segment in enumerate(segments, 1):
            if not isinstance(segment, dict):
                raise ValueError(f"cue group {ids} segment {index} is not an object")
            segment_start, segment_end = segment_times(segment, ids, index)
            if segment_start < start - 0.0005 or segment_end > cue_end + 0.0005:
                raise ValueError(f"cue group {ids} segment {index} falls outside the group timing")
            if segment_start < previous_segment_end - 0.0005:
                raise ValueError(f"cue group {ids} segment {index} overlaps the previous segment")
            line_1 = " ".join(segment["line_1"].split())
            line_2 = " ".join(segment["line_2"].split())
            output.extend(
                [
                    str(subtitle_index),
                    f"{format_timestamp(segment_start)} --> {format_timestamp(segment_end)}",
                    line_1,
                    line_2,
                    "",
                ]
            )
            subtitle_index += 1
            previous_segment_end = segment_end
        previous_source_id = ids[-1]
        previous_end = cue_end
    return "\n".join(output)


def parse_srt(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    content = path.read_text(encoding="utf-8-sig").strip()
    if not content:
        return entries
    for block in re.split(r"\n\s*\n", content):
        lines = block.splitlines()
        if len(lines) != 4 or " --> " not in lines[1]:
            raise ValueError(f"malformed SRT block: {block[:120]!r}")
        timing_match = SRT_TIMING_RE.fullmatch(lines[1])
        if timing_match is None:
            raise ValueError(f"malformed SRT timing: {lines[1]!r}")
        entries.append(
            {
                "index": int(lines[0]),
                "start": parse_timestamp(timing_match.group("start")),
                "end": parse_timestamp(timing_match.group("end")),
                "line_1": lines[2].strip(),
                "line_2": lines[3].strip(),
            }
        )
    return entries


def validate_srt(entries: Sequence[dict[str, Any]], media_duration: float | None = None) -> dict[str, Any]:
    if not entries:
        raise ValueError("SRT contains no subtitles")
    errors: list[str] = []
    previous_end = 0.0
    short_entries: list[int] = []
    for expected_index, entry in enumerate(entries, 1):
        if entry["index"] != expected_index:
            errors.append(f"expected index {expected_index}, got {entry['index']}")
        if float(entry["start"]) < previous_end - 0.001:
            errors.append(f"subtitle {expected_index} overlaps the previous subtitle")
        if float(entry["end"]) <= float(entry["start"]):
            errors.append(f"subtitle {expected_index} has non-positive duration")
        if not entry["line_1"] or not entry["line_2"]:
            errors.append(f"subtitle {expected_index} has an empty line")
        if float(entry["end"]) - float(entry["start"]) < 0.8:
            short_entries.append(expected_index)
        previous_end = float(entry["end"])
    if media_duration is not None and entries and previous_end > media_duration + 0.05:
        errors.append("final subtitle ends after the media duration")
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "subtitle_count": len(entries),
        "end": previous_end,
        "short_entry_ids": short_entries,
        "max_line_1_words": max((len(str(entry["line_1"]).split()) for entry in entries), default=0),
        "max_line_2_chars": max((len(str(entry["line_2"])) for entry in entries), default=0),
    }


def command_prepare(args: argparse.Namespace) -> None:
    require_distinct_paths(args.input, args.output, args.manifest)
    selected = select_cues(parse_vtt(args.input), args.start, args.end)
    if not selected:
        raise ValueError("no VTT cues were parsed in the requested range")
    write_jsonl(args.output, selected)
    manifest = build_manifest(args.input, args.output, args.line_1_language, args.line_2_language)
    write_manifest(args.manifest, manifest)
    print(json.dumps({"cues": len(selected), "output": str(args.output), "manifest": str(args.manifest)}))


def command_verify_work(args: argparse.Namespace) -> None:
    require_distinct_paths(args.source, args.manifest, *args.input)
    manifest = read_manifest(args.manifest)
    assert_source_matches_manifest(manifest, args.source)
    covered, segments = verify_work(read_jsonl([args.source]), read_jsonl(args.input))
    print(json.dumps({"source_cues": covered, "segments": segments}))


def command_render(args: argparse.Namespace) -> None:
    require_distinct_paths(args.source, args.manifest, args.output, *args.input)
    manifest = read_manifest(args.manifest)
    assert_source_matches_manifest(manifest, args.source)
    source = read_jsonl([args.source])
    work = read_jsonl(args.input)
    _ = verify_work(source, work)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_srt(work), encoding="utf-8")
    manifest["reviewed_artifacts"] = [
        {"file": path.name, "sha256": file_sha256(path)} for path in args.input
    ]
    manifest["srt_file"] = args.output.name
    manifest["srt_sha256"] = file_sha256(args.output)
    write_manifest(args.manifest, manifest)
    print(json.dumps({"output": str(args.output)}))


def command_validate(args: argparse.Namespace) -> None:
    require_distinct_paths(args.input, args.manifest)
    manifest = read_manifest(args.manifest)
    if args.input.name != manifest.get("srt_file") or file_sha256(args.input) != manifest.get("srt_sha256"):
        raise ValueError("SRT does not match the rendered artifact in the manifest")
    print(json.dumps(validate_srt(parse_srt(args.input), args.media_duration)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Parse VTT cues into an agent work packet")
    prepare.add_argument("--input", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--line-1-language", required=True)
    prepare.add_argument("--line-2-language", required=True)
    prepare.add_argument("--start", type=float, default=0.0)
    prepare.add_argument("--end", type=float, default=float("inf"))
    prepare.set_defaults(func=command_prepare)

    verify = subparsers.add_parser("verify-work", help="Verify agent work against source cue coverage")
    verify.add_argument("--source", type=Path, required=True)
    verify.add_argument("--input", type=Path, nargs="+", required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.set_defaults(func=command_verify_work)

    render = subparsers.add_parser("render", help="Render reviewed bilingual JSONL as SRT")
    render.add_argument("--input", type=Path, nargs="+", required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--manifest", type=Path, required=True)
    render.add_argument("--source", type=Path, required=True)
    render.set_defaults(func=command_render)

    validate = subparsers.add_parser("validate", help="Validate SRT structure and timing")
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--media-duration", type=float)
    validate.set_defaults(func=command_validate)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
