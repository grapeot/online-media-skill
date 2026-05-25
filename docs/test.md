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

Run from the project root:

```bash
.venv/bin/python -m pytest -q
```

If `.venv` does not exist, create it with `uv venv` and install dependencies with `uv pip install -e '.[dev]'`.

## Live Integration Tests

Live tests are opt-in because they touch network services, platform media, large ASR models, or external APIs.

- `ONLINE_MEDIA_ENABLE_LIVE_DOWNLOADS=1`: allow yt-dlp/Bilibili download tests.
- `ONLINE_MEDIA_ENABLE_LIVE_ASR=1`: allow Qwen ASR tests.
- `ONLINE_MEDIA_ENABLE_LIVE_SEARCH=1`: allow Tavily/search workflow tests.

Live tests should use the smallest possible media sample and write outputs under ignored runtime directories.

## Manual QA

For media download/tagging, manually verify that a downloaded `.m4a` can be opened locally and has title, artist, album, track, and cover metadata.

For medley identification, manually inspect final agent CSV rows with `confidence=high` and confirm that each row has source text supporting both lyric evidence and song identity.

## Public Repo Privacy Check

Before publishing or committing a public-ready checkpoint, run a privacy scan from the project root:

```bash
rg -n "/Users/|https://upos|deadline=|upsig=|SESSDATA=|bili_jct=|buvid=[A-Za-z0-9-]+|TAVILY_API_KEY=[A-Za-z0-9_]{20,}" . --glob '!docs/test.md'
```

Expected result for public files is zero matches. Runtime directories are ignored and should not be staged.
