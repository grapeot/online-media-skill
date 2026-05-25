# Media Metadata Skill

## Metadata

- **Type**: Workflow
- **Use cases**: fill local audio metadata after download, verify tags before importing into a music library
- **Outputs**: tagged local media files and verification JSON

## Goal

Make downloaded audio usable in a local music library by filling stable metadata: title, artist, album, album artist, track number, year, genre, comment, and cover art.

## Boundary

This skill can use platform metadata and thumbnails to fill local tags. It should not decide the true original artist of a medley source song. For medleys, the downloaded file's artist is the uploader/performer; individual source-song artists belong in the medley identification output.

## Available CLI

```bash
.venv/bin/python scripts/bilibili_music.py --verify-only library/example.m4a
.venv/bin/python scripts/tidal_download_from_csv.py verify-tags --library-dir library/tidal
.venv/bin/python scripts/metadata_resync.py --help
```

The downloader writes MP4 tags through `mutagen` rather than relying only on `yt-dlp --embed-metadata`, because iPhone/Apple Music import needs predictable title, artist, album, track, comment, and cover fields.

For Tidal and YouTube batch acquisition, post-download metadata verification is required before import. Accepted audio must have title, artist, and embedded cover artwork. If any of those fields are missing, fetch artwork from the selected platform metadata or quarantine the file until it can be corrected.

Apple Music and iOS library sync should use Apple-compatible containers. Do not treat FLAC as an import-ready final format for that path. Convert accepted FLAC sources to ALAC `.m4a`, then explicitly write MP4 tags and artwork after conversion. Keep the source FLAC files in the private runtime library unless the user asks to delete archive copies.

Album tags should describe the real release: studio album, soundtrack, EP, or single. Do not use workflow placeholders such as `Online Media Skill YouTube Sources`, YouTube channel names, or playlist names as album tags. If the album cannot be verified, leave it unresolved in the plan instead of inventing a value.

## Acceptance Criteria

- `title`, `artist`, `album_artist`, and `has_cover` are present when platform metadata provides enough information.
- `album` is verified against a music source or left unresolved for review; placeholder workflow names are not accepted.
- Tidal/YouTube source batches pass `verify-tags` or an equivalent tag report with zero `missing_metadata` rows before import.
- Playlist imports include track numbers when order is known.
- `comment` retains a stable source identifier such as a video ID and canonical webpage URL.
- Verification output is machine-readable JSON.

## Album Lookup Practice

For batch repair, generate a candidate CSV first, then have agents fill a researched album map with `album`, `album_artist`, `year`, `confidence`, and `evidence_url`. Public sources with useful coverage include MusicBrainz release or recording pages, Apple Music/iTunes, Deezer, KKBOX, Wikipedia, Baidu Baike, and official MV descriptions. Prefer sources that name both the track and the release. Mark ambiguous live, cover, soundtrack, compilation, or unknown-artist cases as `medium` or `unresolved` rather than forcing a studio-album guess.

For large album maps, run one smoke batch first. Validate that the plan reports the expected mix of `ready`, `already_ok`, and `needs_album`; apply only that small batch; then submit parallel research tasks for the remaining slices. Parallel agents should write researched maps, not mutate audio files. The main thread owns the final merge, plan, dry-run, apply, and tag verification.

`scripts/metadata_resync.py` keeps repair operations plan/apply separated:

```bash
.venv/bin/python scripts/metadata_resync.py plan-youtube-albums \
  --candidates source_identification/youtube_album_tag_repair_candidates.csv \
  --album-map source_identification/album_research_merged.csv \
  --output source_identification/youtube_album_repair_plan.csv

.venv/bin/python scripts/metadata_resync.py apply-youtube-albums \
  --plan source_identification/youtube_album_repair_plan.csv \
  --output source_identification/youtube_album_repair_apply_log.csv
```

Omit `--apply` for dry-run. Add `--apply` only after reviewing the generated plan.

For accepted Tidal FLAC sources intended for Apple Music or iOS sync, convert to ALAC M4A and then resync the managed music library through a separate plan/apply step:

```bash
.venv/bin/python scripts/metadata_resync.py plan-tidal-alac \
  --library-dir library/tidal \
  --output-dir library/import_ready/tidal_m4a \
  --output source_identification/tidal_alac_convert_plan.csv

.venv/bin/python scripts/metadata_resync.py convert-tidal-alac \
  --plan source_identification/tidal_alac_convert_plan.csv \
  --source-root library/tidal \
  --output-root library/import_ready/tidal_m4a \
  --output source_identification/tidal_alac_convert_log.csv

.venv/bin/python scripts/metadata_resync.py plan-cloudmusic-resync \
  --convert-log source_identification/tidal_alac_convert_log.csv \
  --output source_identification/cloudmusic_m4a_resync_plan.csv

.venv/bin/python scripts/metadata_resync.py apply-cloudmusic-resync \
  --plan source_identification/cloudmusic_m4a_resync_plan.csv \
  --source-root library/import_ready/tidal_m4a \
  --cloudmusic-dir ~/Music/CloudMusic \
  --output source_identification/cloudmusic_m4a_resync_log.csv
```

Review each plan before adding `--apply`. The root arguments bind apply steps to approved private source, staging, and destination directories; pass custom roots whenever the plan was generated with custom `--library-dir`, `--output-dir`, or `--cloudmusic-dir` values. After the final apply, inventory the destination library and confirm there are no workflow placeholder albums, no read errors, and no missing title/artist/album fields in the repaired target set.

## Known Failure Modes

- Thumbnails may be WebP or another format even when MP4 cover embedding expects JPEG-compatible data. Verify real files after tagging.
- Platform uploader is not necessarily the original song artist.
- Re-running downloads can skip files when `.m4a` and `.info.json` already exist. Use explicit cleanup or force behavior when retagging is required.
- `ffmpeg` can move audio correctly while losing or remapping container-specific metadata. Read FLAC/Vorbis tags first, convert to ALAC, then write MP4 atoms explicitly and verify the result.
