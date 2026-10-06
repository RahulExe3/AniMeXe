# AniMeXe Build Plan

> The implementation blueprint. The AniMeXe repository remains the source of truth.

## 1. Product shape

AniMeXe is a reusable episode-production engine:

`anime library → scheduler → episode job → provider/local input → inspection → analysis → story → script → TTS → scene matching → timeline → audio/subtitles → FFmpeg render → validation → state/artifact`

Publishing is a later adapter and is not part of the first production milestone.

## 2. Operational principles

The implementation follows the proven operational ideas from YTAutoPilot without copying its gaming-specific content code:

- Python package with one CLI entry point.
- Workflow-dispatch CI before scheduled automation.
- Warm dependency/model caches where useful.
- Explicit FFmpeg/ffprobe checks.
- Environment-based configuration.
- Machine-readable manifests and reports.
- Persistent JSON state under `data/`.
- Workflow artifacts for debugging.
- Checkpointed retries.
- Git-backed state persistence with safe rebase/fetch before state pushes.
- Clear distinction between committed, workflow-tested, and visually verified behavior.

## 3. Build order

### Phase 0 — Foundation
**Now.** Build the Python package, CLI, configuration loader, logging, canonical paths, Git-friendly state directories, tests, and basic job-report primitives.

Initial commands:

```bash
python -m animexe init
python -m animexe status
python -m animexe anime list
python -m animexe episode list
python -m animexe plan
```

### Phase 1 — State engine
Implement anime, season, episode, scheduler, checkpoint, attempt, failure, and generation-history models.

Requirements:
- independent episode progress per anime;
- failed episodes remain the current episode;
- atomic JSON writes;
- schema-versioned state;
- restart-safe recovery.

Initial state files:

```text
data/
├── anime.json
├── episodes.json
├── scheduler.json
├── generation_history.json
└── provider_cache.json
```

### Phase 2 — Metadata
Implement AniList identity lookup, Jikan fallback, season/episode normalization, release-state tracking, and provider-independent IDs.

Metadata existence must never imply episode media availability.

### Phase 3 — Provider foundation
Create the provider interface and normalized media boundary:

```text
EpisodeRef
EpisodeAvailability
MediaSource
```

Also implement:
- provider registry;
- provider health states;
- retry/backoff;
- cache boundaries;
- request/error normalization;
- LocalProvider fixtures.

Providers must remain replaceable and must never leak provider-specific response structures into the scheduler or renderer.

### Phase 4 — Kuhi primary provider
Implement `src/providers/kuhi` against the verified Kuhi / `aryaniiil/anime-api` contract.

The adapter must:
- search and identify anime;
- resolve seasons and episodes;
- validate title/season/episode continuity;
- resolve actual media sources;
- validate media usability;
- expose subtitles/audio metadata;
- report provider health;
- prefer Kuhi's native provider layer over legacy fallbacks.

A provider result is not accepted merely because metadata exists.

### Phase 5 — Anivexa secondary provider
Implement `src/providers/anivexa` with the same normalized contract.

Use it as a fallback when Kuhi cannot provide a usable source. Keep strict episode/catalog validation and isolate all Anivexa-specific response details inside the adapter.

### Phase 6 — Local/manual media input
Support a supplied local episode file as the mandatory development path.

Local media must enter through the same normalized media boundary as external providers so the rest of the pipeline stays provider-agnostic.

### Phase 7 — Episode analysis

Current sub-checkpoints:
- **inspected:** ffprobe technical manifest with input fingerprint and stream metadata.
- **scenes:** PySceneDetect cut detection plus representative-frame extraction.
- **next:** transcript/subtitle extraction aligned to the scene timeline.

Implement:
- ffprobe technical inspection;
- scene detection;
- representative frame extraction;
- subtitle/transcript extraction;
- optional Whisper/faster-whisper transcription;
- analysis manifest generation.

Checkpoint chain:

`input → inspected → scenes → transcript`

### Phase 8 — Story engine
Convert analysis into a structured episode representation containing:
- events;
- characters;
- locations;
- importance;
- ending;
- continuity notes;
- candidate scenes.

Generate and validate an original explanation script from that representation.

### Phase 9 — Narration
Build a replaceable TTS interface with:
- free/local-first implementation;
- Hinglish-friendly pronunciation;
- sentence-level generation;
- duration measurement;
- punctuation-aware pacing;
- retries/fallbacks;
- clean audio manifests.

### Phase 10 — Intelligent editing
Match narration segments to scenes using:
- chronology;
- transcript overlap;
- entities;
- scene importance;
- visual similarity where available;
- duration fit;
- repetition penalties.

Generate a declarative timeline. The renderer should consume the timeline rather than contain story logic.

### Phase 11 — Audio, subtitles, and rendering
Build:
- source-audio mute;
- narration mix;
- ducked BGM;
- optional SFX;
- clean subtitle generation;
- burned-in subtitles;
- FFmpeg rendering;
- final media validation.

Quality gates must reject incomplete or suspicious output.

### Phase 12 — Anime discovery and scheduler
Build:
- anime library discovery;
- release monitoring;
- candidate pool;
- active-slot management;
- independent episode queues;
- Balanced / Priority / Flexible strategies.

Initial limits:
- `MAX_ACTIVE_ANIME = 4`
- `DAILY_OUTPUT_LIMIT = 2` successful outputs

Not-yet-released anime do not consume active slots. Airing anime that catch up to the latest episode enter `WAITING_FOR_NEXT_EPISODE` and can leave active capacity until a new episode becomes eligible.

### Phase 13 — GitHub Actions worker
Run the production worker through:

`checkout → restore caches → install/check tools → load state → schedule → process → validate → artifacts → persist state → fetch/rebase/push`

Initial modes:
- `dry-run`
- `analyze`
- `render`
- scheduled execution

YouTube publishing remains disabled here.

### Phase 14 — Publishing
Only after production is reliable:
- upload;
- playlist association;
- ordering;
- deduplication;
- retry;
- publishing-state persistence.

A publishing failure must never force an already-rendered episode to be regenerated.

## 4. Checkpointing

Every expensive stage should write a checkpoint manifest containing:
- input fingerprint;
- configuration fingerprint;
- tool/model versions;
- outputs;
- timestamp;
- validation result.

Example recovery state:

`input ✓ → metadata ✓ → scenes ✓ → transcript ✓ → story ✓ → script ✓ → TTS ✗ → matching pending → render pending`

The next run resumes at the failed stage.

## 5. Temporary media strategy

Source episodes are processing inputs, not permanent project assets.

Preferred lifecycle:

`provider reference → temporary media/chunks → analysis → required clips → narration/timeline → render → validation → cleanup`

Use streaming, range requests, HLS/DASH segments, or targeted extraction when the media source supports them. Full materialization is allowed only as temporary worker workspace when random access requires it.

Successful jobs should delete source media and unnecessary intermediates while preserving the final artifact and compact manifests required for reproducibility. Failed jobs must clean up safely without deleting recovery checkpoints.

## 6. Reproducibility

Each episode generation should record:
- anime/season/episode identity;
- metadata snapshot;
- provider;
- media reference;
- processing configuration;
- TTS/model configuration;
- scene index;
- script;
- narration manifest;
- timeline;
- renderer version;
- generation timestamp;
- validation report.

## 7. First real milestone

The first real experiment is complete when AniMeXe can:

1. register multiple anime with independent episode state;
2. select eligible jobs under the daily budget;
3. accept a supplied episode;
4. inspect and analyze it;
5. understand the episode;
6. generate an original explanation;
7. synthesize narration;
8. match narration to scenes;
9. render a validated MP4;
10. persist success and resume failures from checkpoints;
11. reproduce the process inside GitHub Actions.

YouTube publishing is not required for this milestone.

## 8. Current implementation status

**Foundation and metadata/provider implementation are in progress; episode analysis has now started.**

Completed in the current implementation slice:
- Python package;
- CLI;
- config model/loader;
- canonical project paths;
- schema-versioned JSON state;
- atomic state writes;
- first scheduler planner;
- normalized provider models;
- provider interface and registry;
- LocalProvider input adapter;
- provider tests;
- GitHub Actions CI with compile and test checks;
- AniList/Jikan metadata clients and normalized AnimeMetadata;
- metadata fallback service;
- metadata CLI commands;
- metadata configuration and contract tests;
- metadata-to-library upsert and identity merging;
- Kuhi catalog/health boundary;
- provider factory/registry wiring;
- ffprobe-based episode inspection;
- schema-versioned episode analysis manifests;
- persisted episode inspection checkpoints;
- episode inspection tests.
- PySceneDetect scene indexing with representative-frame extraction and fingerprint validation.

Next implementation slice: **transcript extraction aligned to the scene index**.
