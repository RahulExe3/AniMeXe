# Episode Analysis

AniMeXe treats episode analysis as a checkpointed, provider-agnostic pipeline.

## Current slice: technical inspection

The first analysis checkpoint is **inspected**. A supplied local episode is passed through `ffprobe`, normalized, fingerprinted, and written as a machine-readable manifest.

Current flow:

\`\`\`text
local episode
    ↓
ffprobe
    ↓
technical inspection
    ↓
analysis manifest
    ↓
checkpoint: inspected
\`\`\`

The inspector records:

- absolute input path
- input byte size
- SHA-256 fingerprint
- inspection timestamp
- ffprobe version when available
- container/format information
- duration and start time
- bitrate when available
- video streams
- audio streams
- subtitle streams
- codec information
- video dimensions
- frame-rate strings
- audio channels/sample rate
- stream language/title tags

The manifest is intentionally normalized so later stages do not need to understand raw ffprobe JSON.

## CLI

Inspect a local episode without attaching it to an episode record:

\`\`\`bash
python -m animexe episode inspect /path/to/episode.mkv
\`\`\`

The default manifest is written under:

\`\`\`text
workspace/analysis/<input-name>.analysis.json
\`\`\`

Attach the inspection checkpoint to the persistent episode state:

\`\`\`bash
python -m animexe episode inspect /path/to/episode.mkv \
  --anime-id mal:12345 \
  --episode-number 4 \
  --season 1
\`\`\`

The episode record then points at the manifest, stores the local source reference, and advances its checkpoint to `inspected`.

For very large files, the fingerprint can be skipped explicitly:

\`\`\`bash
python -m animexe episode inspect /path/to/episode.mkv --no-hash-input
\`\`\`

## Manifest contract

The canonical manifest is implemented by `EpisodeAnalysisManifest` and is schema-versioned.

The current checkpoint chain is:

\`\`\`text
input → inspected → scenes → transcript → story → script → TTS → matching → render
\`\`\`

The `inspected`, `scenes`, and `transcript` transitions are now implemented. Later stages must consume these manifests rather than re-probing or reparsing the source independently.

## Design rules

Technical inspection must remain independent of provider selection, story generation, TTS, and rendering.

A provider may supply a normalized media reference, but the analysis layer should only receive processable media that is already inside the authorized/local input boundary.

Full source media remains temporary workspace data. The compact manifest is the durable reproducibility record.

## Next slice

The next implementation step is scene indexing:

1. detect scene/shot boundaries;
2. extract representative frames;
3. persist a scene manifest;
4. make the scene checkpoint resumable.

Transcript extraction can then consume the same scene/analysis workspace.

## Current scene-indexing checkpoint

The second analysis checkpoint is now implemented:

```text
input → inspected → scenes
```

Scene indexing uses PySceneDetect 0.7.x with ContentDetector. The detector identifies shot changes, then AniMeXe normalizes each scene into a stable SceneRecord.

For every scene AniMeXe records:

- stable scene ID and index
- start/end timestamps
- duration
- representative timestamp
- relative representative-frame path

Representative frames are extracted through FFmpeg and downscaled to the configured width (640 pixels by default). This keeps the visual index compact enough for later AI analysis while leaving the original episode untouched.

The scene manifest also carries the source SHA-256 from the inspection manifest. Before indexing, AniMeXe verifies that the current input still matches that fingerprint. This prevents stale manifests from being silently reused after an input file changes.

If the detector reports no cuts but the inspection manifest has a valid duration, the episode is represented as one scene spanning the full duration. This gives later stages a usable baseline rather than an empty visual index.

## Scene CLI

The current command is:

```bash
python -m animexe episode scenes /path/to/episode.mkv
```

When the inspection manifest is missing, the command creates it first. Otherwise it consumes the existing manifest.

Attach the scene checkpoint to persistent episode state:

```bash
python -m animexe episode scenes /path/to/episode.mkv \
  --anime-id mal:12345 \
  --episode-number 4 \
  --season 1
```

Disable frame extraction when only timestamp analysis is required:

```bash
python -m animexe episode scenes /path/to/episode.mkv --no-frames
```

By default, scene output is placed under:

```text
workspace/analysis/<input-name>/
├── scenes.json
└── frames/
    ├── scene_0001.jpg
    ├── scene_0002.jpg
    └── ...
```

The transcript checkpoint follows scene indexing. Transcript data is aligned to these scene timestamps so story processing can use both spoken content and visual context.

## Current transcript checkpoint

The third analysis checkpoint is now implemented for episodes that contain an embedded text subtitle stream.

Flow:

```text
input → inspected → scenes → transcript
```

AniMeXe:

1. verifies that the input path matches both prior manifests;
2. verifies the current input SHA-256 against the inspection manifest;
3. chooses the preferred embedded subtitle stream (English is preferred by default, followed by Hindi, then the first available text subtitle);
4. asks FFmpeg to convert that stream to SRT;
5. parses timed captions into normalized transcript segments;
6. attaches each caption to every scene whose interval overlaps the caption;
7. writes a versioned transcript manifest.

The extracted source subtitle file is kept beside the manifest as a worker artifact and can be discarded after downstream checkpoints have consumed it.

CLI:

```bash
python -m animexe episode transcript /path/to/episode.mkv
```

Attach the transcript checkpoint to an episode record:

```bash
python -m animexe episode transcript /path/to/episode.mkv \
  --anime-id mal:12345 \
  --episode-number 4 \
  --season 1
```

Default output:

```text
workspace/analysis/<input-name>/
├── source.srt
├── scenes.json
├── transcript.json
└── frames/
```

Episodes without an embedded text subtitle track fail this checkpoint with an explicit message rather than silently creating an empty transcript. The transcript layer is intentionally separated from ASR so a future local ASR adapter (for example, a Whisper-family backend) can be added without changing the story engine or state contract.

The next checkpoint is story understanding: combining episode metadata, scene frames, and transcript segments into a structured episode representation.

## Current story checkpoint

The fourth analysis checkpoint is now implemented as a deterministic extractive evidence layer.

Flow:

```text
input → inspected → scenes → transcript → story
```

The first story pass does not pretend that keyword extraction is full semantic understanding. It creates a reproducible evidence package containing:

- transcript-derived events with scene IDs and timestamps;
- a simple importance score based on timing and text density;
- repeated keyword evidence;
- conservative capitalized-name evidence for potential characters;
- the final transcript event as the current ending candidate;
- continuity notes explicitly identifying the method as extractive.

This gives the later LLM-backed story adapter a stable input/output contract without coupling the rest of AniMeXe to a specific model vendor.

CLI:

```bash
python -m animexe episode story /path/to/episode.mkv
```

Attach the story checkpoint to an episode record:

```bash
python -m animexe episode story /path/to/episode.mkv \
  --anime-id mal:12345 \
  --episode-number 4 \
  --season 1
```

Output:

```text
workspace/analysis/<input-name>/
├── analysis.json
├── scenes.json
├── transcript.json
├── source.srt
├── story.json
└── frames/
```

The story manifest references the transcript and scene manifests used to build it. The next implementation slice is an LLM-backed story explainer that converts this evidence into a structured episode summary suitable for original narration-script generation.


## Current Gemini semantic story checkpoint

The story checkpoint now has an optional Gemini backend. It keeps the deterministic extractive pass available while adding genuine multimodal semantic understanding.

Flow:

```text
input → inspected → scenes + frames → transcript → Gemini story understanding
```

Gemini receives:

- normalized scene metadata;
- transcript segments already aligned to scene IDs;
- representative JPEG frames when available.

The response is requested as structured JSON and validated locally before being persisted. Events must reference real scene IDs, event timing must be valid, importance/confidence must stay in the 0–1 range, and summaries/endings cannot be empty.

Run the offline deterministic pass:

```bash
python -m animexe episode story /path/to/episode.mkv --mode extractive
```

Run the Gemini semantic pass:

```bash
python -m animexe episode story /path/to/episode.mkv --mode gemini
```

Configuration lives under `llm:` in the project config. The API key is read from the configured environment variable, which defaults to `GEMINI_API_KEY`. Never commit the key.

The resulting `story.json` now carries the richer semantic fields needed by the next stage: episode summary, relationships, ending, narration points, confidence, and the Gemini model identifier.

The next checkpoint is original narration-script generation from this semantic story representation.
