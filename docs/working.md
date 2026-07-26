# Working Notes

## Changelog

### 2026-07-26

- Made source fidelity the default bilingual-subtitle editorial contract: correct high-confidence ASR errors, but do not paraphrase, summarize, normalize spoken syntax, remove meaningful repetitions, or resolve uncertainty.
- Split fidelity audit from readability QA. Parallel packet workers now need an auditable list of non-punctuation source-language changes before final rendering.
- Documented the trade-off for short speaker turns: preserve substantive speech and speaker boundaries instead of forcing every cue above a display-duration threshold.
- Added final media-tail verification and the option to trim only the rendered segment when a caption source exceeds the probed media duration by a few milliseconds.

### 2026-07-19

- Added an agent-led bilingual subtitle workflow for local or permitted online talks, meetings, lessons, and speeches.
- Added deterministic `bilingual-subtitles` commands for VTT packet preparation, reviewed-work coverage checks, SRT rendering, and structural validation; correction, semantic segmentation, and translation remain agent responsibilities.
- Added offline tests for VTT parsing, packet boundaries, grouped source-cue coverage, explicit segment timing, mixed Chinese/Latin spacing, overlap detection, and media-duration validation.
- Updated the root router, README, PRD, RFC, and test strategy with the new workflow and CLI/agent boundary.

### 2026-05-25

- Scoped local music-library deduplication to `~/Music/CloudMusic` and `~/Music/Music` only. Staging directories such as `library/tidal`, `library/youtube`, and medley acquisition artifacts stay outside this pass.
- Surveyed both library roots: CloudMusic is a flat export; Music/Music is an Apple Music library with artist folders plus `Media.localized`.
- Added shared tag-reading helpers in `scripts/audio_tags.py` for MP3/ID3, FLAC/Vorbis, and M4A/MP4 through `mutagen`, plus normalized `(title_key, artist_key)` fields and filename fallback when embedded tags are missing.
- Added `scripts/music_library_dedup.py read-tags` to scan one or more library roots and write `source_identification/music_library_inventory.csv` with `full_path` and tag metadata.
- Registered the CLI entry point as `music-library-dedup` in `pyproject.toml`.
- Added offline tests in `tests/test_audio_tags.py` and `tests/test_music_library_dedup.py`; default suite now covers tag normalization, inventory rows, and `read-tags` CSV export.
- Clarified the existing tag QA boundary: `tidal_download_from_csv.py verify-tags` and `bilibili_music.py --verify-only` check tag presence only; full metadata export for dedupe belongs to `read-tags`.
- Added `scripts/dedup_logic.py` for duplicate clustering, canonical ranking, near-duplicate detection, artwork cache wiring, and HTML review rendering.
- Extended `music_library_dedup.py` with `survey` and `build-review` commands alongside `read-tags`.
- Wrote `skills/music_library_dedup.md` and routed it from `skills/online_media.md`.
- Ran the full private-library pipeline on the local CloudMusic and Apple Music roots:
  - `music_library_inventory.csv`: file inventory plus read-error count
  - `music_library_survey.md`: folder layout plus tag coverage summary
  - `music_library_dedup_review.csv/json/html`: duplicate-cluster review artifacts
  - `music_library_near_duplicates.csv`: same-title different-artist review rows
  - artwork cache extracted for review visualization
- Stopped before apply/trash as planned; user approval is required against the review CSV/HTML.

### 2026-05-24

- Ran Qwen ASR smoke on a medley and confirmed timestamped segment output works.
- Added initial `medley_identify.py` CLI and offline tests for year detection, segment parsing, anchor extraction, song inference, and CSV writing.
- Regenerated year-labeled inventory and confirmed the expected `.m4a` matches.
- Ran a small `transcribe` smoke and a constrained `identify` smoke.
- Found that Tavily aggregate answers can produce overconfident song identity rows when source snippets do not support the lyric anchor.
- Pivoted the project boundary: CLI should produce deterministic sidecars; AI agents should own search, evidence judgment, and confidence assignment.
- Added PRD/RFC/test scaffold for a public-ready online media skill project.
- Removed the legacy Tavily/song-inference CLI path from the public command surface.
- Replaced public test and RFC examples with invented lyrics and fake song evidence.
- Split repo skills into a root router plus focused download/transcribe, medley identification, metadata, and source-search workflows.
- Documented loose AI-agent installation, Markdown skill discovery, and Qwen ASR setup expectations in README.
- Set English as the public working language for this repository.
- Merged the agent-produced medley source batches into `source_identification/medley_sources.csv` with globally ordered rows and relative artifact filenames.
- Renamed the project directory from its temporary path to `adhoc_jobs/online_media_skill/` and updated workspace skill routing plus the root symlink.
- Tightened CLI and test typing so basedpyright reports no diagnostics for the Python files.
- Compared YouTube and Tidal download routes on confirmed songs; YouTube produced lossy MP3 files while Tidal produced substantially larger FLAC files.
- Documented yt-dlp + Deno/EJS and streamrip + Tidal as practical source acquisition routes.
- Added a private-environment streamrip Tidal patch helper and conservative Tidal batch-rate guidance.
- Added deterministic medley source dedupe, generating a download-ready unique song list plus near-duplicate review CSV.
- Refactored Tidal acquisition into search-candidates, AI/human approval, and download-approved stages after smoke tests showed raw search can return misleading cover candidates.
- Clarified Tidal candidate review semantics: `desc_artist` is the structured platform artist, while artist names embedded inside `desc_title` are weak evidence and can indicate covers, karaoke, or mislabeled uploads.
- Recorded private runtime scale only in ignored sidecars; committed notes now keep the reusable workflow shape without publishing local library counts.
- Ran full Tidal candidate search for the deduped queue and kept the high-volume candidate CSV under ignored runtime storage.
- Reviewed the full candidate CSV conservatively, approving only strong source groups and leaving weak or mismatched groups unresolved.
- Downloaded the approved Tidal IDs, then quarantined files whose downloaded filenames exposed `Live` or accompaniment markers.
- Built a YouTube Route A queue for the remaining unresolved songs after excluding accepted Tidal studio matches and adding quarantined Tidal live/accompaniment cases back into the unresolved set.
- Ran YouTube candidate discovery for the remaining rows, kept the high-volume candidate CSV private, approved conservative URL matches, and wrote unresolved rows to `source_identification/youtube_unresolved_queue.csv`.
- Downloaded the approved YouTube URLs as MP3 files. Post-download filename QA found no YouTube files requiring quarantine in this pass.
- Added `scripts/metadata_resync.py` for plan/apply metadata repair, Tidal FLAC to ALAC M4A conversion, and CloudMusic M4A resync. Registered the `metadata-resync` entry point and added offline coverage in `tests/test_metadata_resync.py`.
- Confirmed the Apple Music/iOS import path should use ALAC `.m4a` rather than FLAC for lossless local library sync. The repair workflow now treats FLAC as a private source/archive format and ALAC M4A as the import-ready format.
- Documented album tag repair practice: query structured music sources such as MusicBrainz, Apple Music/iTunes, Deezer, KKBOX, Wikipedia, Baidu Baike, and official MV descriptions; keep unresolved rows in a review plan instead of writing workflow placeholder albums.
- Converted the accepted Tidal FLAC batch to ALAC M4A and applied the CloudMusic resync plan. The resynced M4A files retained title, artist, album, and artwork.
- Completed the YouTube album repair workflow and kept final plan outcomes in ignored runtime files.
- Kept final post-resync inventory details in ignored runtime files.

## Lessons Learned

- `yt-dlp --write-info-json` outputs can include signed CDN URLs, browser identifiers, headers, and expiring download parameters. Treat real `.info.json` files as private runtime data.
- Real `.m4a`, full ASR lyric transcripts, search payloads, and result CSV files should stay out of the public repo.
- ASR is an artifact-producing media transformation. It can live in the CLI even though the model is probabilistic, because downstream agents can inspect and rerun the artifact.
- Search strategy, source credibility, song identity, translation quality, and confidence labels belong in the agent workflow, not the deterministic CLI.
- Tavily aggregate answers are useful hints, but `high` confidence requires source snippets or extracted page text that support both the lyric anchor and the claimed song identity.
- YouTube downloads are useful for fast verification, but Tidal FLAC is a better private listening/archive source when the user has an authorized subscription.
- Streamrip/Tidal failures around `invalid_client`, `403`, and lyrics `401` are usually tooling/API-boundary issues; patch only the local virtual environment and keep credentials out of repo files.
- Run dedupe after source identification and before bulk download; exact title/artist matches are safe to collapse, while same-title different-artist groups need review.
- Do not let code auto-pick Tidal IDs from search results. Use CLI to gather candidates, then let AI/human review simplified/traditional variants, cover markers, artist-title inversions, and weak matches before approving downloads.
- A candidate like `ALWAYS ONLINE by 林俊傑` is a likely simplified/traditional variant match for `Always Online - 林俊杰`; a candidate like `林俊杰 - Always Online by A` has the searched artist only in the title and should be rejected unless a listening check confirms it is the intended recording.
- Tidal search output can omit version qualifiers that appear in downloaded filenames. Post-download QA found files such as live or accompaniment versions even after candidate metadata looked acceptable, so future batches should quarantine filename/tag matches for `Live`, `伴奏`, `Karaoke`, `Cover`, and medley-style titles before import.
- YouTube Route A should follow the same shape as Tidal Route B at batch scale: candidate discovery first, AI/human review second, approved download third, post-download marker QA last. Direct `ytsearch` download is too loose for a library-building workflow.
- Existing download QA commands only verify tag presence. Library dedupe needs full metadata export through `read-tags`; do not overload `verify-tags` into an inventory tool.
- ID3-only MP3 files without a valid MPEG frame can still carry usable tags. The reader should fall back to `ID3(path)` instead of treating the file as untagged.
- Offline tests for FLAC/M4A should mock format-specific readers rather than synthesize compressed audio containers in pytest.
- Inventory CSVs contain local absolute paths and belong under ignored runtime directories such as `source_identification/`.
- Workflow album names such as `Online Media Skill YouTube Sources` are useful as temporary batch labels but are wrong for library tags. Real imports should use a verified release name, soundtrack/EP/single title, or an unresolved review row.
- FLAC is not a safe final assumption for Apple Music/iOS library workflows. Ask whether the target player accepts FLAC; if the target is Apple Music or iOS sync, add an ALAC `.m4a` conversion and post-conversion tag/artwork verification step.
- At batch scale, run a small smoke batch first, verify the full plan/apply/output loop, then fan out parallel research or candidate-review tasks. Keep parallel workers on artifact production and evidence judgment; the main thread should merge maps, apply mutations, and run the final inventory checks.
- ASR chunks and caption cues are evidence boundaries, not semantic sentence boundaries. Bilingual subtitle work needs an agent pass that can merge adjacent same-speaker cues while retaining source-cue provenance.
- Keep deterministic subtitle code language-neutral through `line_1` and `line_2`; declare the language order in the agent workflow. For English-Chinese subtitles, stable English-first ordering is easier to review than changing layout with source language.
- Preserve intentional spaces around Latin names in Chinese text. Collapsing all whitespace produces artifacts such as joined product names and surrounding words.
- Semantic segmentation is not semantic rewriting. Joining cues to recover a spoken sentence must preserve the speaker's original token order, repetition, self-correction, hedging, and unfinished phrases.
- Independent ASR can confirm a local correction, but a smoother ASR transcript is not authority to replace the source transcript wholesale.
- Readability QA naturally optimizes toward polished prose and fewer short captions. Without a separate fidelity audit, it can flip negation, erase live confusion, or teach a correction that the speaker had not yet reached.
- Parallel translation workers should return a ledger of every non-punctuation source-language change. This makes unsupported normalization visible before packet outputs are merged.
- Structural validation proves coverage and timing, not transcript faithfulness. Final acceptance needs both deterministic validation and source-to-reviewed language audit.
