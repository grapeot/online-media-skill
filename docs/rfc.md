# Online Media Skill RFC

## Status

Draft. This RFC replaces the first `medley_identify.py` prototype boundary, where the CLI both called Tavily and inferred song identity.

## Decision

Use a two-contract architecture:

- **CLI contract:** artifact-producing commands that transform inputs into structured files.
- **Agent contract:** workflows that consume those files, call search tools, make evidence-backed judgments, and write final deliverables.

The CLI may run ASR because ASR is a media transformation that produces a reusable artifact. The CLI should not decide which song a lyric belongs to, whether a source is trustworthy, or whether two recordings are the same song.

## Rationale

The first medley smoke test exposed the failure mode directly. Tavily's aggregate answer can confidently name a song while the returned snippets do not actually support the lyric anchor. If the CLI turns that answer into `confidence=high`, downstream users inherit a judgment that looks deterministic but is actually an unverified AI/search conclusion.

The cleaner design mirrors mature media tools:

- `yt-dlp` writes and reloads `.info.json` sidecars.
- Whisper separates transcription from result writers.
- faster-whisper returns typed segment objects and leaves formatting to callers.
- AcoustID-style workflows separate local fingerprints from remote lookup.
- Search CLIs keep raw response formatting separate from interpretation.

## Proposed Project Layout

```text
online-media-skill/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docs/
│   ├── prd.md
│   ├── rfc.md
│   ├── test.md
│   └── working.md
├── skills/
│   ├── online_media.md
│   ├── download_and_transcribe.md
│   ├── medley_source_identification.md
│   ├── media_metadata.md
│   └── source_search.md
├── scripts/
│   ├── bilibili_music.py
│   └── medley_identify.py
├── src/
│   └── online_media_skill/
└── tests/
```

The project directory is `adhoc_jobs/online_media_skill/`. Keep runtime media libraries and generated artifacts in ignored local directories inside that project.

## CLI Commands

### Media Download

`bilibili_music.py` remains a deterministic media operation:

- `list` playlist entries.
- `download` audio into a local library.
- write platform metadata sidecars.
- tag `.m4a` files for local music library import.
- `verify` existing tags.

The public repo must not include downloaded media or real platform info JSON.

### Medley and Transcript Preparation

`medley_identify.py` should expose deterministic preparation commands:

- `list-year-files`: list files whose names match configured year patterns.
- `transcribe`: run Qwen ASR and write transcript Markdown.
- `query-pack`: write JSONL records containing segment metadata, anchor text, and suggested search queries.

`identify` was removed from the public CLI. Final source identification belongs in the agent workflow. If a future deterministic finalizer is needed, it should consume an externally reviewed evidence file rather than calling search or assigning confidence internally.

## Sidecar Schemas

### `segments.jsonl`

```json
{"source_file":"media/example.m4a","asr_file":"transcripts/example.md","segment_id":1,"start":"00:43","end":"01:03","text":"Blue paper boats drift slowly under the glass bridge."}
```

### `anchor_queries.jsonl`

```json
{"source_file":"media/example.m4a","asr_file":"transcripts/example.md","segment_id":1,"start":"00:43","end":"01:03","anchor":"Blue paper boats drift slowly","query":"\"Blue paper boats drift slowly\" song title"}
```

### Agent Final CSV

```text
order,source_file,asr_file,start,end,song_title,artist,release_year,lyric_evidence,source_urls,confidence,needs_review,notes
```

The final CSV is an agent artifact, not a deterministic CLI artifact, unless it is generated from a reviewed evidence file.

## Agent Contract

The agent reads query packs and decides search strategy. Tavily `answer` is a hint, not evidence. A `high` confidence music match requires source snippets or extracted page text to support both the lyric anchor and the song identity. Aggregate answers without supporting snippets should be `low` or `needs_review=true`.

For talks and meetings, the agent reads transcript sidecars and produces translation, summary, action items, or topic indexes. Those outputs must cite segment ranges when possible.

For candidate song verification, the agent may ask the CLI to download/transcribe candidates, but the same-song judgment remains in the agent layer and must cite lyrics, metadata, or description evidence.

## Testing Strategy

Default tests are offline and fixture-based. They cover filename detection, ASR Markdown parsing, anchor generation, JSONL writing, and deterministic metadata formatting.

Live tests are opt-in:

- `ONLINE_MEDIA_ENABLE_LIVE_DOWNLOADS=1` for yt-dlp/Bilibili tests.
- `ONLINE_MEDIA_ENABLE_LIVE_ASR=1` for Qwen ASR tests.
- `ONLINE_MEDIA_ENABLE_LIVE_SEARCH=1` for Tavily/search workflow tests.

The default test suite must pass without API keys, network, downloaded media, or installed ASR model weights.

## Privacy Boundary

Public files may include fake fixtures, short invented transcripts, schemas, docs, and code. Public files must not include real `.m4a`, platform `.info.json`, signed CDN URLs, cookies, browser fingerprints, real local absolute paths, full real lyric transcripts, or live search payloads.

Private workspace skills may point to local media libraries. Public repo skills should say that private media libraries live outside the repository.
