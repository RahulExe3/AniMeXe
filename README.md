# AniMeXe

> Anime episode explanation automation — research, episode understanding, narration, clip selection, editing, and rendering.

**Status:** Planning / research phase  
**Repository:** Private  
**Brand:** AniMeXe  
**Current focus:** Build the core automation first. YouTube publishing is intentionally out of scope for the initial implementation.

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

AniMeXe is not a one-anime-at-a-time pipeline. It maintains independent episode progress for multiple active anime and uses a central scheduler to decide which eligible episode jobs should run.

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

### Anime state

Each anime/season maintains persistent state including:

- anime identifier
- title and season
- active/paused/completed status
- next eligible episode
- completed episodes
- failed episodes
- priority
- scheduling history
- playlist identifier

### Intelligent scheduler

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

## 10. Episode analysis

### 6.1 Technical inspection

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

### 6.2 Scene detection

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

### 6.3 Transcript extraction

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

**AniMeXe is in the planning/research stage.**

No production pipeline has been implemented yet.

### Next implementation milestone

> Build a local proof-of-concept that registers multiple anime, maintains independent episode state, selects daily jobs, processes a test episode, detects scenes, generates narration, renders the video, and persists the result.

After that works reliably, add provider automation, playlist management, publishing, and larger-scale processing.

## Source of truth

**The AniMeXe repository is the source of truth for this project.** The README and documentation in this repository should be treated as the canonical record of AniMeXe's architecture, goals, decisions, constraints, implementation status, and planned behavior. Future sessions should read and follow the repository documentation before making assumptions about the project. If a conversation decision changes the architecture or behavior, update the repository documentation so the repo remains the single source of truth.

This is intentional: chat history is context, but the repository is the persistent project memory.

## Project principle

**Build the engine once. Let the scheduler decide what runs next.**

AniMeXe should ultimately manage multiple anime independently, preserve episode continuity, intelligently distribute daily production slots, automatically organize published episodes into playlists, and turn eligible episode inputs into complete narrated explanation videos with minimal manual intervention.
