# Online Media Skill PRD

## Goal

Build a public-ready Python CLI and agent skill for online media workflows. The CLI produces reproducible media artifacts and structured sidecar files; AI agents consume those files to make research, translation, and matching judgments with explicit evidence.

The project starts from music medley source identification, but the product boundary is broader: online songs, talks, meetings, speeches, and candidate media verification should all share the same artifact pipeline.

## Users

Primary users are AI agents and technical operators who need reliable media processing primitives. A human can run the CLI directly, but the main design target is an agent that can compose commands, inspect JSON outputs, call search tools, and write final reports.

## Core Principle

The CLI owns deterministic or artifact-producing work:

- Download allowed media into a local library.
- Extract platform metadata into sidecar JSON.
- Transcribe media with Qwen ASR or another configured ASR backend.
- Parse transcripts into timestamped segments.
- Generate lyric/search anchor candidates and query packs.
- Verify file metadata and produce machine-readable reports.
- Prepare VTT work packets, verify source-cue coverage, render reviewed bilingual segments, and validate SRT structure.

The AI agent owns judgment work:

- Choose which anchors to search first.
- Call Tavily or other search tools.
- Decide whether a source supports a song, artist, translation, or candidate match.
- Merge uncertain evidence across segments.
- Assign confidence and review flags.
- Write final CSV/JSON/report artifacts.
- Correct ASR, restore semantic sentence boundaries, translate, and review bilingual subtitle language.

This boundary keeps the CLI reusable across projects. It also avoids hiding Tavily aggregate answers or LLM-style judgments inside a command that appears deterministic.

## Scenarios

### 1. Music Medley Source Identification

Input can be a Bilibili/YouTube URL, a playlist, or a local audio file. The CLI downloads or reads the media, runs ASR, parses the timestamped transcript, and emits an anchor query pack. The agent searches lyric evidence, identifies source songs, and writes a CSV/JSON song list with `start`, `end`, `song_title`, `artist`, `lyric_evidence`, `source_urls`, `confidence`, and `needs_review`.

Success means every confirmed song has at least one ASR lyric fragment and at least one external source supporting the song identity. Search summaries alone are not sufficient evidence.

### 2. Online Talks, Meetings, and Speeches

Input can be a media URL or local recording. The CLI downloads or reads the media and produces a transcript sidecar with segments and metadata. The agent translates, summarizes, extracts action items, or builds a topic index.

Success means the transcript artifact is preserved separately from the agent's interpretation. A future agent can rerun translation or summarization without rerunning ASR.

### 3. Candidate Song Search and Verification

Input can be a known song title, partial lyric, description, or local audio. The agent searches for candidate media. The CLI downloads permitted candidates, transcribes or fingerprints them, and emits sidecars. The agent compares lyrics, descriptions, metadata, and search evidence to decide whether a candidate is the intended song.

Success means the final judgment cites both candidate metadata and content evidence. Downloading candidates and deciding whether they match remain separate steps.

### 4. Agent-Led Bilingual Subtitles

Input can be a local or permitted online recording plus any available VTT, SRT, diarization, or ASR sidecars. The CLI prepares timestamped work packets and later verifies coverage, renders reviewed bilingual segments, and validates the SRT. The agent compares transcript evidence, corrects terminology, restores sentences across raw cue boundaries, translates, and performs global readability QA.

Success means the final SRT has a persisted language-order manifest, complete source-cue coverage, aligned bilingual meaning, consistent terminology, agent-reviewed segment timing, and a player-load or mux smoke test. Raw transcript artifacts remain separate so another agent can audit or retranslate the recording without rerunning ASR.

## Non-Goals

- Do not ship copyrighted audio, real downloaded media, real platform `.info.json` files, or real ASR outputs in the public repository.
- Do not bypass platform access controls or DRM.
- Do not embed Tavily, search-engine, or LLM judgment into the default deterministic CLI path.
- Do not treat video titles, upload dates, tags, or aggregate search answers as final facts.

## Acceptance Criteria

- The public repo contains only source code, docs, skills, tests, fake fixtures, and schemas.
- Runtime data directories such as `library/`, `source_identification/`, ASR outputs, `.m4a`, `.info.json`, and live search payloads are gitignored.
- Default tests run offline without API keys, media downloads, or ASR model calls.
- Live integration tests are opt-in through explicit environment variables.
- CLI outputs are structured JSON/JSONL/CSV/Markdown sidecars with stable schemas.
- Agent-facing skills define evidence requirements and confidence rules for intelligent steps.
- Bilingual subtitle tooling remains deterministic: it never calls an LLM or presents machine translation as a CLI result.
