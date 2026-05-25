# AGENTS.md

## Project Boundary

This is a public-ready online media skill project. Keep reusable CLI code, tests, docs, schemas, and fake fixtures in the repo. Keep real media, downloaded platform metadata, full ASR outputs, live search payloads, and user-specific libraries out of git.

English is the working language for public files in this repository. Rewrite repo-facing docs, skills, examples, and comments in English unless a test specifically needs non-English text to exercise parsing behavior.

The core architecture has two contracts:

- CLI contract: deterministic or artifact-producing commands that write structured sidecars.
- Agent contract: AI workflows that consume sidecars, call search tools, and make evidence-backed judgments.

Do not put Tavily search judgment, song identity inference, translation quality judgment, or confidence assignment into the deterministic CLI path.

## Layout

- `docs/prd.md`: product goals and scenarios.
- `docs/rfc.md`: architecture, schemas, and CLI/agent boundary.
- `docs/test.md`: offline, live, and privacy verification strategy.
- `docs/working.md`: changelog and lessons learned. Update it after meaningful changes.
- `skills/`: agent-facing workflow documents.
- `scripts/`: current CLI entry points and compatibility wrappers.
- `tests/`: offline-first tests.

## Environment

Use the project `.venv` if it exists. If not, create it with `uv venv` and install dependencies with `uv pip install -e '.[dev]'`.

Run default tests with:

```bash
.venv/bin/python -m pytest -q
```

## Privacy Rules

Never commit:

- `library/`
- `source_identification/`
- `asr_smoke/`
- real `.m4a`, `.mp3`, `.mp4`, `.wav`, or `.flac` files
- real `.info.json` files from yt-dlp
- signed CDN URLs, cookies, `buvid`, `SESSDATA`, or local absolute paths
- real Tavily payloads or full copyrighted lyric transcripts

Before publishing, run the privacy scan in `docs/test.md`.
