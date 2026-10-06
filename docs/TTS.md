# Text-to-Speech

AniMeXe treats TTS as a provider boundary. The narration script is the source of truth for text; TTS creates measured audio and establishes the authoritative narration timeline.

## Backends

The current implementation includes two backends:

- `synthetic`: deterministic pure-Python WAV tones for end-to-end pipeline testing. It does not produce speech and does not require FFmpeg.
- `command`: bridges to an external/local TTS runner without hard-coding a large model into the repository.

A production TTS wrapper can use an open-source engine/model appropriate for the selected language. AI4Bharat documents explicit English, Hindi, and Hinglish TTS support in its Indic-TTS inference package. citeturn538629search3

## Configuration

The default test backend is:

```yaml
tts:
  provider: synthetic
  voice: null
  command: []
  timeout_seconds: 180
```

For a real local/external engine:

```yaml
tts:
  provider: command
  voice: narrator
  timeout_seconds: 180
  command:
    - python
    - tools/tts_runner.py
    - "{text_file}"
    - "{output_file}"
```

The command receives placeholders for the text file, output WAV path, narration language, writing-system mode, segment ID, and configured voice.

## Manifest

The TTS checkpoint is:

```text
workspace/narration/<input-name>/
├── script.json
├── audio/
│   ├── 0001_hook.wav
│   ├── 0002_segment_0001.wav
│   └── ...
└── tts.json
```

Each audio segment records measured duration, sample rate, channels, source text, scene IDs, and filename.

The manifest also stores:

- source script;
- language;
- writing-system mode;
- provider;
- voice;
- total measured duration.

Hook and ending are synthesized as first-class segments so the complete narration has authoritative timing.

## CLI

Synthetic end-to-end audio:

```bash
python -m animexe episode tts /path/to/episode.mkv
```

Persist the checkpoint to an episode record:

```bash
python -m animexe episode tts /path/to/episode.mkv \
  --anime-id mal:12345 \
  --episode-number 4
```

The TTS stage consumes the previously generated `script.json`. No new story or script generation happens here.

## Next stage

Scene matching consumes the measured durations and scene IDs. Its output is a declarative edit map that the renderer can consume without containing story logic.
