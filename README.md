# Online Media Skill

Public-ready CLI and agent workflows for online media processing.

The core idea is simple: the CLI produces reusable artifacts, and AI agents make the judgments. Downloading media, writing metadata, running ASR, parsing transcript segments, and generating query packs are CLI responsibilities. Searching the web, deciding whether a lyric belongs to a song, translating a talk, or judging whether two recordings match are agent responsibilities.

## Use Cases

- Identify source songs inside music medleys from ASR lyric anchors.
- Download and transcribe online talks, meetings, and speeches for later translation or summarization.
- Search for candidate song recordings, transcribe or inspect them, and let an agent verify the match with evidence.
- Produce reviewed bilingual SRT subtitles from English, Chinese, or mixed-language talks while preserving auditable transcript sidecars.

## Setup

For a human operator:

```bash
uv venv
uv pip install -e '.[dev]'
```

The default test suite is offline:

```bash
.venv/bin/python -m pytest -q
```

Live workflows require local media tools, optional API keys, and explicit opt-in environment variables. See `.env.example` and `docs/test.md`.

### Optional Music Source Tools

For source-song verification and private local listening checks, two routes are useful:

- YouTube route: `yt-dlp` + `ffmpeg` + `deno`; use `--js-runtimes deno --remote-components ejs:github` for current YouTube extraction.
- Tidal route: `streamrip` + a user-authorized Tidal account; use it for private FLAC downloads when the user has access rights.

`yt-dlp` and `streamrip` are Python dependencies. `ffmpeg` and `deno` are system tools. On macOS, install the system tools with:

```bash
brew install ffmpeg deno
```

If a future streamrip release cannot authenticate to Tidal because its bundled client credentials were revoked, use `scripts/patch_streamrip_tidal.py` with private environment variables. Do not commit Tidal OAuth tokens or client credential values.

### Installing The Skill With An AI Agent

This repository is not a Codex, Claude Code, Cursor, or OpenCode vendor-specific packaged skill. It is a loose Markdown skill: installation works by making the agent discover `skills/online_media.md`, then letting that root skill route to the focused files in `skills/`.

The expected installation path is intentionally simple: give the GitHub repository URL to an AI coding agent and ask it to install the skill into your workspace. The agent should clone or vendor the repository, then connect the root skill to the workspace's discovery chain.

For AI installers:

1. Inspect the target workspace instructions. For Codex, Cursor, and many generic agents, start with `AGENTS.md`. For Claude Code, start with `CLAUDE.md`. If either file points to a workspace routing file such as `WORKSPACE.md`, follow that file before editing anything.
2. Place or keep this repository in a stable project directory, for example `adhoc_jobs/online_media_skill/` or another user-approved tools directory.
3. Ensure the workspace discovery path mentions the root skill `skills/online_media.md`. If the workspace has a skills index such as `rules/skills/INDEX.md` or `skills/INDEX.md`, add one entry there. If it has no index, add a short pointer in `AGENTS.md` or `CLAUDE.md`.
4. If the workspace supports symlinks for global skills, symlink only the root skill. The focused skills should remain local files reached through the root skill.
5. Keep private media libraries, playlist aliases, API keys, and user-specific routes outside this public repository.

Suggested trigger phrases for the workspace index: `online media skill`, `music skill`, `download and transcribe media`, `identify medley source songs`, `fill music metadata`, `find high quality song source`, `bilingual subtitles`, `双语字幕`, `generate SRT`.

### Qwen ASR Setup

Qwen ASR is optional for installation and required only when the user asks for transcription. The project does not assume one fixed path. If an existing Python environment already has a working Qwen ASR setup, point this repo at it:

```bash
export ONLINE_MEDIA_ASR_PYTHON=/path/to/python-with-qwen-asr
export ONLINE_MEDIA_TRANSCRIBE_SCRIPT=/path/to/transcribe.py
```

On Apple Silicon, a typical local setup uses `mlx-qwen3-asr`:

```bash
uv venv
uv pip install mlx-qwen3-asr
```

Installers should check current upstream instructions before pinning package names or model variants. The default model used by this project is `Qwen/Qwen3-ASR-1.7B`, but users can override it with `ONLINE_MEDIA_ASR_MODEL` or the CLI `--model` flag.

## Current CLIs

```bash
# Download or verify Bilibili audio for local personal use.
.venv/bin/python scripts/bilibili_music.py --help

# Prepare medley/transcript artifacts.
.venv/bin/python scripts/medley_identify.py --help

# Plan/apply metadata repair and Apple Music compatible imports.
.venv/bin/python scripts/metadata_resync.py --help

# Prepare and validate artifacts for agent-led bilingual subtitles.
.venv/bin/python scripts/bilingual_subtitles.py --help
```

The medley CLI exports deterministic query packs. Final song identification belongs in the agent workflow described in `skills/online_media.md`.

## Skills

- `skills/online_media.md`: root router. Symlink or register this one globally.
- `skills/download_and_transcribe.md`: online media download and Qwen ASR transcription.
- `skills/medley_source_identification.md`: lyric evidence search and source-song CSV/JSON output.
- `skills/media_metadata.md`: fill and verify local music metadata after download.
- `skills/source_search.md`: find high-quality candidate media sources from titles, lyrics, or descriptions.
- `skills/bilingual_subtitles.md`: correct, semantically segment, translate, and review bilingual SRT subtitles using deterministic artifact helpers.

The repository working language is English. If a downstream workspace keeps private notes in another language, keep those notes outside the public repo or clearly mark them as private overlays.

## Docs

- `docs/prd.md`: product requirements and scenarios.
- `docs/rfc.md`: architecture, schemas, and command boundaries.
- `docs/test.md`: testing and privacy checks.
- `docs/working.md`: changelog and lessons learned.

## Privacy

This repository is designed to be publishable with only fake examples. Real downloaded media, platform `.info.json` files, ASR transcripts, search payloads, and result CSVs are runtime data and must stay out of git.
