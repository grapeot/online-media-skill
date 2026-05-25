# Media Metadata Skill

## Metadata

- **Type**: Workflow
- **Use cases**: fill local audio metadata after download, verify tags before importing into a music library
- **Outputs**: tagged local media files and verification JSON

## Goal

Make downloaded audio usable in a local music library by filling stable metadata: title, artist, album, album artist, track number, year, genre, comment, and cover art.

## Boundary

This skill can use platform metadata and thumbnails to fill local tags. It should not decide the true original artist of a medley source song. For medleys, the downloaded file's artist is the uploader/performer; individual source-song artists belong in the medley identification output.

## Available CLI

```bash
.venv/bin/python scripts/bilibili_music.py --verify-only library/example.m4a
```

The downloader writes MP4 tags through `mutagen` rather than relying only on `yt-dlp --embed-metadata`, because iPhone/Apple Music import needs predictable title, artist, album, track, comment, and cover fields.

## Acceptance Criteria

- `title`, `artist`, `album_artist`, and `has_cover` are present when platform metadata provides enough information.
- Playlist imports include track numbers when order is known.
- `comment` retains a stable source identifier such as a video ID and canonical webpage URL.
- Verification output is machine-readable JSON.

## Known Failure Modes

- Thumbnails may be WebP or another format even when MP4 cover embedding expects JPEG-compatible data. Verify real files after tagging.
- Platform uploader is not necessarily the original song artist.
- Re-running downloads can skip files when `.m4a` and `.info.json` already exist. Use explicit cleanup or force behavior when retagging is required.
