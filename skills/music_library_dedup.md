# Music Library Dedup Skill

## Metadata

- **Type**: Workflow
- **Use cases**: inventory local music libraries, cluster duplicate tracks, pick canonical copies, and produce a human-review artifact before trashing files
- **Scope**: `~/Music/CloudMusic` and `~/Music/Music` only
- **Outputs**: inventory CSV, survey markdown, review CSV/JSON, HTML visualization

## Goal

Find duplicate songs across the user's local music libraries using embedded audio tags, choose a deterministic canonical copy per duplicate cluster, and stop for explicit human approval before any file is trashed.

Success means the operator can inspect every duplicate cluster with artwork and file metadata, edit a machine-readable review file, and only then approve an apply step.

## Boundary

This workflow does:

- scan permitted local library folders
- read embedded tags through the CLI
- cluster exact `(title, artist)` duplicates after normalization
- propose one canonical file per cluster
- export review artifacts for human approval

This workflow does not:

- scan staging download folders such as `library/tidal` or `library/youtube`
- auto-trash or move files without an explicit reviewed approval step
- merge same-title different-artist groups automatically
- decide cover/live/karaoke/medley variants are equivalent to studio versions

The agent may help interpret ambiguous clusters, but canonical changes and trash decisions belong to the user until they confirm the reviewed CSV.

## Available CLI

Run from the project root:

```bash
.venv/bin/python scripts/music_library_dedup.py read-tags \
  --roots ~/Music/CloudMusic ~/Music/Music \
  --output source_identification/music_library_inventory.csv

.venv/bin/python scripts/music_library_dedup.py survey \
  --inventory source_identification/music_library_inventory.csv \
  --roots ~/Music/CloudMusic ~/Music/Music \
  --output source_identification/music_library_survey.md

.venv/bin/python scripts/music_library_dedup.py build-review \
  --inventory source_identification/music_library_inventory.csv \
  --review-csv source_identification/music_library_dedup_review.csv \
  --review-json source_identification/music_library_dedup_review.json \
  --near-csv source_identification/music_library_near_duplicates.csv \
  --html source_identification/music_library_dedup_review.html
```

`read-tags` is the metadata inventory step. `survey` summarizes folder layout and tag coverage from that inventory. `build-review` creates duplicate clusters, canonical recommendations, artwork cache files, and the HTML review page.

Do not implement or run apply/trash until the user explicitly confirms the reviewed CSV.

## Review Artifacts

Primary machine-readable file:

```text
source_identification/music_library_dedup_review.csv
```

Important columns:

- `cluster_id`: duplicate group identifier
- `cluster_type`: `format_duplicate`, `cross_library`, `exact_duplicate`, or `needs_review`
- `full_path`: absolute local path
- `is_canonical`: exactly one `true` row per duplicate cluster
- `user_action`: `keep`, `trash`, or `pending`
- `canonical_reason`: why the CLI chose the canonical row
- `artwork_cache_path`: cached cover image used by the HTML review page

Near-duplicate groups with the same normalized title but different artists are written separately to:

```text
source_identification/music_library_near_duplicates.csv
```

Those rows are for manual inspection only. Do not trash them from the duplicate review CSV.

## Canonical Selection Policy

The CLI uses a deterministic ranking inside each exact duplicate cluster:

1. prefer non-live/non-cover/non-karaoke files
2. prefer higher-quality formats: FLAC > M4A > AAC > MP3 > WMA
3. prefer embedded cover art
4. prefer embedded title and artist tags over filename fallback
5. prefer larger files when other signals tie

If version markers such as `Live`, `Cover`, `伴奏`, or `串烧` appear, the cluster is marked `needs_review` even when title and artist match exactly.

## Human Approval Loop

The workflow must stop before destructive action.

1. Open `source_identification/music_library_dedup_review.html`.
2. Inspect each cluster's artwork, format, library location, and canonical recommendation.
3. Edit `music_library_dedup_review.csv` or the paired JSON when the proposed canonical file is wrong.
4. Set unwanted duplicates to `user_action=trash`.
5. Leave uncertain rows as `user_action=pending`.
6. Tell the agent explicitly when the reviewed CSV is approved.

Only after that explicit approval may a future `apply` command trash non-canonical rows marked `user_action=trash`. That apply step is out of scope until the user confirms the review artifact.

## Acceptance Criteria

- Inventory CSV contains `full_path`, embedded tag fields, normalized keys, and tag coverage flags for every scanned audio file.
- Survey markdown describes both library roots, top-level folder buckets, extension counts, and tag coverage totals.
- Review CSV contains one row per duplicate file and exactly one canonical row per duplicate cluster.
- Same-title different-artist groups appear only in the near-duplicate CSV, not in the auto-trash review CSV.
- HTML review page renders cluster summaries, member paths, cover art when available, and points the user to the editable CSV.
- No trash/move command runs during the review generation phase.

## Known Failure Modes

- Filename fallback can invent title/artist pairs when embedded tags are missing. Treat `has_tag_title=false` or `has_tag_artist=false` rows as lower-confidence inventory entries.
- Apple Music and CloudMusic use different on-disk layouts. Cross-library duplicates are valid clusters, but the canonical choice may still need manual correction.
- Embedded cover art extraction can fail even when `has_cover=true`. The HTML page falls back to a placeholder instead of blocking review.
- Inventory and review CSVs contain local absolute paths and must stay in ignored runtime directories such as `source_identification/`.
