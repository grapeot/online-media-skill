# Test Strategy

## Default Offline Tests

The default test suite must run without network, API keys, ASR model downloads, or local media files. It should cover deterministic logic only:

- year-labeled filename detection
- safe stem generation
- ASR Markdown segment parsing
- lyric anchor splitting
- query pack generation
- JSONL/CSV writer behavior
- mocked metadata/tag parsing where possible
- audio tag normalization, inventory record building, and `read-tags` CSV export
- VTT parsing and non-overlapping packet boundaries
- grouped source-cue coverage, explicit segment timing, and language-manifest invariants
- bilingual SRT rendering, mixed-script spacing, and structural validation

Run from the project root:

```bash
.venv/bin/python -m pytest -q
```

If `.venv` does not exist, create it with `uv venv` and install dependencies with `uv pip install -e '.[dev]'`.

### Offline test map

| Area | Test file | What it verifies |
|------|-----------|------------------|
| Medley source identification | `tests/test_medley_identify.py` | year-labeled filenames, segment parsing, anchor/query-pack generation, source CSV dedupe |
| Audio tag reading | `tests/test_audio_tags.py` | `normalize_key`, filename parsing, MP3/ID3 reads, FLAC/M4A reader dispatch, filename fallback, inventory rows, non-audio skips |
| Music library CLI | `tests/test_music_library_dedup.py` | `read-tags` parser wiring, missing-root handling, `build-review` parser wiring |
| Music library dedupe logic | `tests/test_dedup_logic.py` | canonical ranking, duplicate clustering, near-duplicate separation, version-marker detection |
| Metadata resync CLI | `tests/test_metadata_resync.py` | dry-run parser wiring, placeholder album rejection, MP3 album writing, researched-album plan generation, already-fixed row handling |
| Bilingual subtitles | `tests/test_bilingual_subtitles.py` | VTT parsing, packet boundaries, JSONL coverage, grouped cues, SRT rendering, mixed-script spacing, overlap and duration checks |

Tag-reading offline tests use synthetic fixtures rather than real audio streams:

- MP3 coverage writes ID3 tags directly with `ID3.save()`; this exercises the ID3-only fallback path in `_read_mp3_tags`.
- FLAC and M4A coverage monkeypatch `_read_flac_tags` and `_read_mp4_tags` so tests stay fast and do not depend on generating valid compressed audio containers offline.

## Live Integration Tests

Live tests are opt-in because they touch network services, platform media, large ASR models, or external APIs.

- `ONLINE_MEDIA_ENABLE_LIVE_DOWNLOADS=1`: allow yt-dlp/Bilibili download tests.
- `ONLINE_MEDIA_ENABLE_LIVE_ASR=1`: allow Qwen ASR tests.
- `ONLINE_MEDIA_ENABLE_LIVE_SEARCH=1`: allow Tavily/search workflow tests.

Live tests should use the smallest possible media sample and write outputs under ignored runtime directories.

There is no committed live test yet for local library inventory. Manual verification against a private library is expected before trusting a full `read-tags` run on `~/Music/CloudMusic` and `~/Music/Music`.

## Manual QA

For media download/tagging, manually verify that a downloaded `.m4a` can be opened locally and has title, artist, album, track, and cover metadata.

For medley identification, manually inspect final agent CSV rows with `confidence=high` and confirm that each row has source text supporting both lyric evidence and song identity.

For bilingual subtitles, run a short pilot before full processing. Inspect language order, terminology, sentence boundaries, translation alignment, short display intervals, and packet boundaries. Treat source wording as the baseline: line breaking and punctuation may improve, but the pilot must not paraphrase, summarize, remove meaningful repetitions or false starts, or turn uncertain speech into a definite claim.

At batch scale, have each packet worker list every non-punctuation source-language correction. After merging, run a separate fidelity audit against source JSONL and independent ASR evidence. Keep this separate from readability QA so pressure to eliminate fragments or short display intervals does not silently rewrite the transcript. Spot-check negation, uncertainty, self-correction, cross-speaker handoffs, and translations of technical action direction.

After rendering, run `bilingual-subtitles validate` with the probed media duration and confirm the final subtitle does not extend beyond the media. Verify the SRT loads in the target player. If FFmpeg lacks the libass `subtitles` filter, mux a short MP4 with `-c:s mov_text` and confirm the video, audio, and subtitle streams with `ffprobe`.

For local music-library inventory, run:

```bash
.venv/bin/python scripts/music_library_dedup.py read-tags \
  --roots ~/Music/CloudMusic ~/Music/Music \
  --output source_identification/music_library_inventory.csv

.venv/bin/python scripts/music_library_dedup.py survey \
  --inventory source_identification/music_library_inventory.csv \
  --roots ~/Music/CloudMusic ~/Music/Music \
  --output source_identification/music_library_survey.md

.venv/bin/python scripts/music_library_dedup.py build-review \
  --inventory source_identification/music_library_inventory.csv
```

Manual checks after a real inventory run:

- `files=` count is plausible for both library roots.
- `read_errors=0`, or any non-zero count is investigated file-by-file.
- Spot-check rows with `has_tag_title=false` or `has_tag_artist=false` and confirm filename fallback is acceptable.
- Confirm `full_path`, `title_key`, and `artist_key` look sane before using the CSV for duplicate clustering.

Existing tag QA commands remain valid for download batches:

```bash
.venv/bin/python scripts/tidal_download_from_csv.py verify-tags --library-dir library/tidal
.venv/bin/python scripts/bilibili_music.py --verify-only library/example.m4a
```

`verify-tags` checks presence only. `read-tags` exports full metadata sidecars for deduplication work.

For Apple Music or iOS import, convert accepted FLAC files to ALAC `.m4a` before adding them to the managed music library. Use dry-run planning first:

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
```

Only add `--apply` after reviewing the plan. `--source-root` and `--output-root` bind the apply step to the approved private source and staging directories so stale or edited plans cannot overwrite arbitrary paths. After conversion, verify the generated `.m4a` files still have title, artist, album, album artist, track/date when available, and cover artwork.

For CloudMusic resync after ALAC conversion, plan and apply separately:

```bash
.venv/bin/python scripts/metadata_resync.py plan-cloudmusic-resync \
  --convert-log source_identification/tidal_alac_convert_log.csv \
  --cloudmusic-dir ~/Music/CloudMusic \
  --output source_identification/cloudmusic_m4a_resync_plan.csv

.venv/bin/python scripts/metadata_resync.py apply-cloudmusic-resync \
  --plan source_identification/cloudmusic_m4a_resync_plan.csv \
  --source-root library/import_ready/tidal_m4a \
  --cloudmusic-dir ~/Music/CloudMusic \
  --output source_identification/cloudmusic_m4a_resync_log.csv
```

Review the plan before adding `--apply`. The apply command recomputes the current CloudMusic action and rejects rows outside `--source-root` or `--cloudmusic-dir`. After applying, regenerate a private inventory under `source_identification/` and verify there are no read errors, repaired targets no longer use workflow placeholder albums, and converted `.m4a` files still carry artwork.

## Public Repo Privacy Check

Before publishing or committing a public-ready checkpoint, run a privacy scan from the project root:

```bash
rg -n "/Users/|https://upos|deadline=|upsig=|SESSDATA=|bili_jct=|buvid=[A-Za-z0-9-]+|TAVILY_API_KEY=[A-Za-z0-9_]{20,}" . --glob '!docs/test.md'
```

Expected result for public files is zero matches. Runtime directories are ignored and should not be staged.

For Bilibili short-link troubleshooting, do not commit expanded `b23.tv` redirect URLs. Keep only canonical `https://www.bilibili.com/video/BV.../` examples in public docs. Expanded redirect URLs can contain `buvid`, `share_session_id`, `mid`, `up_id`, and other private or user-specific tracking parameters.

Inventory CSVs under `source_identification/` contain local absolute paths and must stay out of git.
