# Working Notes

## Changelog

### 2026-05-24

- Ran Qwen ASR smoke on a 1998 medley and confirmed timestamped segment output works.
- Added initial `medley_identify.py` CLI and offline tests for year detection, segment parsing, anchor extraction, song inference, and CSV writing.
- Regenerated year-labeled inventory and confirmed 38 matched `.m4a` files.
- Ran a one-file `transcribe` smoke and a constrained `identify` smoke.
- Found that Tavily aggregate answers can produce overconfident song identity rows when source snippets do not support the lyric anchor.
- Pivoted the project boundary: CLI should produce deterministic sidecars; AI agents should own search, evidence judgment, and confidence assignment.
- Added PRD/RFC/test scaffold for a public-ready online media skill project.
- Removed the legacy Tavily/song-inference CLI path from the public command surface.
- Replaced public test and RFC examples with invented lyrics and fake song evidence.
- Split repo skills into a root router plus focused download/transcribe, medley identification, metadata, and source-search workflows.
- Documented loose AI-agent installation, Markdown skill discovery, and Qwen ASR setup expectations in README.
- Set English as the public working language for this repository.
- Merged the five agent-produced medley source batches into `source_identification/medley_sources.csv` with 856 globally ordered rows and relative artifact filenames.
- Renamed the project directory from its temporary path to `adhoc_jobs/online_media_skill/` and updated workspace skill routing plus the root symlink.
- Tightened CLI and test typing so basedpyright reports no diagnostics for the Python files.
- Compared YouTube and Tidal download routes on three confirmed songs; YouTube produced lossy MP3 files while Tidal produced substantially larger FLAC files.
- Documented yt-dlp + Deno/EJS and streamrip + Tidal as practical source acquisition routes.
- Added a private-environment streamrip Tidal patch helper and conservative Tidal batch-rate guidance.
- Added deterministic medley source dedupe, generating a download-ready unique song list plus near-duplicate review CSV.
- Refactored Tidal acquisition into search-candidates, AI/human approval, and download-approved stages after smoke tests showed raw search can return misleading cover candidates.
- Clarified Tidal candidate review semantics: `desc_artist` is the structured platform artist, while artist names embedded inside `desc_title` are weak evidence and can indicate covers, karaoke, or mislabeled uploads.
- Current private runtime scale: `medley_sources.csv` has 856 identified medley rows, `medley_sources_deduped.csv` and `medley_sources_download_queue.csv` each have 763 rows, and the five-song Tidal candidate smoke produced 328 candidate rows with one search error.
- Ran full Tidal candidate search for the 763-row deduped queue. Search returned 22,637 candidate rows across 754 source groups, including 186 search-error groups.
- Reviewed the full candidate CSV conservatively, approving one candidate for 310 source groups and leaving weak or mismatched groups unresolved.
- Downloaded the approved Tidal IDs, then quarantined 64 files whose downloaded filenames exposed `Live` or accompaniment markers. The accepted Tidal directory currently has 246 files, and the quarantine directory has 64 files.
- Built a YouTube Route A queue for the remaining unresolved songs after excluding accepted Tidal studio matches and adding quarantined Tidal live/accompaniment cases back into the unresolved set.
- Ran YouTube candidate discovery for 516 remaining rows, producing 2,580 candidate rows. Conservative review approved 452 URLs and wrote the 64 still-unresolved rows to `source_identification/youtube_unresolved_queue.csv`.
- Downloaded the 452 approved YouTube URLs as MP3 files. Post-download filename QA quarantined no YouTube files in this pass.

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
