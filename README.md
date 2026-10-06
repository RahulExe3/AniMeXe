# AniMeXe

> Anime episode explanation automation — research, episode understanding, narration, clip selection, editing, and rendering.

**Status:** Foundation implementation in progress  
**Repository:** Private  
**Brand:** AniMeXe  
**Current focus:** Build the core automation first. The runnable foundation now includes metadata/provider boundaries plus `inspected`, `scenes`, `transcript`, and deterministic `story` evidence checkpoints. YouTube publishing is intentionally out of scope for the initial implementation.

## 1. Vision

AniMeXe is a free-first automation pipeline for producing narrated anime episode explanations.

Target format:

**One episode → understand the episode → write an original explanation → generate natural voiceover → select relevant visual clips → mute source audio → add narration/BGM/SFX → subtitles → final rendered video.**

The system is modular so anime metadata, episode availability, media input, narration, TTS, editing, and publishing remain independent components.

## 2. Core goals

- Automate as much of the production pipeline as practical.
- Prefer free and open-source tools.
- Run locally and in free/low-cost CI where practical.
- Keep source providers replaceable through adapters.
- Generate natural-sounding narration with proper sentence rhythm and pauses.
- Produce clean burned-in subtitles.
- Automatically detect scenes and create a visual index of an episode.
- Match narration segments to appropriate visual scenes.
- Remove original episode audio from selected footage.
- Add configurable background music and sound effects.
- Produce consistent, professional-looking edits.
- Keep temporary media out of Git history.
- Make the system testable without publishing anything.
- Keep scheduling, state, publishing, playlists, and YouTube automation separate from the core renderer.
- Support multiple active anime with independent episode queues.
- Automatically organize successful episodes into anime/season playlists.

## 3. Multi-anime orchestration

AniMeXe is not a one-anime-at-a-time pipeline. It maintains an anime library, monitors release and episode availability, automatically builds an eligible candidate pool, and uses a central scheduler to decide which episode jobs should run.

The active-anime limit is a capacity limit, not a requirement for the user to manually choose four anime. AniMeXe can automatically fill and refill active slots from the library. Manual selection is an optional override.

Initial target:

~~~text
MAX_ACTIVE_ANIME = 4
DAILY_OUTPUT_LIMIT = 2
~~~

Example active state:

~~~text
Jujutsu Kaisen S1  → next episode: 4
Demon Slayer S1    → next episode: 7
Mushoku Tensei S1  → next episode: 5
One Piece           → next episode: 12
~~~

With two daily output slots, AniMeXe may select two different anime on one day and different anime on the next. It never requires one anime to finish before another can progress.

Episode order is enforced independently inside each anime. JJK must progress 1 → 2 → 3 → 4, while Demon Slayer can independently progress 1 → 2 → 3 → 4 → 5 → 6 → 7.

### Anime library and release monitoring

The anime library is the persistent set of anime/season records known to AniMeXe. New anime may enter through automatic discovery or explicit manual addition. Discovery does not automatically consume an active slot.

AniMeXe tracks release state separately from production state. A not-yet-released anime must not consume an active slot. When its premiere becomes available, it becomes eligible for consideration. An airing anime that has caught up to its latest available episode remains in the library as WAITING_FOR_NEXT_EPISODE rather than blocking an active slot.

For airing anime, AniMeXe periodically refreshes configured metadata providers and detects newly available episodes. A newly detected episode becomes PENDING when episode continuity and other eligibility rules permit it. Temporary provider failures must not be treated as evidence that no episode exists.

The monitor should persist latest known episode, next expected episode, release status, next airing time when available, last refresh, provider observation, and availability errors.

### Anime state

Each anime/season maintains persistent state including:

- anime identifier
- title and season
- discovery source
- release/airing status
- latest known episode
- next expected episode
- next airing timestamp when available
- active/paused/completed/waiting status
- next eligible episode
- completed episodes
- failed episodes
- priority
- scheduling history
- playlist identifier

### Intelligent scheduler

The scheduler first fills available active slots from the eligible candidate pool, up to MAX_ACTIVE_ANIME. When an active anime finishes, pauses, becomes unavailable, or catches up to an airing schedule, its slot may be filled by another eligible candidate. When a waiting airing anime receives a new episode, it returns to the candidate pool and may become active again according to the configured strategy.

The scheduler chooses jobs from eligible anime using configurable signals:

- daily output budget
- active-anime limit
- episode continuity
- priority
- fairness/history
- failed jobs
- source availability
- paused/completed status
- processing capacity
- optional manual overrides

Supported scheduling strategies should include:

- **Balanced:** distribute slots fairly across active anime.
- **Priority:** prefer higher-priority anime without blocking all other active anime.
- **Flexible:** vary selection using eligibility, history, availability, and controlled randomness.

Priority is a scheduling signal, not a command to finish one anime first.

### Episode job state

Every episode is an independent job:

~~~text
PENDING → QUEUED → PROCESSING → RENDERED → READY → PUBLISHED
                    ↓
                  FAILED
~~~

A failed Episode 8 must remain Episode 8 until it succeeds. Only the configured success checkpoint may advance an anime's next episode.

### Daily limit

The daily limit is configurable. The initial default is two successful outputs per day. The system should distinguish production attempts from successful outputs so a failed job does not silently consume an intended publishing slot unless explicitly configured.

## 4. Publishing and playlist automation

Publishing is a separate layer from production, but the eventual automated system should automatically organize successful videos.

For each anime/season, AniMeXe should maintain a corresponding playlist:

~~~text
Jujutsu Kaisen — Season 1
├── Episode 1 Explanation
├── Episode 2 Explanation
├── Episode 3 Explanation
└── Episode 4 Explanation
~~~

When an episode is successfully published, AniMeXe should resolve or create the correct anime/season playlist, add the video, preserve episode order, and persist the playlist/video IDs.

A publishing failure must not force an already-rendered episode to be regenerated.

## 5. Anime lifecycle and persistence

Anime lifecycle:

~~~text
DISCOVERED → ACTIVE ↔ PAUSED → COMPLETED
                 ↓
              FAILED / UNAVAILABLE / ARCHIVED
~~~

Persistent state is required so restarts and failed workflows cannot lose episode progress.

Prototype state storage can use JSON or SQLite. The state layer should remain replaceable so a database-backed implementation can be introduced later.

State should track three levels:

1. **Anime:** identity, season, status, priority, next episode, playlist, history.
2. **Episode:** number, status, attempts, source, render result, video ID, failure reason.
3. **Scheduler:** daily limit, selected jobs, successful outputs, history/fairness data.

## 6. Expanded architecture

~~~text
                         AniMeXe Controller
                                │
                         Anime Discovery
                                │
                         Release Monitor
                                │
                         Candidate Pool
                                │
                         Active Slots ≤ 4
                                │
                                ↓
                                │
             ┌──────────────────┴──────────────────┐
             ↓                                     ↓
       Anime Library                           Scheduler
             │                                     │
      ┌──────┼─────────┐                           ↓
      ↓      ↓         ↓                    Daily Job Queue
     JJK     DS        OP                           │
      │      │         │                           ↓
      └──────┴─────────┴────────────────────→ Production
                                                   │
                                      Metadata + Episode Input
                                                   ↓
                                           Episode Analysis
                                                   ↓
                                           Story Understanding
                                                   ↓
                                           Explanation Script
                                                   ↓
                                                  TTS
                                                   ↓
                                           Scene Matching
                                                   ↓
                                          Clip Generation
                                                   ↓
                                         Audio + Subtitles
                                                   ↓
                                            FFmpeg Render
                                                   ↓
                                         Publishing Adapter
                                                   ↓
                                         Playlist Association
~~~

Production, scheduling, state, and publishing must remain separate modules.

## 7. Non-goals for the first version

- YouTube channel creation.
- Automatic publishing.
- Thumbnail generation.
- Channel analytics.
- Subscriber tracking.
- Final publishing/branding decisions.
- A public hosted anime streaming service.

The first milestone is a reliable **multi-anime scheduler + episode → finished explanation video** pipeline.

## 8. High-level production pipeline

```
Anime selection
      ↓
Metadata / Identity
(AniList / Jikan etc.)
      ↓
Episode information
      ↓
Media Input
(provider / local)
      ↓
Episode inspection
(duration / scenes / transcript)
      ↓
Story understanding
      ↓
Explanation script
      ↓
Natural TTS
      ↓
Narration timing
      ↓
Scene ↔ narration matching
      ↓
FFmpeg renderer
      ↓
Subtitles + BGM/SFX
      ↓
Final MP4
```

## 9. Provider abstraction

The media layer must be provider-agnostic.

Planned structure:

```text
providers/
├── anilist/
├── jikan/
├── official/
├── archive/
└── local/
```

A provider should expose normalized data instead of leaking provider-specific formats into the rest of the application.

Example normalized episode object:

```json
{
  "anime_id": "provider-independent-id",
  "title": "Example Anime",
  "season": 1,
  "episode": 1,
  "episode_title": "Example Episode",
  "duration": 1440,
  "thumbnail": "...",
  "source": {
    "provider": "example",
    "type": "local-or-authorized-media",
    "reference": "..."
  }
}
```

The renderer must work from this normalized object.

### Source research findings

The research phase identified:

- **AniList:** strong free anime identity/metadata layer.
- **Jikan:** free MyAnimeList-derived metadata/episode layer.
- **TMDB:** useful for season/episode metadata and watch-provider discovery.
- **Watchmode:** useful for streaming-availability discovery, with free-tier limitations.
- **Official anime distributors:** selected titles are available free on YouTube in particular territories.
- **Public-domain/archive material:** useful for genuinely reusable historical animation.
- **GitHub anime API projects:** useful for understanding provider-adapter architecture, but a public API does not automatically grant rights to redistribute its media.

The architecture therefore separates **metadata discovery**, **media acquisition**, and **media processing**.



### Temporary media and storage policy

AniMeXe must not permanently store full source episodes. Provider media should be treated as disposable processing input.

Preferred flow:

~~~text
Provider/source reference
        ↓
Stream or fetch media incrementally
        ↓
Temporary workspace/chunks
        ↓
Analyze episode and identify required scenes
        ↓
Extract only required clips
        ↓
Generate narration + timeline
        ↓
Render final video
        ↓
Validate output
        ↓
Delete source chunks and unnecessary intermediates
~~~

The processing layer may use temporary disk space when required by FFmpeg, scene detection, seeking, or rendering, but the complete source episode must not become persistent project storage. Temporary media is deleted after a successful job, and failed jobs should clean up safely while preserving only the checkpoints and small metadata needed for retry.

This keeps GitHub Actions and other workers from accumulating episode files while preserving reliable checkpointed processing. If a provider supports range requests, HLS/DASH segments, or timestamp-based extraction, the media adapter should prefer targeted retrieval over downloading the complete episode.

## 10. Episode analysis

### 10.1 Technical inspection

Extract:

- resolution
- FPS
- duration
- codecs
- audio streams
- subtitle streams
- keyframes
- scene timestamps

FFmpeg is the primary media-processing dependency.


### Scene indexing checkpoint

The analysis layer now detects shot changes with PySceneDetect, extracts compact representative frames through FFmpeg, and persists a fingerprinted scene manifest. The scene index is the visual substrate for later transcript alignment and story understanding.

CLI:

```bash
python -m animexe episode scenes /path/to/episode.mkv
```

See `docs/ANALYSIS.md` for the manifest contract and checkpoint behavior.

### 10.2 Scene detection

Use PySceneDetect/OpenCV or an equivalent detector to identify hard cuts and create a scene index.

Example:

```text
scene_001  00:00.0 → 00:08.4
scene_002  00:08.4 → 00:13.9
scene_003  00:13.9 → 00:21.2
...
```

Each scene should retain:

- start/end timestamp
- representative frame
- duration
- optional visual embedding
- optional transcript overlap

### 10.3 Transcript extraction

If subtitles/audio are available, extract them for analysis.

If speech recognition is required, use an open-source Whisper/faster-whisper style pipeline.

The transcript is an **analysis input**, not the narration itself.

## 11. Story understanding

The system should understand the episode before generating narration.

Target intermediate representation:

```json
{
  "episode": 1,
  "summary": "...",
  "characters": [],
  "locations": [],
  "events": [
    {
      "order": 1,
      "description": "...",
      "importance": 0.92,
      "scene_candidates": [3, 4, 5]
    }
  ],
  "ending": "...",
  "continuity_notes": []
}
```

Narration requirements:

- Preserve chronological order.
- Identify important character actions.
- Explain context when necessary.
- Avoid inventing events.
- Avoid confusing similarly named characters.
- Detect episode/season boundaries.
- Handle recaps and openings/endings intelligently.
- Keep the explanation engaging instead of reading a transcript.

## 12. Narration and TTS

TTS is a replaceable module.

Required capabilities:

- free/local option where possible
- Hindi/Hinglish pronunciation
- configurable voice
- sentence-level generation
- controllable speaking rate
- reliable audio-duration reporting
- clean WAV/MP3 output
- retry/fallback support

Example:

```json
[
  {
    "id": 1,
    "text": "...",
    "audio": "segment_001.wav",
    "duration": 4.82
  }
]
```

### Text-cleaning rules

Remove artifacts such as:

- `---`
- `____`
- unnecessary em-dashes
- markdown separators
- unnecessary headings
- accidental stage directions
- repeated punctuation
- raw JSON/code fragments

Punctuation must remain meaningful because it affects TTS prosody.

## 13. Scene ↔ narration matching

This is one of the most important components.

Matching signals can include:

1. Chronological story position.
2. Transcript overlap.
3. Scene timestamps.
4. Character/entity recognition.
5. Visual similarity.
6. Scene importance.
7. Narration duration.
8. Repetition penalties.

Example:

```text
Narration 01
  ↓
candidate scenes 03, 04, 05
  ↓
scene 04 selected
```

The system should avoid repeatedly showing the same scene unless intentionally requested.

## 14. Clip generation

Selected scenes become editable clips.

Support:

- configurable maximum/minimum clip duration
- start/end padding
- hard-cut alignment
- optional creative zoom/crop
- aspect-ratio conversion
- safe subtitle area
- optional transitions
- original-audio mute

Visual transformations are for creative presentation only, not for bypassing copyright detection or platform protections.

## 15. Audio mix

Final layers:

```text
Narration ────────────────┐
BGM ─────────────────────┼──→ Master mix
SFX ─────────────────────┘
Original episode audio ── X
```

Default behavior:

- source episode audio muted
- narration dominant
- BGM ducked under narration
- optional SFX
- loudness normalization
- no clipping

BGM/SFX should come from sources permitted for the intended use.

## 16. Subtitles

Generate subtitles from final narration timing.

Support:

- burned-in subtitles
- optional SRT/VTT
- sentence/word timing where supported
- mobile-friendly layout
- automatic line breaking
- configurable styling

## 17. Rendering

FFmpeg is the core rendering engine.

The renderer should consume a declarative timeline rather than contain story logic.

Example:

```json
{
  "canvas": {
    "width": 1920,
    "height": 1080,
    "fps": 30
  },
  "segments": [
    {
      "video": "scene_004.mp4",
      "start": 0,
      "duration": 4.82,
      "narration": "segment_001.wav"
    }
  ]
}
```

## 18. Planned repository layout

```text
AniMeXe/
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PIPELINE.md
│   ├── PROVIDERS.md
│   ├── TTS.md
│   ├── RENDERING.md
│   └── ROADMAP.md
├── src/
│   ├── metadata/
│   ├── providers/
│   ├── analysis/
│   ├── story/
│   ├── narration/
│   ├── scenes/
│   ├── subtitles/
│   ├── audio/
│   └── render/
├── tests/
├── config/
├── scripts/
├── workflows/
├── assets/
│   ├── music/
│   ├── sfx/
│   └── fonts/
├── workspace/
│   ├── input/
│   ├── analysis/
│   ├── narration/
│   ├── clips/
│   ├── timeline/
│   └── output/
└── .github/
    └── workflows/
```

Large media files must remain outside Git history.

## 19. Free-first technology strategy

Preferred open-source/free components:

- Python for orchestration and analysis.
- FFmpeg for media processing.
- OpenCV for visual processing.
- PySceneDetect for scene detection.
- Whisper/faster-whisper ecosystem for transcription.
- AniList/Jikan for metadata.
- Local/open-source models where practical.
- GitHub Actions for tests/builds where workload fits free limits.

The architecture must allow paid APIs/models to be swapped in later without rewriting the pipeline.

## 20. Configuration

No secrets should be hard-coded.

Example:

```yaml
project:
  name: AniMeXe
  language: hinglish

episode:
  input_mode: provider
  scene_detection: true

narration:
  style: conversational
  language: hinglish
  speed: 1.0

video:
  resolution: 1920x1080
  fps: 30
  max_clip_duration: 8

audio:
  mute_source: true
  bgm: true
  sfx: optional

subtitles:
  enabled: true
  burn_in: true
```

Secrets belong in environment variables or GitHub Actions secrets.

## 21. Implementation phases

### Phase 1 — Foundation
- Repository structure.
- Configuration.
- Logging.
- Workspace management.
- FFmpeg detection.
- Basic tests.

### Phase 2 — Anime metadata
- AniList integration.
- Jikan fallback.
- Episode normalization.
- Season/episode handling.

### Phase 3 — Media input abstraction
- Local-file provider.
- Provider interface.
- Source availability metadata.
- Pluggable authorized/owned media inputs.

### Phase 4 — Episode analysis
- FFmpeg inspection.
- Scene detection.
- Frame extraction.
- Transcript extraction.
- Scene index.

### Phase 5 — Story engine
- Episode event extraction.
- Chronological story representation.
- Explanation generation.
- Script validation.

### Phase 6 — Voice
- TTS adapter interface.
- Local/free voice implementation.
- Segment-level audio.
- Prosody/text cleanup.

### Phase 7 — Intelligent editing
- Narration-to-scene matching.
- Clip generation.
- Timeline generation.
- Audio mixing.
- Subtitles.

### Phase 8 — Renderer
- FFmpeg renderer.
- Templates.
- Final quality checks.
- MP4 output.

### Phase 9 — Optional automation
Only after the core pipeline is stable:
- scheduled jobs
- queue management
- batch processing
- optional YouTube integration

## 22. Quality gates

A job should fail instead of silently producing a bad video when:

- episode metadata is inconsistent
- media duration is invalid
- scene detection produces unusable output
- narration generation is empty
- TTS contains unresolved placeholders
- narration audio is missing
- subtitles have invalid timestamps
- output has no video stream
- output has no narration
- final duration is unexpectedly short
- FFmpeg exits unsuccessfully

Every job should produce a machine-readable report.

## 23. Reproducibility

Each generated project should store:

- anime identifier
- season
- episode number
- metadata snapshot
- provider name
- processing configuration
- model/TTS configuration
- scene timestamps
- narration script
- narration audio manifest
- timeline
- renderer version
- generation timestamp

This makes failed jobs reproducible and debuggable.

## 24. Key design decisions

### Source abstraction
Provider-specific URLs and response formats must never leak into the renderer.

### Media is temporary
Episodes, extracted scenes and intermediate renders are build artifacts and must not enter Git history.

### Narration is the primary track
The final video should remain understandable from narration alone.

### Editing is data-driven
The renderer consumes a timeline rather than containing story logic.

### No detection-evasion design
Creative transformations may be used for presentation, but not as a mechanism to bypass copyright detection or platform protections.

### Publishing is separate
AniMeXe first becomes a reliable video-production engine. YouTube automation is a later adapter.

## 25. Research references

The research phase identified:

- AniList — anime identity and metadata.
- Jikan — MyAnimeList-derived metadata.
- TMDB — TV/season/episode metadata and availability.
- Watchmode — streaming availability discovery.
- Consumet — open-source provider/API architecture reference.
- Anivexa API — multi-provider anime API architecture reference.
- Blitz Anime API — multi-provider API architecture reference.
- PySceneDetect — scene detection.
- FFmpeg — video/audio processing.
- Whisper/faster-whisper ecosystem — transcription.

These are architecture/integration references. Public availability of an API or scraper does not itself establish permission to redistribute its media.

## 26. Current status

**AniMeXe is in active foundation implementation.**

The repository now contains a runnable Python package, CLI, persistent JSON state, scheduler planner, normalized provider boundary, LocalProvider, AniList/Jikan metadata, Kuhi catalog/health integration, GitHub Actions CI, and the first episode-analysis checkpoint. A supplied local episode can be inspected with ffprobe and persisted as a schema-versioned analysis manifest.

See `docs/ANALYSIS.md` for the current inspection contract and the next scene-indexing step.

### Next implementation milestone

> Build a local proof-of-concept that registers multiple anime, maintains independent episode state, selects daily jobs, processes a test episode, detects scenes, generates narration, renders the video, and persists the result.

After that works reliably, add provider automation, playlist management, publishing, and larger-scale processing.

## Source of truth

**The AniMeXe repository is the source of truth for this project.** The README and documentation in this repository should be treated as the canonical record of AniMeXe's architecture, goals, decisions, constraints, implementation status, and planned behavior. Future sessions should read and follow the repository documentation before making assumptions about the project. If a conversation decision changes the architecture or behavior, update the repository documentation so the repo remains the single source of truth.

This is intentional: chat history is context, but the repository is the persistent project memory.

## Project principle

**Build the engine once. Let the scheduler decide what runs next.**

AniMeXe should ultimately manage multiple anime independently, preserve episode continuity, intelligently distribute daily production slots, automatically organize published episodes into playlists, and turn eligible episode inputs into complete narrated explanation videos with minimal manual intervention.

## 27. Current implementation blueprint

The anime library, release monitor, candidate pool, and active-slot manager are first-class parts of the scheduler. Four is the maximum number of active production candidates, not a fixed list supplied by the user.

Airing anime are monitored even when waiting for their next episode. A newly detected episode re-enters the scheduling pool automatically. Not-yet-released anime remain in the library without consuming active capacity.

The implementation now follows the practical execution pattern proven in YTAutoPilot while keeping AniMeXe modular and provider-agnostic.

### Build order

1. Foundation and CLI.
2. Persistent anime/episode/scheduler state.
3. AniList/Jikan metadata normalization.
4. Provider foundation and normalized media models.
5. Kuhi primary provider.
6. Anivexa secondary provider.
7. Local/manual episode input boundary.
8. FFprobe, scene detection, frame extraction, and transcript analysis.
9. Story understanding and original explanation generation.
10. Local/free TTS with sentence-level timing.
11. Narration-to-scene matching and declarative timeline generation.
12. BGM/SFX, subtitles, source-audio mute, and FFmpeg rendering.
13. Validation and machine-readable artifacts.
14. Multi-anime scheduler, discovery, and episode monitoring.
15. GitHub Actions worker, caching, checkpoints, artifacts, and persistent state commits.
16. Publishing and playlist automation only after production is stable.

### GitHub Actions operating model

The first hosted worker will follow:

checkout → restore caches → install/check FFmpeg → load state → schedule → process → validate → upload artifacts → persist state → rebase main → push state.

The workflow will initially expose dry-run, analyze, render, and scheduled modes. YouTube publishing remains disabled.

### YTAutoPilot-derived operational patterns

AniMeXe will reuse the proven ideas of:

- warm Python/model caches;
- explicit media-tool checks;
- environment-based configuration;
- machine-readable manifests;
- persistent JSON state;
- workflow artifacts;
- checkpointed retries;
- Git-backed state persistence;
- fetch/rebase/push state commits;
- clear workflow and visual verification gates.

YTAutoPilot's gaming-specific content and publishing code are not part of AniMeXe.

### Provider strategy

Provider research has moved beyond the older Kitsune-first model.

**Primary external media-provider target:** Kuhi / `aryaniiil/anime-api`.

**Secondary provider/reference targets:** Anivexa API, Anivault Scraper, StreamPlay, anime-sdk, and vetted CloudStream-style extensions.

Kitsune remains a legacy/reference integration rather than the architectural center. See `docs/PROVIDERS.md` for the detailed registry, normalization contract, health model, fallback policy, and research notes.

The provider boundary is:

```
metadata identity
      ↓
episode availability
      ↓
provider source resolution
      ↓
normalized MediaSource
      ↓
episode processing
```

Metadata existence must never be treated as proof that usable media exists.

### Checkpointed episode processing

An episode can resume from its last successful stage instead of restarting from the beginning.

Example:

input ✓ → metadata ✓ → scenes ✓ → transcript ✓ → story ✓ → script ✓ → TTS ✗ → matching pending → render pending

This is required both locally and in GitHub Actions.

For the detailed blueprint, see docs/BUILD_PLAN.md, docs/PROVIDERS.md, docs/SCHEDULER.md, and docs/CI.md.

### First real milestone

The first real milestone is a working multi-anime production engine that can register four anime, maintain independent episode progress, select two successful jobs per day, accept a supplied episode, analyze it, generate an original explanation and narration, match scenes, render a validated MP4, persist the result, resume failed work from checkpoints, and reproduce the process in GitHub Actions.

YouTube publishing is not required for this milestone.

### Story evidence checkpoint

AniMeXe now assembles transcript-derived events, scene links, keywords, conservative character evidence, and an ending candidate into a persistent `story.json`. This first pass is deterministic/extractive; the next story layer will add a pluggable LLM backend for genuine semantic episode understanding.

```bash
python -m animexe episode story /path/to/episode.mkv
```

### Transcript checkpoint

AniMeXe now has a third analysis checkpoint: embedded timed subtitles are converted into normalized transcript segments and aligned to overlapping scene IDs. The input fingerprint is verified again before extraction. Episodes without a text subtitle track stop with an explicit error; the transcript interface remains ready for a future local ASR adapter.

```bash
python -m animexe episode transcript /path/to/episode.mkv
```

See `docs/ANALYSIS.md` for the analysis contracts.
