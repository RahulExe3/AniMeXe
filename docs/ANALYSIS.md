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
