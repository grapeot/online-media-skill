# Medley Source Identification Skill

## Metadata

- **Type**: Workflow
- **Use cases**: identify original songs in medleys, cover chains, year collections, and lyric mashups
- **Inputs**: ASR Markdown, segment JSONL, query-pack JSONL, or local audio that can first be transcribed
- **Outputs**: evidence-backed CSV/JSON song list

## Goal

Produce a structured source-song list with timestamps, lyric evidence, supporting URLs, confidence, and review flags. The agent owns the judgment; the CLI only prepares transcript and query artifacts.

## Required Evidence

A confirmed row needs evidence for both the lyric anchor and the song identity. Tavily `answer` is a hint, not evidence. Prefer source snippets or extracted page text from lyric pages, music platforms, encyclopedic entries, album pages, or reliable video descriptions.

Use confidence levels this way:

- `high`: source text supports both the lyric anchor and the song title/artist.
- `medium`: the lyric strongly points to a song, but evidence is partial, secondary, or version-specific.
- `low`: the result comes only from aggregate answers, title similarity, upload metadata, or weak hints.

Set `needs_review=true` when ASR is noisy, the anchor is short or common, singer/version attribution is ambiguous, or source evidence does not include both lyric and identity.

## CLI Artifacts

Generate a query pack from existing ASR:

```bash
.venv/bin/python scripts/medley_identify.py query-pack \
  --asr-dir source_identification/asr \
  --output source_identification/anchor_queries.jsonl
```

The query pack contains source file, ASR file, segment timing, segment text, anchor text, and a suggested search query. The agent may change the query strategy when needed.

## Output Schema

Final CSV columns:

```text
order,source_file,asr_file,start,end,song_title,artist,release_year,lyric_evidence,source_urls,confidence,needs_review,notes
```

The final CSV/JSON is an agent artifact. Do not generate it from an unreviewed aggregate search answer.


## Post-Identification Dedupe

After the evidence-backed source CSV is complete, deduplicate before any bulk download. The first pass is deterministic and belongs in the CLI:

```bash
.venv/bin/python scripts/medley_identify.py dedupe-sources \
  --input source_identification/medley_sources.csv \
  --output source_identification/medley_sources_deduped.csv \
  --near-duplicates source_identification/near_duplicates_for_review.csv
```

The dedupe key is exact normalized `(song_title, artist)`. Rows with empty `song_title` are unresolved and excluded. Boundary rows such as `title A / title B` are expanded into separate entries when the artist field has matching slash-separated parts. The deduped CSV keeps traceability through `source_files`, `time_ranges`, merged lyric evidence, merged source URLs, best confidence, and review flags.

Then inspect `near_duplicates_for_review.csv`. Same title with different artists is not automatically merged because it can mean a cover, duet, live version, or a different song with the same title. For example, `大哥` by 卫兰 and `大哥` by 柯受良 should remain separate. Only merge when a human or agent has checked the rows and decided they are the same recording target for download.

For bulk acquisition, use the manually reviewed deduped CSV rather than the original segment-level CSV. Do not download before dedupe.

## Known Failure Modes

- Whole-video playlist searches often hallucinate plausible songs from the era. Use lyric anchors as the primary evidence path.
- ASR can corrupt song titles and names. Search nearby distinctive lyric fragments instead of the suspect word alone.
- One ASR segment may contain parts of two songs. Mark boundary uncertainty in `notes`.
- Video theme year is not the release year for each song. Leave `release_year` blank unless separately sourced.
