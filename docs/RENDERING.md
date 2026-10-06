# Rendering

AniMeXe keeps rendering separate from story and scene-selection logic. The renderer consumes a declarative timeline created from measured narration audio and scene matches.

## Checkpoint chain

```text
story
  ↓
script
  ↓
TTS
  ↓
matching
  ↓
timeline
  ↓
render
```

The timeline is the contract between intelligent editing and FFmpeg.

## Timeline contents

The timeline records:

- source input path and fingerprint;
- ordered source-scene clips;
- source start/end timestamps;
- timeline start/end timestamps;
- narration audio files;
- measured narration duration;
- subtitle text and timing;
- upstream matching/TTS manifests.

Example:

```json
{
  "segment_id": "segment_0004",
  "scene_id": "scene_0017",
  "source_start_seconds": 82.4,
  "source_end_seconds": 87.9,
  "timeline_start_seconds": 31.2,
  "timeline_end_seconds": 36.7
}
```

## FFmpeg renderer

The current renderer:

1. reads the source episode once;
2. trims the matched scene intervals;
3. normalizes the output canvas/FPS;
4. concatenates the video clips;
5. deliberately ignores source episode audio;
6. delays measured narration audio to its timeline position;
7. optionally loops a supplied local BGM track at low volume and ducks it under narration;
8. mixes the narration/BGM master;
9. optionally burns the generated SRT subtitles;
9. writes an MP4 with H.264 video and AAC audio.

The renderer contains no scene-scoring or story-generation logic.

## Subtitles

The renderer also writes a sidecar SRT next to the final output. When subtitle burn-in is enabled, FFmpeg uses that SRT as the subtitle source.

Subtitle timing comes from measured TTS durations, not the provisional script anchors.

## CLI

Build the declarative timeline:

```bash
python -m animexe episode timeline /path/to/episode.mkv
```

Render:

```bash
python -m animexe episode render /path/to/episode.mkv
```

Persist the render checkpoint:

```bash
python -m animexe episode render /path/to/episode.mkv \
  --anime-id mal:12345 \
  --episode-number 4
```

Disable subtitle burn-in for a render:

```bash
python -m animexe episode render /path/to/episode.mkv --no-subtitles
```

## Current scope

The first renderer milestone intentionally focuses on:

- source-audio removal;
- narration mix;
- subtitles;
- stable scene cuts;
- deterministic output validation.

BGM/SFX mixing and richer transition/crop effects remain separate follow-up layers so they do not complicate the core timeline contract.
