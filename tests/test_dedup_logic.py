from __future__ import annotations

from pathlib import Path

from scripts.dedup_logic import InventoryRow, choose_canonical, cluster_inventory, render_review_html, version_markers


def row(
    *,
    full_path: str,
    title: str,
    artist: str,
    extension: str = ".mp3",
    library: str = "CloudMusic",
    bytes_size: int = 1000,
    has_cover: bool = False,
    tag_source: str = "id3",
) -> InventoryRow:
    return InventoryRow(
        library=library,
        full_path=full_path,
        relative_path=full_path.split("/")[-1],
        filename=full_path.split("/")[-1],
        extension=extension,
        bytes=bytes_size,
        title=title,
        artist=artist,
        album="",
        duration_sec="200",
        has_cover=has_cover,
        has_tag_title=True,
        has_tag_artist=True,
        tag_source=tag_source,
        title_key=title.casefold(),
        artist_key=artist.casefold(),
        read_error="",
    )


def test_choose_canonical_prefers_flac_over_mp3() -> None:
    flac = row(full_path="/a/song.flac", title="Song", artist="Artist", extension=".flac", bytes_size=3000)
    mp3 = row(full_path="/a/song.mp3", title="Song", artist="Artist", extension=".mp3", bytes_size=1000)
    winner, reason = choose_canonical([mp3, flac])
    assert winner.full_path == "/a/song.flac"
    assert "format=.flac" in reason


def test_cluster_inventory_marks_format_duplicate() -> None:
    rows = [
        row(full_path="/a/song.flac", title="Song", artist="Artist", extension=".flac"),
        row(full_path="/a/song.mp3", title="Song", artist="Artist", extension=".mp3"),
    ]
    review_rows, near_rows = cluster_inventory(rows)
    assert len(review_rows) == 2
    assert review_rows[0]["cluster_type"] == "format_duplicate"
    assert sum(row["is_canonical"] == "true" for row in review_rows) == 1
    assert near_rows == []


def test_cluster_inventory_keeps_same_title_diff_artist_separate() -> None:
    rows = [
        row(full_path="/a/one.mp3", title="Rain", artist="Artist A"),
        row(full_path="/b/two.mp3", title="Rain", artist="Artist B"),
    ]
    review_rows, near_rows = cluster_inventory(rows)
    assert review_rows == []
    assert len(near_rows) == 1
    assert "Artist A" in near_rows[0]["artists"]


def test_version_markers_detect_cover_and_live() -> None:
    cover = row(full_path="/a/cover.mp3", title="Song (Cover Artist)", artist="Artist")
    live = row(full_path="/b/live.mp3", title="Song (Live)", artist="Artist")
    assert "cover" in version_markers(cover)
    assert "live" in version_markers(live)


def test_review_html_escapes_csv_values(tmp_path: Path) -> None:
    output = tmp_path / "review.html"
    review_rows = [
        {
            "cluster_id": "dup-<001>",
            "cluster_type": "format_duplicate",
            "title": "<script>alert('title')</script>",
            "artist": "Artist & Co",
            "full_path": "/tmp/<script>alert('path')</script>.mp3",
            "library": "CloudMusic",
            "extension": ".mp3",
            "bytes": "2048",
            "duration_sec": "200",
            "has_cover": "false",
            "has_tag_title": "true",
            "has_tag_artist": "true",
            "is_canonical": "true",
            "user_action": "keep",
            "canonical_reason": "format=<mp3>",
            "review_notes": "",
            "artwork_cache_path": "/tmp/cover\" onerror=\"alert(1).jpg",
            "version_markers": "live<script>",
        }
    ]
    summary = {
        "duplicate_clusters": 1,
        "duplicate_files": 1,
        "pending_non_canonical": 0,
        "needs_review_clusters": 0,
    }

    render_review_html(review_rows, summary, output, tmp_path / "review.csv")

    html = output.read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "onerror=\"alert" not in html
    assert "&lt;script&gt;alert(&#x27;title&#x27;)&lt;/script&gt;" in html
    assert "format=&lt;mp3&gt;" in html
