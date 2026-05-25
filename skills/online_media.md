# Online Media Root Skill

## Metadata

- **Type**: Root Workflow
- **Use cases**: route online media tasks to the right focused skill
- **Public boundary**: this root skill is the only file intended to be symlinked from a private workspace-level skill index. Private media libraries, playlist aliases, and credentials live outside this public repo.

## Goal

Route an agent to the correct online media workflow. This repository uses Markdown skills rather than a vendor-specific skill package format; discovery depends on an agent reading this root file and then following the linked local skill paths.

## Which Skill To Use

Use `skills/download_and_transcribe.md` when the task is to download permitted online audio/video, preserve platform metadata, run Qwen ASR, or produce transcript sidecars for talks, meetings, speeches, or songs.

Use `skills/medley_source_identification.md` when the task is to identify original songs inside a medley, cover chain, year collection, or lyric-based mashup from ASR text.

Use `skills/media_metadata.md` when the task is to fill or verify local audio metadata after download, especially title, artist, album, track number, cover art, and comments for local music library import.

Use `skills/source_search.md` when the task starts from a song title, partial lyric, description, or remembered fragment and the goal is to find a high-quality candidate source before download or verification.

## CLI vs Agent Boundary

The CLI may:

- download permitted media
- write metadata sidecars
- run ASR
- parse timestamped transcripts
- split lyrics or speech into segments
- generate search/query packs
- verify local file metadata

The agent must handle:

- choosing which query pack rows to search
- calling Tavily or other search tools
- deciding whether evidence supports a song, translation, or candidate match
- merging adjacent segments into songs or topics
- assigning confidence and `needs_review`
- writing final reports, JSON, or CSV deliverables

## Shared Boundary

The CLI produces artifacts: downloaded files, metadata sidecars, ASR transcripts, segment JSONL, and query packs. The agent produces judgments: source credibility, song identity, translation quality, candidate match decisions, confidence labels, and final reports.

If a task asks the CLI to decide a song title, assign confidence from search results, or summarize a transcript, stop and move that work into the agent layer.

## Known Failure Modes

- Search aggregate answers can name a song that returned snippets do not support. Treat this as `low` confidence.
- ASR can turn named entities or song titles into plausible common words. Search nearby lyric anchors rather than the suspect token alone.
- Platform upload dates and video titles describe the uploaded media, not necessarily the release year of each source song.
- Real `.info.json` files can contain signed URLs and browser identifiers. Keep them out of public repos.
