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

Only the first transition is implemented in this slice. Later stages must consume the manifest rather than re-probing the source independently.

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

The next checkpoint is transcript extraction. Transcript data will be aligned to these scene timestamps so story understanding can use both spoken content and visual context.
