# Narration Script

AniMeXe separates semantic story understanding from narration language. The story checkpoint is language-neutral; the script checkpoint turns that story into the spoken explanation that the TTS layer will later voice.

## Supported languages

AniMeXe currently supports two narration modes:

| Language | Writing system | Intended style |
|---|---|---|
| `english` | `latin` | Natural spoken English |
| `hinglish` | `roman` | Natural Hindi-English speech written in Roman script |

Hinglish is deliberately controlled rather than randomly mixing languages. Hindi remains the conversational base, while English words are used where they sound natural for the speaker.

The same semantic `story.json` can generate either language. Story analysis is therefore performed once.

## Duration target

The default target is approximately two minutes:

```yaml
narration:
  language: hinglish
  script: roman
  target_duration_seconds: 120
  min_duration_seconds: 105
  max_duration_seconds: 135
  words_per_minute: 145
```

The word limits are derived from the configured duration bounds and speaking-rate estimate. TTS later supplies the authoritative measured duration.

## Generator

The current implementation is Gemini-backed:

```text
story.json
    ↓
Gemini narration writer
    ↓
hook
    ↓
chronological narration segments
    ↓
ending
    ↓
validated script.json
```

The generator uses structured JSON output and validates:

- requested language/writing-system pairing;
- non-empty hook and ending;
- valid scene IDs;
- valid story-event IDs;
- unique segment IDs;
- chronological segment anchors;
- word count and duration range;
- markdown/decorative formatting artifacts;
- stage directions and repeated punctuation;
- obvious exact nine-word subtitle copying.

The subtitle check is intentionally a narrow integrity guard, not a general similarity or legal determination.

## Manifest

The durable checkpoint is:

```text
workspace/narration/<input-name>/script.json
```

It records:

- source story path and input fingerprint;
- language and writing-system choice;
- style;
- duration targets;
- words-per-minute target;
- hook and ending scene references;
- ordered narration segments;
- scene and story-event references;
- computed word count;
- computed estimated duration;
- Gemini model;
- checkpoint name.

Segment timing is provisional. It is a planning anchor for scene matching; real TTS audio timing replaces it later.

## CLI

Generate using the configured language:

```bash
python -m animexe episode script /path/to/episode.mkv
```

Generate English:

```bash
python -m animexe episode script /path/to/episode.mkv \
  --language english \
  --script latin
```

Generate Hinglish:

```bash
python -m animexe episode script /path/to/episode.mkv \
  --language hinglish \
  --script roman
```

The command expects an existing story checkpoint and transcript manifest. The transcript is used only as an integrity signal for obvious exact copying; the story manifest remains the narration source of truth.

## Episode checkpoint

When an episode record is supplied with `--anime-id` and `--episode-number`, a successful script generation advances the durable episode checkpoint to:

```text
current_checkpoint = script
```

and stores the manifest path in `script_manifest`.

## Next stage

The next stage is TTS. It will consume the script segments, generate sentence/segment audio, measure actual duration, and establish the authoritative narration timeline before scene matching.
