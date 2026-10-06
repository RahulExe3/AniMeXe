# Narration Script

AniMeXe separates semantic story understanding, visual editing, narration language, and voice generation.

The important production rule is:

```text
story understanding
      ↓
visual edit plan
      ↓
narration for the exact selected visuals
      ↓
TTS
```

The script is therefore not a generic narration of the whole 23-minute episode. It describes the specific clips that the edit plan says will appear in the final explanation video.

## Supported languages

AniMeXe currently supports two narration modes:

| Language | Writing system | Intended style |
|---|---|---|
| `english` | `latin` | Natural spoken English |
| `hinglish` | `roman` | Natural Hindi-English speech written in Roman script |

Hinglish is deliberately controlled rather than randomly mixing languages. Hindi remains the conversational base, while English words are used where they sound natural for the speaker.

The same semantic `story.json` can generate either language. Story analysis is therefore performed once.

## Duration target

The default visual/narration target is approximately two minutes. The edit planner and narration generator share these duration bounds so the planned visual material is sized for the explanation voiceover:

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
edit_plan.json
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

The edit plan is the visual contract. It supplies the selected event IDs, scene IDs, source intervals, and durations that the narration is allowed to describe.

The generator uses structured JSON output and validates:

- requested language/writing-system pairing;
- non-empty hook and ending;
- valid scene IDs from the selected edit plan;
- valid story-event IDs from the selected edit plan;
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
- source edit-plan path;
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

The command expects an existing story checkpoint and transcript manifest. The transcript is used only as an integrity signal for obvious exact copying. The semantic story remains the factual source, while the edit plan is the hard boundary for what may be narrated.

## Episode checkpoint

When an episode record is supplied with `--anime-id` and `--episode-number`, a successful script generation advances the durable episode checkpoint to:

```text
current_checkpoint = script
```

and stores the manifest path in `script_manifest`.

## Next stage

The next stage is TTS. It consumes the selected script segments, generates sentence/segment audio, measures actual duration, and establishes the authoritative narration timeline.

Scene matching then remains constrained to the same edit plan, so TTS timing can adjust clip durations without reopening the whole 23-minute episode as a candidate source.
