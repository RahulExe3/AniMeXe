# AniMeXe Roadmap

## Now — foundation
- Python package and CLI.
- Configuration and workspace management.
- Persistent state model.
- Scheduler unit tests.
- Provider interface.

## Next — first usable episode
- Local/manual episode input.
- FFprobe inspection.
- Scene detection and frame index.
- Subtitle/transcript extraction.
- Story representation.
- Original explanation script.
- Local/free TTS.
- Scene matching.
- FFmpeg render and validation.

## Then — provider and automation
- Kitsune adapter.
- Provider health and fallback.
- GitHub Actions analyze/render workflows.
- Warm dependency/model caches.
- Checkpoint recovery.
- Artifact reports.
- Persistent state commits.

## Scale — multi-anime
- Four active anime.
- Two successful outputs per day.
- Balanced, Priority, and Flexible scheduling.
- Independent episode queues.
- Retry without skipping episodes.

## Later — publishing
- YouTube publishing adapter.
- Anime/season playlist management.
- Upload deduplication.
- Publish retry without rerendering.

## Rule
Do not enable the next automation layer until the previous layer has a reproducible test and a clear recovery path.