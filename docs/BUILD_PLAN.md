# AniMeXe Build Plan

> The implementation blueprint. The AniMeXe repository remains the source of truth.

## 1. Product shape
AniMeXe is a reusable episode-production engine. The core flow is: anime library -> central scheduler -> episode job -> provider or local media input -> media inspection -> scene/transcript analysis -> story understanding -> original explanation script -> TTS -> scene matching -> timeline -> BGM/SFX/subtitles -> FFmpeg render -> validation -> artifact/state.

Publishing is a later adapter and is not part of the first production milestone.

## 2. YTAutoPilot template
We will copy the proven operational pattern from RahulExe69/ytautopilot, not its gaming-specific code.

- Python package with a single CLI entrypoint.
- GitHub Actions worker.
- workflow_dispatch for manual testing.
- Scheduled Actions only after the local pipeline is stable.
- Warm pip/Python/model caches.
- Explicit FFmpeg and ffprobe checks.
- Environment-based configuration.
- Machine-readable manifests and reports.
- Persistent JSON state under data/.
- Workflow artifacts for debugging.
- Retry loops around expensive stages.
- State commits back to main.
- Fetch and rebase before pushing state so concurrent runs do not blindly overwrite newer commits.
- Dry-run/analyze modes before expensive rendering.
- Clear distinction between committed, workflow-tested, and visually verified.

## 3. Build order

### Phase 0 — Foundation
Create the Python package, CLI, configuration loader, structured logging, workspace manager, FFmpeg checks, tests, and job reports.

### Phase 1 — State engine
Implement anime records, season records, episode records, job state transitions, attempts, failure reasons, checkpoints, and atomic state writes.

Episode progression must remain independent per anime. A failed episode remains the current episode until it succeeds.

### Phase 2 — Metadata
Implement AniList identity lookup, Jikan fallback, season/episode normalization, and provider-independent IDs.

### Phase 3 — Provider foundation
Create the provider interface, normalized EpisodeRef/EpisodeAvailability/MediaSource models, provider registry, health states, caching boundaries, retry/backoff handling, and LocalProvider fixtures.

### Phase 4 — Primary external provider
Implement `src/providers/kuhi` against the verified Kuhi/anime-api contract. Prefer its native provider layer rather than its legacy Miruro fallback. Validate title/season matching, episode continuity, source resolution, media usability, subtitles, and provider health.

### Phase 5 — Secondary provider
Implement `src/providers/anivexa` as the first external fallback/reference integration. Reuse AniMeXe's normalized models; do not leak Anivexa-specific response structures into the scheduler or renderer.

### Phase 6 — Local/manual input
### Phase 4 — Media input
Support a manually supplied local episode file as the mandatory development path. Provider-resolved media enters through the same normalized MediaInput boundary.

### Phase 5 — Episode analysis
Run FFprobe inspection, scene detection, representative-frame extraction, subtitle/transcript extraction, optional Whisper/faster-whisper processing, and write an analysis manifest.

Checkpoint chain: input -> inspected -> scenes -> transcript.

### Phase 6 — Story engine
Convert analysis into an ordered episode representation containing events, characters, locations, importance, ending, continuity notes, and candidate scenes. Generate and validate an original explanation script from this representation.

### Phase 7 — Narration
Build a replaceable TTS adapter with a free/local first implementation, Hinglish-friendly pronunciation, sentence-level synthesis, duration measurement, retries, fallback, and punctuation-aware pacing.

### Phase 8 — Intelligent editing
Match narration segments to scenes using chronology, transcript overlap, entities, visual similarity where available, importance, duration fit, and repetition penalties. Produce a declarative timeline.

### Phase 9 — Audio, subtitles, render
Mix narration, ducked BGM, optional SFX, burned-in subtitles, and muted source audio. Render with FFmpeg and validate the final MP4.

### Phase 10 — Anime discovery, episode monitoring, and scheduler
Build the anime library, discovery layer, release-state tracking, episode monitor, candidate pool, and multi-anime scheduler. The four-anime limit is an active-slot limit, not a manually selected list. AniMeXe should automatically discover/add anime according to configured discovery rules, exclude not-yet-released anime, detect premieres and newly released episodes, keep caught-up airing anime in a waiting state, and dynamically fill vacant active slots from eligible candidates. Defaults are four active anime and two successful outputs per day. Supported strategies are Balanced, Priority, and Flexible.

### Phase 11 — GitHub Actions
Use GitHub Actions as the hosted worker. The sequence is checkout -> restore caches -> install/check media tools -> load state -> schedule jobs -> process -> validate -> upload artifacts -> persist state -> fetch main -> rebase -> push.

Initial workflow modes: dry-run, analyze, render, scheduled. Publishing stays disabled.

### Phase 12 — Publishing
Only after production is reliable, add upload, playlist association, ordering, retry, and publishing deduplication. A publishing failure must never force an already-rendered episode to be regenerated.

## 4. Checkpointing
Every expensive stage writes a checkpoint manifest containing input fingerprint, configuration fingerprint, tool/model versions, outputs, timestamp, and validation result.

Example recovery state: input complete, metadata complete, scenes complete, transcript complete, story complete, script complete, TTS failed. The next run starts at TTS.



## 4.5 — Temporary media strategy
Source episodes are processing inputs, not permanent assets. The media boundary should prefer streaming, range requests, HLS/DASH segment retrieval, or targeted timestamp extraction when the provider supports them. A full episode may be materialized temporarily when a processing stage requires random access, but it must live only in the worker workspace.

The target lifecycle is:

provider source -> temporary media/chunks -> analysis -> required scene clips -> narration/timeline -> final render -> validation -> cleanup.

After successful rendering, delete the source episode, unused chunks, and unnecessary intermediates. Preserve only the final output and compact manifests/checkpoints required by the configured retention policy. Failed jobs should clean up safely without deleting the checkpoint/state needed to resume.

This policy prevents episode files from accumulating in GitHub Actions or other workers while keeping the pipeline reliable. The renderer and analysis stages must never assume that the original full episode remains available after the job completes.

## 5. Persistent state
Initial Git-backed state files:
- data/anime.json
- data/episodes.json
- data/scheduler.json
- data/generation_history.json
- data/provider_cache.json

Large media never belongs in these files or in Git history.

## 6. First real milestone
AniMeXe is ready for the first real experiment when it can register four anime, maintain independent episode progress, select two successful jobs per day, accept a supplied episode, analyze it, understand it, generate an original explanation, synthesize narration, match scenes, render a validated MP4, persist success, resume failed work from a checkpoint, and reproduce the process inside GitHub Actions.

No YouTube publishing is required for this milestone.