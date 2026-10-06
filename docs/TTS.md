# Text-to-Speech

AniMeXe treats TTS as a provider boundary. The narration script is the source of truth for text; TTS creates measured audio and establishes the authoritative narration timeline.

## Backends

The current implementation includes three backends:

- `gemini`: production natural-language narration using Gemini 3.8 Flash TTS.
- `synthetic`: deterministic pure-Python WAV tones for end-to-end pipeline testing. It does not produce speech and does not require FFmpeg.
- `command`: bridges to an external/local TTS runner without hard-coding a large model into the repository.

A production TTS wrapper can also use an open-source engine/model appropriate for the selected language. For the managed Gemini backend, Gemini 3.8 Flash TTS is the flagship current model and supports single-speaker TTS with turn-level `speech_metadata.style`; unary generation returns a WAV file directly. citeturn845316search0turn162182search1

## Configuration

The default test backend is:

```yaml
tts:
  provider: gemini
  model: gemini-3.8-flash-tts
  api_key_env: GEMINI_API_KEY
  voice: Kore
  style: natural, conversational, expressive YouTube narrator; clear sentence endings; natural pauses; believable Hinglish delivery
  timeout_seconds: 180
```

Gemini TTS models detect the input language automatically. Gemini 3.8 Flash TTS supports more than 130 languages, including Hindi and English, and the prebuilt voice catalog includes options such as Kore, Puck, Charon, and many others. citeturn595477view0turn845316search0

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

### Gemini TTS behavior

AniMeXe sends each hook/body/ending segment as a separate TTS request so measured durations can drive the editing timeline. The narration text remains the transcript; sustained tone/prosody instructions stay in `speech_metadata.style`, which matches the current Gemini 3.8 TTS guidance. citeturn595477view0

## Next stage

Scene matching consumes the measured durations and scene IDs. Its output is a declarative edit map that the renderer can consume without containing story logic.
