# Gemini story understanding

AniMeXe uses Gemini as an optional semantic layer after local episode inspection, scene indexing, and transcript extraction.

## Current model

The default model is `gemini-3.8-flash`. It is currently a stable Gemini 3 model and supports multimodal inputs and structured outputs. Google recommends the current stable Flash family for new applications.

The integration deliberately uses the Google GenAI Python SDK and a `GEMINI_API_KEY` environment variable. The key must never be written into repository files or persisted state. Google documents environment variables as the recommended authentication pattern.

## Data flow

```text
FFprobe manifest
      ↓
scene index + representative frames
      ↓
embedded subtitle transcript
      ↓
Gemini semantic story understanding
      ↓
structured story.json
      ↓
future script / scene-matching stages
```

Gemini receives the transcript plus scene metadata and, when available, representative JPEG frames. The model does not receive the complete source episode in this checkpoint.

## Structured output

Gemini is instructed to return JSON containing:

- episode summary
- characters
- locations
- keywords
- relationships
- chronological events with scene IDs and timestamps
- ending
- continuity notes
- narration points
- confidence

The response is validated locally before it becomes a story checkpoint. Unknown scene IDs, duplicate event IDs, invalid importance/confidence values, empty summaries, and malformed JSON are rejected instead of silently entering pipeline state.

Google's structured-output support is used so the semantic layer remains machine-readable and deterministic at the boundary. citeturn729201search2turn729201search1

## CLI

Run the deterministic story pass:

```bash
python -m animexe episode story /path/to/episode.mkv --mode extractive
```

Run Gemini understanding:

```bash
python -m animexe episode story /path/to/episode.mkv --mode gemini
```

The Gemini mode reads the existing analysis, scene, and transcript manifests. Representative frames are loaded from the scene-manifest directory when they exist.

## GitHub Actions

Store the API key as a repository or environment secret named:

```text
GEMINI_API_KEY
```

The workflow should expose it only to the command that needs it, for example:

```yaml
env:
  GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

Do not place the key in `config.yml`, `config.example.yml`, JSON state, logs, or generated artifacts.

## Failure behavior

A missing key, missing SDK, failed request, empty response, invalid JSON, or schema-validation error fails the Gemini story checkpoint clearly. The extractive analyzer remains available as an offline fallback.

Gemini is a semantic analysis provider, not the source of truth for media acquisition and not a replacement for the provider boundary.

## Next step

The next layer should consume this richer story manifest to generate an original ~2-minute narration script while preserving event order, source-scene references, and the episode's actual ending.
