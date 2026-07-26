# Agent-Led Bilingual Subtitles

## Metadata

- **Type**: Workflow
- **Use cases**: turn a local or permitted online talk, meeting, lesson, or speech into a reviewed bilingual SRT
- **Output**: UTF-8 SRT plus inspectable ASR and JSONL sidecars

## Goal

Produce bilingual subtitles whose language, sentence boundaries, terminology, coverage, and timing can be audited. The deterministic CLI prepares and validates artifacts. The agent corrects speech recognition, restores semantic sentence boundaries, translates, and reviews the final text.

This workflow does not hide translation inside a CLI, assume that ASR chunks are sentences, or claim that a structurally valid SRT is linguistically correct.

## Required Context

Before processing the full recording, identify:

- the media file and its duration;
- the source and two output languages;
- the required line order;
- available ASR, VTT, SRT, or diarization sidecars;
- a domain glossary for names, products, acronyms, and specialized terms;
- the destination filename and whether the target player expects an external SRT, a muxed subtitle track, or burned-in text.

For English-Chinese output, default to a stable layout regardless of source language:

```text
English
Simplified Chinese
```

For another language pair, declare `line_1` and `line_2` explicitly before translation.

## Artifact Contract

Use `bilingual-subtitles prepare` to parse a timestamped VTT into source records and write a language-order manifest. Other SRT, diarization, and ASR sidecars are agent evidence; the current deterministic preparation input is VTT. ASR output without fine timing must not replace a better cue timeline.

The agent returns reviewed JSONL. Consecutive cues from the same speaker may be combined when the caption source split one sentence across cue boundaries:

```json
{"source_cue_ids":[15,16],"start":84.155,"end":112.064,"segments":[{"start":84.155,"end":92.984,"line_1":"Welcome, everyone.","line_2":"欢迎大家。"},{"start":92.985,"end":112.064,"line_1":"This is the thirteenth cohort.","line_2":"这是第十三期课程。"}]}
```

Every source cue ID must appear exactly once across the reviewed records. The agent assigns each bilingual segment's timing from source cue or word evidence; the CLI never guesses semantic timing from text length. Combining rapid, semantically redundant handoffs can be justified for readability, but do not merge different speakers merely to create longer subtitles.

## Agent Judgment

The agent owns all language decisions:

- compare available transcript sources and listen around unresolved timestamps;
- correct only high-confidence recognition errors involving names, technical terms, or clearly misheard common words;
- preserve the speaker's wording, word order, repetitions, self-corrections, hesitation, and intentional code-switching;
- restore a sentence across raw cue boundaries without rewriting its syntax;
- split long speech at aligned semantic boundaries in both languages;
- translate naturally within each segment without adding, omitting, or resolving meaning that the speaker left uncertain;
- keep terminology consistent across parallel work packets;
- inspect packet boundaries after merging subagent output.

Do not invent an unclear model name, person, product, or number. Preserve uncertainty in a review note and resolve it by listening when it affects meaning.

## Fidelity Before Readability

The default editorial contract is transcript correction, not prose editing. A subtitle may improve punctuation and line breaks, but it must not make the speaker more concise, certain, grammatical, or pedagogically complete than the recording.

- Keep the source transcript as the wording baseline. Independent ASR is corroborating evidence, not permission to smooth the source.
- Preserve meaningful repetition, false starts, unfinished phrases, hedges, and self-corrections. A non-lexical `um` or `uh` may be omitted when it has no semantic role, but do not remove surrounding words to make the sentence cleaner.
- Do not replace a phrase with a shorter synonym, summarize several clauses, supply an implied conclusion, or reorder syntax merely to improve reading speed.
- Joining adjacent same-speaker cues is allowed only when the caption source split one spoken sentence. Preserve the original token order after joining.
- Never silently absorb substantive speech from another speaker. A very short acknowledgment may remain short when speaker fidelity is more important than display duration.
- Translation may use natural target-language grammar, but it must preserve negation, uncertainty, repetition, self-correction, technical relationships, and the direction of actions.

For parallel packet work, require each worker to report every non-punctuation source-language change as `cue_id: before -> after`. After merging packets, run a separate fidelity audit against the source JSONL. This audit is distinct from readability QA: readability findings may change timing or line breaks, but wording changes require source or independent-ASR evidence.

## Deterministic CLI

The helper exposes atomic operations only:

```bash
bilingual-subtitles prepare --input transcript.vtt \
  --output session.subtitle_source.jsonl \
  --manifest session.subtitle_manifest.json \
  --line-1-language en --line-2-language zh-Hans
bilingual-subtitles verify-work --source session.subtitle_source.jsonl \
  --manifest session.subtitle_manifest.json \
  --input session.subtitle_reviewed.jsonl
bilingual-subtitles render --manifest session.subtitle_manifest.json \
  --source session.subtitle_source.jsonl \
  --input session.subtitle_reviewed.jsonl --output bilingual.srt
bilingual-subtitles validate --manifest session.subtitle_manifest.json \
  --input bilingual.srt --media-duration 8926.4
```

- `prepare` parses and partitions timestamp cues without semantic inference, rejects unrecognized cue blocks, and binds the VTT and source JSONL hashes into the manifest.
- `verify-work` checks source coverage, uniqueness, group timing, and non-empty bilingual segments.
- `render` re-verifies source coverage, uses agent-reviewed segment timestamps, preserves intentional spaces around Latin terms, and records reviewed-input and SRT hashes in the manifest.
- `validate` verifies the SRT hash, then checks indices, timing order, overlap, empty lines, media duration, and short display intervals.

## Quality Standard

- Each subtitle contains exactly two non-empty lines in the declared order.
- English-Chinese work keeps English on line 1 and Simplified Chinese on line 2 even when Chinese is the source language.
- Most English segments stay at or below 12 words; an inseparable phrase may reach 16.
- Source cue IDs have complete, duplicate-free coverage.
- The language-order manifest stays beside source, reviewed JSONL, and SRT artifacts.
- Timestamps are increasing, non-overlapping, and end within the media duration.
- Product names and mixed Chinese/Latin text retain readable spacing.
- Rapid acknowledgments under 0.8 seconds are reviewed. Merge redundant exchanges when meaning survives; do not extend text across another speaker's meaningful speech.
- A short pilot is rendered and inspected before full-session processing.
- Every non-punctuation correction is traceable to a cue and supporting evidence.
- A final fidelity audit confirms that readability edits did not paraphrase, summarize, remove meaningful speech, or resolve uncertainty.
- The final SRT passes `validate` and a player-load or subtitle-track mux smoke test.

## Known Failure Modes

- ASR chunks may be accurate prose but too coarse for subtitle timing.
- Zoom-style cue boundaries often split after articles, conjunctions, or prepositions and therefore are not sentence boundaries.
- Selecting every cue that intersects adjacent time packets duplicates boundary-spanning cues. Packet assignment must use cue start time.
- Removing all whitespace joins mixed-script text into artifacts such as `AIBuilder` or `officehour`.
- Structurally valid parallel packets can still disagree on terminology or split one thought at packet boundaries. Run a global language and boundary review before rendering.
- Readability review can overcorrect a transcript by turning spoken language into polished prose. Treat suggestions to shorten, combine, or clarify wording as suspect unless the source audio supports them.
- Parallel agents tend to normalize grammar and remove repetitions even when asked only to correct ASR. Collect their non-punctuation edits and audit them against source cues before rendering.
- Eliminating every short subtitle can erase speaker turns or false starts. Accept unavoidable short cues when the alternative is cross-speaker merging or invented wording.
- A valid source cue can end a few milliseconds after the probed media duration. Keep the source record auditable, but trim the final rendered segment to the exact media duration.
- Some FFmpeg builds omit the libass `subtitles` filter. A short mux using `mov_text` plus `ffprobe` is a valid loadability smoke test for MP4 workflows.
