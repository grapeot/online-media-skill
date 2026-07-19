from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bilingual_subtitles import (
    assert_source_matches_manifest,
    build_manifest,
    build_parser,
    file_sha256,
    format_timestamp,
    parse_srt,
    parse_timestamp,
    parse_vtt,
    read_manifest,
    read_jsonl,
    render_srt,
    select_cues,
    validate_srt,
    validate_manifest,
    verify_work,
    write_jsonl,
)


def sample_source() -> list[dict[str, object]]:
    return [
        {"cue_id": 1, "start": 0.1, "end": 1.0, "speaker": "Alex", "source_text": "Welcome."},
        {"cue_id": 2, "start": 1.2, "end": 2.0, "speaker": "Alex", "source_text": "This is"},
        {"cue_id": 3, "start": 2.0, "end": 3.4, "speaker": "Alex", "source_text": "a test."},
    ]


def sample_work() -> list[dict[str, object]]:
    return [
        {
            "source_cue_ids": [1],
            "start": 0.1,
            "end": 1.0,
            "segments": [{"start": 0.1, "end": 1.0, "line_1": "Welcome.", "line_2": "欢迎。"}],
        },
        {
            "source_cue_ids": [2, 3],
            "start": 1.2,
            "end": 3.4,
            "segments": [
                {"start": 1.2, "end": 3.4, "line_1": "This is a test.", "line_2": "这是 AI Builder 测试。"},
            ],
        },
    ]


def test_timestamp_round_trip() -> None:
    assert parse_timestamp("01:02:03.456") == pytest.approx(3723.456)
    assert parse_timestamp("01:02:03,456") == pytest.approx(3723.456)
    assert format_timestamp(3723.456) == "01:02:03,456"


def test_parse_zoom_vtt_and_strip_speaker(tmp_path: Path) -> None:
    vtt = tmp_path / "sample.vtt"
    _ = vtt.write_text(
        "WEBVTT\n\n1\n00:00:00.100 --> 00:00:01.000\nAlex: Tom &amp; Jerry.\n\n"
        "2\n00:01.200 --> 00:02.000 align:start\n<v Alex>This is</v>\n",
        encoding="utf-8",
    )

    cues = parse_vtt(vtt)

    assert cues[0]["speaker"] == "Alex"
    assert cues[0]["source_text"] == "Tom & Jerry."
    assert cues[1]["speaker"] == "Alex"
    assert cues[1]["source_text"] == "This is"


def test_packet_selection_uses_start_time_without_boundary_duplicates() -> None:
    cues = sample_source()
    assert [cue["cue_id"] for cue in select_cues(cues, 0, 2.0)] == [1, 2]
    assert [cue["cue_id"] for cue in select_cues(cues, 2.0, 4.0)] == [3]


def test_parse_vtt_rejects_a_partially_malformed_cue(tmp_path: Path) -> None:
    vtt = tmp_path / "broken.vtt"
    _ = vtt.write_text(
        "WEBVTT\n\n00:00:00.100 --> 00:00:01.000\nValid.\n\n"
        "2\n00:00:bad --> 00:00:02.000\nBroken.\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unrecognized VTT cue block"):
        parse_vtt(vtt)


def test_jsonl_round_trip_preserves_unicode(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    write_jsonl(path, sample_work())
    assert read_jsonl([path]) == sample_work()
    assert "欢迎" in path.read_text(encoding="utf-8")


def test_verify_work_accepts_grouped_source_cues() -> None:
    assert verify_work(sample_source(), sample_work()) == (3, 2)


def test_verify_work_rejects_missing_or_duplicate_cues() -> None:
    duplicate = [sample_work()[0], sample_work()[0]]
    with pytest.raises(ValueError, match="duplicate source cue_id 1"):
        verify_work(sample_source(), duplicate)

    with pytest.raises(ValueError, match="missing source cue_ids"):
        verify_work(sample_source(), [sample_work()[0]])

    with pytest.raises(ValueError, match="source cue list is empty"):
        verify_work([], [])


def test_verify_work_rejects_changed_group_timing() -> None:
    work = sample_work()
    work[1]["start"] = 1.3
    with pytest.raises(ValueError, match="changed start"):
        verify_work(sample_source(), work)


def test_verify_work_rejects_nan_group_timing() -> None:
    work = sample_work()
    work[0]["start"] = "NaN"
    work[0]["end"] = "NaN"
    with pytest.raises(ValueError, match="must have numeric start and end"):
        verify_work(sample_source(), work)


def test_render_preserves_mixed_script_spacing(tmp_path: Path) -> None:
    rendered = render_srt(sample_work())
    assert "这是 AI Builder 测试。" in rendered
    assert "这是AIBuilder测试" not in rendered

    path = tmp_path / "output.srt"
    _ = path.write_text(rendered, encoding="utf-8")
    entries = parse_srt(path)
    report = validate_srt(entries, media_duration=3.5)
    assert report["subtitle_count"] == 2
    assert report["end"] == pytest.approx(3.4)


def test_render_splits_group_time_across_segments() -> None:
    work = sample_work()
    work[1]["segments"] = [
        {"start": 1.2, "end": 2.0, "line_1": "This is", "line_2": "这是"},
        {"start": 2.0, "end": 3.4, "line_1": "a longer test.", "line_2": "一个更长的测试。"},
    ]
    rendered = render_srt(work)
    assert "00:00:01,200 --> 00:00:02,000" in rendered
    assert rendered.rstrip().endswith("一个更长的测试。")


def test_validate_rejects_overlap(tmp_path: Path) -> None:
    path = tmp_path / "bad.srt"
    _ = path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello.\n你好。\n\n"
        "2\n00:00:01,900 --> 00:00:03,000\nAgain.\n再来一次。\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="overlaps"):
        validate_srt(parse_srt(path))


def test_validate_rejects_media_overrun(tmp_path: Path) -> None:
    path = tmp_path / "late.srt"
    _ = path.write_text("1\n00:00:00,000 --> 00:00:03,000\nHello.\n你好。\n", encoding="utf-8")
    with pytest.raises(ValueError, match="after the media duration"):
        validate_srt(parse_srt(path), media_duration=2.5)


def test_parse_srt_rejects_nan_and_out_of_range_time(tmp_path: Path) -> None:
    nan_path = tmp_path / "nan.srt"
    _ = nan_path.write_text("1\n00:00:NaN --> 00:00:NaN\nHello.\n你好。\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed SRT timing"):
        parse_srt(nan_path)

    range_path = tmp_path / "range.srt"
    _ = range_path.write_text("1\n00:99:00,000 --> 00:99:01,000\nHello.\n你好。\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid timestamp"):
        parse_srt(range_path)

    short_path = tmp_path / "short.srt"
    _ = short_path.write_text("1\n00:01,000 --> 00:02,000\nHello.\n你好。\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed SRT timing"):
        parse_srt(short_path)


def test_verify_rejects_non_string_lines_and_nonconsecutive_group() -> None:
    null_line = sample_work()
    null_line[0]["segments"][0]["line_1"] = None  # type: ignore[index]
    with pytest.raises(ValueError, match="line_1 must be a non-empty string"):
        verify_work(sample_source(), null_line)

    crossed = [
        {
            "source_cue_ids": [1, 3],
            "start": 0.1,
            "end": 3.4,
            "segments": [{"start": 0.1, "end": 3.4, "line_1": "Combined.", "line_2": "合并。"}],
        },
        {
            "source_cue_ids": [2],
            "start": 1.2,
            "end": 2.0,
            "segments": [{"start": 1.2, "end": 2.0, "line_1": "Middle.", "line_2": "中间。"}],
        },
    ]
    with pytest.raises(ValueError, match="not consecutive"):
        verify_work(sample_source(), crossed)


def test_manifest_persists_language_order_and_binds_source(tmp_path: Path) -> None:
    vtt = tmp_path / "lesson.vtt"
    source = tmp_path / "lesson.subtitle_source.jsonl"
    _ = vtt.write_text("WEBVTT\n", encoding="utf-8")
    write_jsonl(source, sample_source())
    manifest = build_manifest(vtt, source, "en", "zh-Hans")
    assert manifest == {
        "schema_version": 1,
        "source_vtt_file": "lesson.vtt",
        "source_vtt_sha256": file_sha256(vtt),
        "source_jsonl_file": "lesson.subtitle_source.jsonl",
        "source_jsonl_sha256": file_sha256(source),
        "line_1_language": "en",
        "line_2_language": "zh-Hans",
    }
    validate_manifest(manifest)
    assert_source_matches_manifest(manifest, source)
    _ = source.write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash does not match"):
        assert_source_matches_manifest(manifest, source)
    with pytest.raises(ValueError, match="must differ"):
        build_manifest(vtt, source, "en", "en")


def test_complete_cli_artifact_chain(tmp_path: Path) -> None:
    vtt = tmp_path / "lesson.vtt"
    source = tmp_path / "lesson.subtitle_source.jsonl"
    reviewed = tmp_path / "lesson.subtitle_reviewed.jsonl"
    manifest = tmp_path / "lesson.subtitle_manifest.json"
    srt = tmp_path / "lesson.srt"
    _ = vtt.write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.000\nAlex: Welcome.\n\n"
        "00:01.200 --> 00:03.400\nAlex: This is a test.\n",
        encoding="utf-8",
    )

    prepare_args = build_parser().parse_args(
        [
            "prepare",
            "--input",
            str(vtt),
            "--output",
            str(source),
            "--manifest",
            str(manifest),
            "--line-1-language",
            "en",
            "--line-2-language",
            "zh-Hans",
        ]
    )
    prepare_args.func(prepare_args)
    write_jsonl(
        reviewed,
        [
            {
                "source_cue_ids": [1],
                "start": 0.1,
                "end": 1.0,
                "segments": [{"start": 0.1, "end": 1.0, "line_1": "Welcome.", "line_2": "欢迎。"}],
            },
            {
                "source_cue_ids": [2],
                "start": 1.2,
                "end": 3.4,
                "segments": [
                    {"start": 1.2, "end": 3.4, "line_1": "This is a test.", "line_2": "这是测试。"}
                ],
            },
        ],
    )

    render_args = build_parser().parse_args(
        [
            "render",
            "--source",
            str(source),
            "--manifest",
            str(manifest),
            "--input",
            str(reviewed),
            "--output",
            str(srt),
        ]
    )
    render_args.func(render_args)
    validate_args = build_parser().parse_args(
        ["validate", "--manifest", str(manifest), "--input", str(srt), "--media-duration", "3.5"]
    )
    validate_args.func(validate_args)

    final_manifest = read_manifest(manifest)
    assert final_manifest["srt_sha256"] == file_sha256(srt)
    assert final_manifest["reviewed_artifacts"] == [
        {"file": reviewed.name, "sha256": file_sha256(reviewed)}
    ]


def test_cli_rejects_path_collisions(tmp_path: Path) -> None:
    same = tmp_path / "same.vtt"
    _ = same.write_text("WEBVTT\n", encoding="utf-8")
    args = build_parser().parse_args(
        [
            "prepare",
            "--input",
            str(same),
            "--output",
            str(same),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--line-1-language",
            "en",
            "--line-2-language",
            "zh-Hans",
        ]
    )
    with pytest.raises(ValueError, match="must be distinct"):
        args.func(args)


def test_cli_friendly_json_report_shape() -> None:
    report = validate_srt(
        [
            {
                "index": 1,
                "start": 0.0,
                "end": 0.5,
                "line_1": "Hi.",
                "line_2": "你好。",
            }
        ],
        media_duration=1.0,
    )
    assert report["short_entry_ids"] == [1]
    json.dumps(report)
