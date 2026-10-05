# AniMeXe Roadmap

## Now — foundation
- Python package and CLI.
- Configuration and workspace management.
- Persistent state model.
- Anime library model.
- Provider interface.
- Discovery/release-state model.
- Scheduler unit tests.

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
- Anime discovery and release-status refresh.
- Episode availability monitoring.
- Automatic candidate-pool and active-slot management.
- Kuhi primary adapter.
- Anivexa secondary adapter.
- Provider health, source usability, and fallback scoring.
- Kitsune compatibility kept as a legacy/reference adapter.
- Provider health and fallback.
- GitHub Actions analyze/render workflows.
- Warm dependency/model caches.
- Checkpoint recovery.
- Artifact reports.
- Persistent state commits.

## Scale — multi-anime
- Automatic active-slot selection up to four anime.
- Dynamic replacement when an anime finishes, pauses, catches up, or becomes unavailable.
- Automatic re-entry when a new episode is detected.
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