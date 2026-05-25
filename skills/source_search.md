# Source Search Skill

## Metadata

- **Type**: Workflow
- **Use cases**: find high-quality candidate sources from a song title, lyric fragment, description, or remembered clue
- **Outputs**: candidate list with URLs, metadata evidence, expected quality, and verification plan

## Goal

Find candidate media sources worth downloading or verifying. The output is a ranked candidate set, not an automatic download decision.

## Evidence Priorities

Use source quality in this order when available:

- official artist/channel uploads or licensed platform pages
- label/distributor uploads
- music platform pages with stable metadata
- high-quality user uploads with strong description evidence
- secondary lyric/wiki/forum sources as supporting context only

For each candidate, record why it matches the requested song: title, artist, album, lyric fragment, description, duration, upload source, or other metadata.

## Agent Responsibilities

The agent chooses search terms, checks sources, and decides which candidates are worth passing to the CLI for download/transcription. The CLI should only download or inspect candidates the agent has selected.


## Practical Source Routes

### Route A: YouTube With yt-dlp

Use this route when the goal is fast source verification or broad coverage. Search with exact title plus artist first, then prefer official channels, label channels, or stable lyric/MV uploads. For YouTube, run `yt-dlp` with a JavaScript runtime and the EJS remote component enabled; otherwise YouTube signature and n-challenge solving can silently miss formats.

For bulk work, do not download directly from `ytsearch` results. First collect candidate metadata with title, channel/uploader, duration, view count, description snippet, and URL. Let an AI or human approve rows where the title and artist/channel evidence point to the intended recording, then download only approved URLs. Reject live, karaoke, accompaniment, cover, remix, reaction, medley, and playlist-style candidates unless the source row explicitly wants that version.

```bash
yt-dlp --js-runtimes deno --remote-components ejs:github \
  -f "bestaudio" \
  --extract-audio --audio-format mp3 --audio-quality 0 \
  -o "source_candidates/%(title)s.%(ext)s" \
  "https://www.youtube.com/watch?v=..."
```

Expected quality is usually lossy. This route is good for matching, transcription, and listening checks, but it is not the preferred archive source when a licensed lossless source is available.

After download, run the same filename/tag QA as Route B. Move files with version markers into quarantine rather than mixing them into the accepted directory.

### Route B: Tidal With streamrip

Use this route when the user has authorized Tidal and wants higher-quality local files. Search Tidal by exact title and artist, using alternate language forms when needed: Chinese title/artist, traditional characters, romanized artist, and English catalog title.

Use a two-stage workflow. First, ask the CLI to collect candidates only:

```bash
.venv/bin/python scripts/tidal_download_from_csv.py search-candidates \
  --input source_identification/medley_sources_download_queue.csv \
  --output source_identification/tidal_candidates.csv \
  --cache-dir source_identification/tidal_search_cache \
  --sleep 3
```

Then an AI or human reviews `tidal_candidates.csv` and sets `decision=approved` only for rows where the Tidal candidate is the intended source recording. After review, download only approved IDs:

```bash
.venv/bin/python scripts/tidal_download_from_csv.py download-approved \
  --candidates source_identification/tidal_candidates.csv \
  --download-dir library/tidal \
  --sleep 5 \
  --resume
```

`-q 2` requests 16-bit/44.1 kHz FLAC where available. `-q 3` may request higher-tier Tidal material, but availability depends on account tier, region, and the current Tidal API behavior. Keep streamrip credentials and generated config in the user's private home directory, never in this repo.

Candidate review rules:

- `title_match=true` and `artist_match=true` is a strong candidate, but still inspect `tidal_desc`.
- Simplified/traditional artist variants can make `artist_match=false`; for example `林俊杰` vs `林俊傑` should be reviewed by meaning, not raw string equality.
- Treat `desc_artist` as the platform's structured artist field. A searched artist appearing inside `desc_title` is weaker evidence than a match in `desc_artist`.
- Reject rows where the searched artist appears only in the title but the candidate artist is someone else. For example, `林俊杰 - Always Online by A` means Tidal returned a track whose title is `林俊杰 - Always Online` and whose structured artist is `A`; this should not be approved as the original 林俊杰 recording unless a listening check proves it.
- Prefer official original studio recordings over covers, karaoke, live versions, medleys, and "翻自/Cover" uploads unless the source row explicitly wants that version.
- If all candidates are weak, leave `decision` blank and change the search query manually: try traditional characters, English catalog title, romanized artist, album title, or lyric anchor.

After download, inspect filenames or audio metadata for version markers such as `Live`, `伴奏`, `Karaoke`, `Cover`, or medley titles. Tidal search descriptions can omit these details even when the downloaded track filename exposes them. Quarantine those files outside the accepted library and keep the source row unresolved for another search pass.

Observed local experiment on 2026-05-24:

| Song | YouTube result | Tidal result |
|---|---:|---:|
| 张宇 / Phil Chang - 雨一直下 / Rain Keeps Falling | 7.11 MB MP3, ~208 kbps, 48 kHz | 35.83 MB FLAC, ~1035 kbps, 44.1 kHz |
| 朴树 - New Boy | 6.77 MB MP3, ~251 kbps, 48 kHz | 26.94 MB FLAC, ~1015 kbps, 44.1 kHz |
| 王菲 - 约定 | 7.66 MB MP3, ~239 kbps, 48 kHz | 22.45 MB FLAC, ~709 kbps, 44.1 kHz |

If streamrip fails before search with a Tidal OAuth `invalid_client` or 403 error, treat that as a local streamrip client credential issue, not a user subscription failure. Prefer upgrading streamrip first. If the current release still ships revoked credentials, patch only the local virtual environment with `scripts/patch_streamrip_tidal.py`; never commit client credentials or Tidal OAuth tokens.

```bash
export STREAMRIP_TIDAL_CLIENT_ID="current-client-id-from-private-notes-or-upstream-issue"
export STREAMRIP_TIDAL_CLIENT_SECRET="current-client-secret-from-private-notes-or-upstream-issue"
.venv/bin/python scripts/patch_streamrip_tidal.py --dry-run
.venv/bin/python scripts/patch_streamrip_tidal.py
```

If streamrip fails on the Tidal lyrics endpoint with `401 Unauthorized` while track search and audio access work, skip lyrics sidecars and continue with audio verification. The helper patches streamrip's lyrics failure handling so a lyrics endpoint error is logged instead of aborting the audio download.

### Route B Rate Limits

Tidal does not publish a stable CLI scraping quota for this use case. Use conservative operator limits instead of maximizing throughput:

- Set streamrip config `downloads.max_connections` to `1` or `2` for batch runs.
- Set `downloads.requests_per_minute` to `20` or lower when downloading many tracks.
- Sleep 3-10 seconds between individual `rip id tidal track ...` calls if orchestrating from a script.
- Download in small batches, for example 20-50 tracks, then pause and inspect failures before continuing.
- Do not run parallel agents against the same Tidal account. One account, one downloader process.
- Treat repeated `401`, `403`, `429`, or sudden search failures as a stop signal. Pause rather than retrying aggressively.

This route is for private local use with the user's authorized account. Do not redistribute downloaded files.

## Output Schema

Recommended JSON fields:

```json
{
  "query": "invented song clue",
  "candidates": [
    {
      "url": "https://example.com/watch?v=fake",
      "title": "Example Candidate",
      "artist": "Example Artist",
      "source_type": "official|licensed|user|secondary",
      "evidence": "Why this candidate may match",
      "expected_quality": "high|medium|low",
      "needs_download_verification": true
    }
  ]
}
```

## Known Failure Modes

- Search engines can surface lyric pages before actual media sources. Keep lyric pages as evidence, not download targets.
- Reuploads often have wrong titles or misleading descriptions. Verify with transcript, duration, thumbnail, and metadata when possible.
- Tidal search metadata can be cleaner than the downloaded track metadata. A candidate may look like `天下 by 张杰` in search output but download as `天下 (Live)`. Run post-download filename or tag QA before treating the batch as accepted.
- YouTube `ytsearch` should be treated as candidate discovery, not selection. Search ranking often surfaces lyric videos, unofficial uploads, or user compilations before the best source.
- A high-quality source for listening may still be unsuitable for redistribution. Keep downloads local and within the user's access rights.
