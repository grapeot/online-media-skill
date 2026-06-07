# Download And Transcribe Skill

## Metadata

- **Type**: Workflow
- **Use cases**: Bilibili/YouTube audio download, playlist intake, local media transcription, talk/meeting/speech transcript sidecars
- **Outputs**: local media files in ignored runtime directories, platform metadata sidecars, ASR Markdown or JSONL artifacts

## Goal

Acquire permitted online media and turn it into reusable local artifacts. The result is not a summary or judgment. The result is a file plus metadata and, when requested, a transcript that another agent can inspect later.

## Boundary

This skill may download media the user can access, write metadata, embed local tags, run Qwen ASR, and preserve transcript segments. It must not identify medley source songs, judge whether two recordings match, translate talks, or summarize content. Those are downstream agent workflows.

## Available CLI

From the repo root:

```bash
.venv/bin/python scripts/bilibili_music.py --help
.venv/bin/python scripts/medley_identify.py transcribe --help
```

The current Bilibili downloader preserves the original audio stream where possible, writes `.info.json` sidecars for local debugging, and can tag `.m4a` files for local music library import. Real `.info.json` files are private runtime data because they can include signed CDN URLs, platform headers, browser identifiers, and other scrape context.


## Music Download Routes

### Bilibili short links and HTTP 412

Do not pass `b23.tv` short links directly to the downloader when reproducibility matters. Bilibili can return `HTTP Error 412: Precondition Failed` for generic extractors even when the short link is valid in a browser. Resolve the short link first with a browser user agent, keep only the canonical `BV...` URL, and discard the expanded query string because it can contain share metadata and browser identifiers.

```bash
curl -L -A 'Mozilla/5.0' -I 'https://b23.tv/SHORT_ID'
# Use the Location header's BV id only:
# https://www.bilibili.com/video/BVxxxxxxxxxx/
```

If the canonical BV URL still returns 412, retry with browser cookies only for local/private work:

```bash
.venv/bin/python -m yt_dlp --cookies-from-browser chrome \
  -f bestaudio \
  --write-info-json \
  -o 'library/%(title)s.%(ext)s' \
  'https://www.bilibili.com/video/BVxxxxxxxxxx/'
```

Treat any `.info.json` and expanded Bilibili URLs as private runtime data. They may include signed CDN URLs, cookies, `buvid`, share session IDs, or local browser-derived state. Keep them under ignored runtime directories and never copy them into docs, fixtures, commits, or public issue/PR bodies.

### YouTube / yt-dlp Route

Use YouTube downloads for quick verification and broad availability. Install `yt-dlp`, `ffmpeg`, and `deno`. Deno plus the EJS remote component resolves the current YouTube JavaScript challenge warning.

For bulk song acquisition, use YouTube search as a candidate generator first. Approve candidates only after checking title, artist/channel evidence, duration, description, and version markers. Do not pipe raw `ytsearch` results straight into a downloader.

```bash
yt-dlp --js-runtimes deno --remote-components ejs:github \
  -f "bestaudio" \
  --extract-audio --audio-format mp3 --audio-quality 0 \
  -o "library/%(title)s.%(ext)s" \
  "https://www.youtube.com/watch?v=..."
```

Use this route for matching and inspection. Do not assume the output is lossless even when the upload title says FLAC.

After download, quarantine files whose filename or tags expose `Live`, `伴奏`, `Karaoke`, `Cover`, remix, medley, or playlist markers unless that version was explicitly requested. Accepted files must have title, artist, and embedded cover artwork before import.

### Tidal / streamrip Route

Use Tidal downloads when the user has an active subscription and wants a higher-quality local file for private use. `streamrip` stores OAuth tokens under the user's local Streamrip config directory. Keep those tokens private and outside the repo.

```bash
.venv/bin/python scripts/tidal_download_from_csv.py search-candidates \
  --input source_identification/medley_sources_download_queue.csv \
  --output source_identification/tidal_candidates.csv \
  --sleep 3
# Review tidal_candidates.csv and mark decision=approved for verified rows.
.venv/bin/python scripts/tidal_download_from_csv.py download-approved \
  --candidates source_identification/tidal_candidates.csv \
  --download-dir library/tidal \
  --sleep 5 \
  --resume
```

Do not auto-download from raw search results. Search output can contain covers or misleading titles, such as a candidate where the original artist appears in `desc_title` but the structured Tidal artist is someone else. For example, `林俊杰 - Always Online by A` means the platform artist is `A`, not 林俊杰. Before batch work, keep streamrip conservative: `max_connections = 1` or `2`, `requests_per_minute = 20` or lower, and no parallel agents using the same account.

After a Tidal batch, run a filename or tag QA pass before importing files into a main music library. Search output may omit version qualifiers that appear only after download. Move files with markers such as `Live`, `伴奏`, `Karaoke`, `Cover`, or medley titles into a quarantine directory for manual review instead of mixing them with accepted studio tracks. Then verify title, artist, and embedded cover artwork:

```bash
.venv/bin/python scripts/tidal_download_from_csv.py verify-tags \
  --library-dir library/tidal \
  --output source_identification/tidal_tag_report.csv
```

If Tidal OAuth fails with 403 or `invalid_client`, check for a newer streamrip release first. Some releases may ship a revoked Tidal client ID. Patch only the local virtual environment with private values, never the public repo:

```bash
export STREAMRIP_TIDAL_CLIENT_ID="current-client-id"
export STREAMRIP_TIDAL_CLIENT_SECRET="current-client-secret"
.venv/bin/python scripts/patch_streamrip_tidal.py
```

If lyrics fetching returns 401 while audio access works, continue without embedded lyrics. The helper also changes streamrip's lyrics error handling so this case does not abort the audio download.

## Qwen ASR Setup

The preferred ASR backend is Qwen/Qwen3-ASR through `mlx-qwen3-asr` on Apple Silicon. Installation should stay loose and environment-driven because users may already have a working ASR environment.

If no ASR environment exists, create one with `uv` and install the Qwen ASR package recommended by the current upstream docs. A typical local setup is:

```bash
uv venv
uv pip install mlx-qwen3-asr
```

Then point this project at the Python binary and transcribe script:

```bash
export ONLINE_MEDIA_ASR_PYTHON=/path/to/python-with-qwen-asr
export ONLINE_MEDIA_TRANSCRIBE_SCRIPT=/path/to/transcribe.py
```

The repo does not hard-require one fixed ASR installation path. If `ONLINE_MEDIA_ASR_PYTHON` is unset, the CLI uses the current Python. If `ONLINE_MEDIA_TRANSCRIBE_SCRIPT` is unset, the CLI expects a project-local `scripts/transcribe.py` or a caller-provided `--transcribe-script` once that option is added.

## Acceptance Criteria

- Downloaded media and `.info.json` sidecars are written only under ignored runtime directories.
- Transcript artifacts preserve source file, ASR file, and segment timing when the ASR backend supports it.
- The default workflow is reproducible from local sidecars; downstream agents should not need to redownload media just to inspect metadata.
- Live download and ASR tests are opt-in through environment variables.

## Known Failure Modes

- Bilibili flat playlist metadata can show video IDs instead of titles. The real title may only appear after single-item extraction.
- `yt-dlp --write-info-json` can save signed URLs and headers. Treat those files as private runtime data.
- Platform audio format IDs differ by login status and availability. Prefer declared best-audio behavior over assuming one fixed bitrate.
- Tidal candidate metadata can omit live/accompaniment qualifiers that appear in the downloaded filename. Treat post-download filename/tag QA as part of the acquisition workflow.
- YouTube search ranking is not evidence of correctness. Use it to create a reviewable candidate table, then download approved URLs only.
- Missing title, artist, or cover artwork means the file is not ready for local library import. Fetch artwork from the selected platform metadata when available, then rerun tag verification.
- ASR output may use simplified/traditional variants or misrecognize proper nouns. Preserve raw transcript artifacts so the agent can reason about uncertainty.
