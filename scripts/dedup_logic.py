"""Deterministic duplicate clustering and canonical selection for music libraries."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

REVIEW_COLUMNS = [
    "cluster_id",
    "cluster_type",
    "title",
    "artist",
    "full_path",
    "library",
    "extension",
    "bytes",
    "duration_sec",
    "has_cover",
    "has_tag_title",
    "has_tag_artist",
    "is_canonical",
    "user_action",
    "canonical_reason",
    "review_notes",
    "artwork_cache_path",
    "version_markers",
]

NEAR_DUPLICATE_COLUMNS = [
    "title_key",
    "title",
    "artist_keys",
    "artists",
    "file_count",
    "sample_paths",
]

FORMAT_SCORE = {
    ".flac": 100,
    ".m4a": 80,
    ".aac": 60,
    ".mp3": 40,
    ".wma": 20,
}

VERSION_MARKER_PATTERN = re.compile(
    r"(live|cover|karaoke|伴奏|串烧|medley|remix|acoustic|demo|instrumental|现场|翻唱)",
    re.IGNORECASE,
)


class ReviewJsonCluster(TypedDict):
    cluster_id: str
    cluster_type: str
    title: str
    artist: str
    members: list[dict[str, str]]


@dataclass(frozen=True)
class InventoryRow:
    library: str
    full_path: str
    relative_path: str
    filename: str
    extension: str
    bytes: int
    title: str
    artist: str
    album: str
    duration_sec: str
    has_cover: bool
    has_tag_title: bool
    has_tag_artist: bool
    tag_source: str
    title_key: str
    artist_key: str
    read_error: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> InventoryRow:
        return cls(
            library=row["library"],
            full_path=row["full_path"],
            relative_path=row["relative_path"],
            filename=row["filename"],
            extension=row["extension"],
            bytes=int(row["bytes"] or 0),
            title=row["title"],
            artist=row["artist"],
            album=row.get("album", ""),
            duration_sec=row.get("duration_sec", ""),
            has_cover=row.get("has_cover", "") == "true",
            has_tag_title=row.get("has_tag_title", "") == "true",
            has_tag_artist=row.get("has_tag_artist", "") == "true",
            tag_source=row.get("tag_source", ""),
            title_key=row["title_key"],
            artist_key=row["artist_key"],
            read_error=row.get("read_error", ""),
        )


def read_inventory(path: Path) -> list[InventoryRow]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [InventoryRow.from_csv_row(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def version_markers(row: InventoryRow) -> str:
    haystack = " ".join([row.title, row.artist, row.filename, row.relative_path])
    matches = sorted({match.group(0).lower() for match in VERSION_MARKER_PATTERN.finditer(haystack)})
    return ",".join(matches)


def canonical_score(row: InventoryRow) -> tuple[int, int, int, int, int]:
    marker_penalty = 1 if version_markers(row) else 0
    format_score = FORMAT_SCORE.get(row.extension, 0)
    tag_score = int(row.has_tag_title) + int(row.has_tag_artist)
    cover_score = int(row.has_cover)
    filename_fallback_penalty = 1 if "filename" in row.tag_source else 0
    return (
        -marker_penalty,
        format_score,
        cover_score,
        tag_score,
        row.bytes - filename_fallback_penalty,
    )


def choose_canonical(rows: list[InventoryRow]) -> tuple[InventoryRow, str]:
    ranked = sorted(rows, key=canonical_score, reverse=True)
    winner = ranked[0]
    reason_parts = [f"format={winner.extension}"]
    if winner.has_cover:
        reason_parts.append("has_cover")
    if winner.has_tag_title and winner.has_tag_artist:
        reason_parts.append("embedded_tags")
    if len({row.library for row in rows}) > 1:
        reason_parts.append("cross_library")
    return winner, "; ".join(reason_parts)


def cluster_inventory(rows: list[InventoryRow]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    exact_groups: dict[tuple[str, str], list[InventoryRow]] = defaultdict(list)
    title_groups: dict[str, list[InventoryRow]] = defaultdict(list)

    for row in rows:
        if row.read_error or not row.title_key or not row.artist_key:
            continue
        exact_groups[(row.title_key, row.artist_key)].append(row)
        title_groups[row.title_key].append(row)

    review_rows: list[dict[str, str]] = []
    near_rows: list[dict[str, str]] = []
    cluster_index = 1

    for (_title_key, _artist_key), members in sorted(exact_groups.items()):
        if len(members) < 2:
            continue
        cluster_id = f"dup-{cluster_index:05d}"
        cluster_index += 1
        libraries = {member.library for member in members}
        extensions = {member.extension for member in members}
        markers = [version_markers(member) for member in members]
        has_markers = any(markers)
        if len(libraries) > 1:
            cluster_type = "cross_library"
        elif len(extensions) > 1:
            cluster_type = "format_duplicate"
        else:
            cluster_type = "exact_duplicate"

        if has_markers:
            cluster_type = "needs_review"

        canonical, reason = choose_canonical(members)
        for member in members:
            is_canonical = member.full_path == canonical.full_path
            review_rows.append(
                {
                    "cluster_id": cluster_id,
                    "cluster_type": cluster_type,
                    "title": member.title,
                    "artist": member.artist,
                    "full_path": member.full_path,
                    "library": member.library,
                    "extension": member.extension,
                    "bytes": str(member.bytes),
                    "duration_sec": member.duration_sec,
                    "has_cover": "true" if member.has_cover else "false",
                    "has_tag_title": "true" if member.has_tag_title else "false",
                    "has_tag_artist": "true" if member.has_tag_artist else "false",
                    "is_canonical": "true" if is_canonical else "false",
                    "user_action": "keep" if is_canonical else "pending",
                    "canonical_reason": reason if is_canonical else "",
                    "review_notes": "",
                    "artwork_cache_path": "",
                    "version_markers": version_markers(member),
                }
            )

    for title_key, members in sorted(title_groups.items()):
        artist_keys = sorted({member.artist_key for member in members if member.artist_key})
        if len(artist_keys) < 2:
            continue
        near_rows.append(
            {
                "title_key": title_key,
                "title": members[0].title,
                "artist_keys": "|".join(artist_keys),
                "artists": "|".join(sorted({member.artist for member in members})),
                "file_count": str(len(members)),
                "sample_paths": "|".join(member.full_path for member in members[:5]),
            }
        )

    return review_rows, near_rows


def summarize_review_rows(review_rows: list[dict[str, str]]) -> dict[str, int]:
    cluster_ids = {row["cluster_id"] for row in review_rows}
    pending_trash = [
        row for row in review_rows if row["is_canonical"] == "false" and row["user_action"] == "pending"
    ]
    needs_review = {row["cluster_id"] for row in review_rows if row["cluster_type"] == "needs_review"}
    return {
        "duplicate_clusters": len(cluster_ids),
        "duplicate_files": len(review_rows),
        "pending_non_canonical": len(pending_trash),
        "needs_review_clusters": len(needs_review),
    }


def artwork_cache_path(cache_dir: Path, full_path: str) -> Path:
    digest = hashlib.sha1(full_path.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{digest}.jpg"


def attach_artwork_paths(review_rows: list[dict[str, str]], cache_dir: Path) -> None:
    for row in review_rows:
        cached = artwork_cache_path(cache_dir, row["full_path"])
        row["artwork_cache_path"] = str(cached) if cached.exists() else ""


def html_escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def write_review_json(path: Path, review_rows: list[dict[str, str]], summary: dict[str, int]) -> None:
    clusters_payload: dict[str, ReviewJsonCluster] = {}
    payload: dict[str, object] = {
        "summary": summary,
        "clusters": clusters_payload,
    }
    for row in review_rows:
        default_cluster: ReviewJsonCluster = {
            "cluster_id": row["cluster_id"],
            "cluster_type": row["cluster_type"],
            "title": row["title"],
            "artist": row["artist"],
            "members": [],
        }
        cluster = clusters_payload.setdefault(row["cluster_id"], default_cluster)
        cluster["members"].append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_review_html(review_rows: list[dict[str, str]], summary: dict[str, int], output_path: Path, review_csv: Path) -> None:
    clusters: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in review_rows:
        clusters[row["cluster_id"]].append(row)

    cards: list[str] = []
    for cluster_id in sorted(clusters):
        members = clusters[cluster_id]
        first = members[0]
        member_cards: list[str] = []
        for member in members:
            artwork = member.get("artwork_cache_path", "")
            img = (
                f'<img src="file://{html_escape(artwork)}" alt="cover" class="cover" />'
                if artwork
                else '<div class="cover placeholder">No Cover</div>'
            )
            canonical_badge = '<span class="badge canonical">Canonical</span>' if member["is_canonical"] == "true" else ""
            marker_badge = (
                f'<span class="badge marker">{html_escape(member["version_markers"])}</span>' if member.get("version_markers") else ""
            )
            member_class = "canonical" if member["is_canonical"] == "true" else ""
            size_kb = int(member["bytes"]) // 1024
            member_cards.append(
                f"""
                <article class="member {member_class}">
                  {img}
                  <div class="meta">
                    <div class="path">{html_escape(member['full_path'])}</div>
                    <div class="facts">{html_escape(member['library'])} · {html_escape(member['extension'])} · {size_kb} KB · cover={html_escape(member['has_cover'])}</div>
                    <div class="actions">user_action={html_escape(member['user_action'])} {canonical_badge} {marker_badge}</div>
                    <div class="reason">{html_escape(member.get('canonical_reason') or member.get('review_notes') or '')}</div>
                  </div>
                </article>
                """
            )
        cards.append(
            f"""
            <section class="cluster" id="{html_escape(cluster_id)}">
              <header>
                <h2>{html_escape(first['title'])} — {html_escape(first['artist'])}</h2>
                <p>{html_escape(cluster_id)} · {html_escape(first['cluster_type'])} · {len(members)} files</p>
              </header>
              <div class="members">{''.join(member_cards)}</div>
            </section>
            """
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Music Library Dedup Review</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; background: #111; color: #eee; }}
    .summary, .instructions, .cluster {{ background: #1b1b1f; border: 1px solid #333; border-radius: 12px; padding: 16px; margin-bottom: 20px; }}
    .summary dl {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; }}
    .members {{ display: grid; gap: 12px; }}
    .member {{ display: grid; grid-template-columns: 96px 1fr; gap: 12px; padding: 12px; border-radius: 10px; background: #24242a; }}
    .member.canonical {{ outline: 2px solid #5b8cff; }}
    .cover {{ width: 96px; height: 96px; object-fit: cover; border-radius: 8px; background: #333; }}
    .cover.placeholder {{ display: flex; align-items: center; justify-content: center; font-size: 12px; color: #aaa; }}
    .path {{ word-break: break-all; font-size: 13px; }}
    .facts, .actions, .reason {{ color: #bbb; font-size: 13px; margin-top: 6px; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; margin-right: 6px; }}
    .badge.canonical {{ background: #274690; color: white; }}
    .badge.marker {{ background: #6a4c33; color: white; }}
    code {{ background: #2d2d34; padding: 2px 6px; border-radius: 6px; }}
  </style>
</head>
<body>
  <section class="summary">
    <h1>Music Library Dedup Review</h1>
    <dl>
      <div><dt>Duplicate clusters</dt><dd>{summary['duplicate_clusters']}</dd></div>
      <div><dt>Duplicate files</dt><dd>{summary['duplicate_files']}</dd></div>
      <div><dt>Pending non-canonical</dt><dd>{summary['pending_non_canonical']}</dd></div>
      <div><dt>Needs review</dt><dd>{summary['needs_review_clusters']}</dd></div>
    </dl>
  </section>
  <section class="instructions">
    <h2>How to approve</h2>
    <p>Edit <code>{html_escape(review_csv)}</code> or the paired JSON file. For each cluster, keep exactly one row with <code>is_canonical=true</code> and <code>user_action=keep</code>. Mark unwanted duplicates as <code>user_action=trash</code>. Leave uncertain rows as <code>pending</code>.</p>
    <p>Do not run apply/trash until you explicitly confirm the reviewed CSV.</p>
  </section>
  {''.join(cards)}
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ = output_path.write_text(html, encoding="utf-8")
