from __future__ import annotations

import json
from pathlib import Path

from scripts.medley_identify import (
    build_query_pack,
    build_query,
    is_year_labeled,
    list_year_files,
    parse_segments,
    split_anchor_candidates,
    DEDUPED_COLUMNS,
    NEAR_DUPLICATE_COLUMNS,
    SOURCE_COLUMNS,
    dedupe_entries,
    read_source_entries,
    write_csv,
    write_jsonl,
)


def test_year_labeled_detection(tmp_path: Path) -> None:
    yes = tmp_path / "079_一曲串烧【1998上】.m4a"
    yes_nian_de = tmp_path / "107_你捡到一个来自2011年的mp3.m4a"
    no = tmp_path / "042_冷门歌手.m4a"
    _ = yes.write_bytes(b"")
    _ = yes_nian_de.write_bytes(b"")
    _ = no.write_bytes(b"")

    assert is_year_labeled(yes)
    assert is_year_labeled(yes_nian_de)
    assert not is_year_labeled(no)
    assert list_year_files(tmp_path) == [yes, yes_nian_de]


def test_parse_segments() -> None:
    markdown = """
## Segmented Transcript

[00:19-00:43] 星光落在屋檐上，风把旧梦吹成糖。
[00:43-01:03] 蓝色纸船慢慢摇，月亮躲进玻璃桥。
"""
    segments = parse_segments(markdown)
    assert len(segments) == 2
    assert segments[1].start == "00:43"
    assert "纸船" in segments[1].text


def test_anchor_split_and_query() -> None:
    anchors = split_anchor_candidates("蓝色纸船慢慢摇，月亮躲进玻璃桥。星光落在屋檐上，风把旧梦吹成糖。")
    assert "蓝色纸船慢慢摇" in anchors
    assert build_query("蓝色纸船慢慢摇") == '"蓝色纸船慢慢摇" 歌名'


def test_build_query_pack(tmp_path: Path) -> None:
    audio = tmp_path / "079_一曲串烧【1998上】.m4a"
    _ = audio.write_bytes(b"")
    asr = tmp_path / "asr.md"
    _ = asr.write_text("[00:43-01:03] 蓝色纸船慢慢摇，月亮躲进玻璃桥。\n", encoding="utf-8")

    records = build_query_pack(audio, asr, anchors_per_segment=1)

    assert records[0].segment_id == 1
    assert records[0].anchor == "蓝色纸船慢慢摇"
    assert records[0].query == '"蓝色纸船慢慢摇" 歌名'


def test_write_jsonl(tmp_path: Path) -> None:
    out = tmp_path / "queries.jsonl"
    write_jsonl(out, [{"query": '"蓝色纸船慢慢摇" 歌名'}])

    assert json.loads(out.read_text(encoding="utf-8"))["query"] == '"蓝色纸船慢慢摇" 歌名'



def test_dedupe_sources_expands_and_groups(tmp_path: Path) -> None:
    source = tmp_path / "sources.csv"
    rows = [
        {
            "order": "1",
            "source_file": "a.m4a",
            "asr_file": "a.md",
            "start": "00:00",
            "end": "00:10",
            "song_title": "蓝色纸船",
            "artist": "星光乐队",
            "release_year": "2001",
            "lyric_evidence": "蓝色纸船慢慢摇",
            "source_urls": json.dumps(["https://example.com/blue"], ensure_ascii=False),
            "confidence": "high",
            "needs_review": "false",
            "notes": "",
        },
        {
            "order": "2",
            "source_file": "b.m4a",
            "asr_file": "b.md",
            "start": "00:10",
            "end": "00:20",
            "song_title": "蓝色纸船",
            "artist": "星光乐队",
            "release_year": "",
            "lyric_evidence": "月亮躲进玻璃桥",
            "source_urls": json.dumps(["https://example.com/blue"], ensure_ascii=False),
            "confidence": "medium",
            "needs_review": "false",
            "notes": "repeat",
        },
        {
            "order": "3",
            "source_file": "c.m4a",
            "asr_file": "c.md",
            "start": "00:20",
            "end": "00:30",
            "song_title": "红色风筝 / 白色风筝",
            "artist": "风筝少年 / 风筝少女",
            "release_year": "",
            "lyric_evidence": "红色风筝飞",
            "source_urls": "[]",
            "confidence": "low",
            "needs_review": "true",
            "notes": "boundary",
        },
        {
            "order": "4",
            "source_file": "d.m4a",
            "asr_file": "d.md",
            "start": "00:30",
            "end": "00:40",
            "song_title": "蓝色纸船",
            "artist": "星光合唱团",
            "release_year": "",
            "lyric_evidence": "蓝色纸船慢慢摇",
            "source_urls": "[]",
            "confidence": "medium",
            "needs_review": "false",
            "notes": "artist variant",
        },
    ]
    write_csv(source, SOURCE_COLUMNS, rows)

    entries = read_source_entries(source)
    deduped, near = dedupe_entries(entries)

    assert len(entries) == 5
    assert len(deduped) == 4
    blue = next(row for row in deduped if row["song_title"] == "蓝色纸船" and row["artist"] == "星光乐队")
    assert blue["occurrence_count"] == "2"
    assert blue["best_confidence"] == "high"
    assert json.loads(blue["source_files"]) == ["a.m4a", "b.m4a"]
    assert near == [
        {
            "title_key": "蓝色纸船",
            "song_title": "蓝色纸船",
            "artists": json.dumps(["星光乐队", "星光合唱团"], ensure_ascii=False),
            "dedupe_orders": json.dumps([3, 4]),
            "occurrence_count": "3",
            "notes": "Same normalized title appears with multiple artists; review before bulk download.",
        }
    ]
    assert set(DEDUPED_COLUMNS) == set(deduped[0])
    assert set(NEAR_DUPLICATE_COLUMNS) == set(near[0])
