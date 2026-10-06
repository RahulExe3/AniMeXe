# Visual Editing and Episode Cut

AniMeXe does not generate narration directly from a 23-minute episode and hope the final edit happens to match it.

The production contract is:

```text
actual episode
    ↓
technical inspection
    ↓
scene index + transcript
    ↓
semantic story understanding
    ↓
visual edit plan
    ↓
narration written for that exact visual cut
    ↓
TTS with measured timing
    ↓
matching constrained to the same cut
    ↓
timeline
    ↓
final narration/BGM/subtitle render
```

The **visual edit plan is the bridge between understanding and narration**. It defines which parts of the real episode will be shown. Narration must stay inside that boundary.

## Why the edit plan exists

A story summary is not an edit.

A 23-minute episode can contain many events that do not belong in a two-minute explanation. The planner therefore converts semantic story events into a smaller chronological set of actual source-video intervals.

The planner favors:

- high-importance events;
- reveals, turns, conflict, action, climax, and ending events when the story model identifies them;
- the opening context;
- the episode ending/payoff;
- chronological continuity.

It also respects:

- target duration;
- minimum/maximum duration;
- maximum clip duration;
- scene boundaries;
- source fingerprint.

The result is a durable `edit_plan.json` checkpoint.

## Edit-plan manifest

The checkpoint is stored at:

```text
workspace/analysis/<episode-name>/edit_plan.json
```

Each planned clip contains:

```json
{
  "clip_id": "clip_001",
  "event_id": "event_0012",
  "scene_id": "scene_0042",
  "source_start_seconds": 312.4,
  "source_end_seconds": 318.4,
  "duration_seconds": 6.0,
  "importance": 0.91,
  "reason": "reveal"
}
```

The manifest also stores the episode fingerprint, source story/scenes, duration policy, selected event IDs, total planned duration, and schema version.

## Narration contract

Once an edit plan exists, the narration generator receives:

1. the semantic story;
2. the selected event IDs;
3. the exact selected scene IDs;
4. the exact source intervals and durations.

The narration prompt explicitly treats the visual cut as a hard boundary. It must not narrate events that are outside the selected cut.

The narration manifest records the edit-plan source so a script can be traced back to the visual decision that produced it.

## Matching contract

After TTS, scene matching is still required because measured voice audio duration is authoritative.

However, matching is no longer allowed to wander across the whole episode. When an edit plan is present, candidate scenes are restricted to the plan and clip windows are restricted to the plan's source intervals.

That means the same evidence controls both:

```text
what we show → what we say
```

## Narration-free visual cut

AniMeXe provides a separate renderer for inspecting the selected visuals before voiceover:

```bash
python -m animexe episode visual-cut /path/to/episode.mkv
```

The command loads or creates `edit_plan.json`, then renders only the selected clips.

Properties of this artifact:

- video only;
- no original episode audio;
- no narration;
- no TTS;
- no BGM;
- no SFX;
- no subtitles;
- only the selected visual clips concatenated in chronological order;
- FFmpeg output validated with ffprobe.

This artifact is intentionally useful as a review/debugging checkpoint. It lets a human verify that the selected footage actually explains the episode before spending time on voice generation and final rendering.

## GitHub Actions workflow

Run:

```text
.github/workflows/episode-visual-cut.yml
```

The workflow is `workflow_dispatch` and produces an artifact named:

```text
animexe-episode-visual-cut
```

The artifact contains the video-only cut plus compact analysis artifacts such as the edit plan, story, scenes, and workflow diagnostics.

### Synthetic mode

Synthetic mode is the default CI-safe demonstration. It creates a small local episode with embedded subtitles, performs real analysis, runs Gemini story understanding, builds an edit plan, renders the video-only cut, validates that the output contains only a video stream, and uploads the artifact.

### Workspace mode

Workspace mode expects an episode file to already exist at the supplied path on the runner. GitHub Actions does not provide a general local-file upload control, so a real episode must be provisioned to the runner by the surrounding workflow or storage integration before this workflow starts.

The workflow must never silently substitute metadata for missing media. If the episode file is missing or unreadable, the run fails.

## Relationship to the full pipeline

The edit plan is not a second unrelated editing system.

The normal production pipeline now uses the same planning stage:

```text
story → edit_plan → script → TTS → matching → timeline → render
```

The standalone visual-cut workflow simply stops after the visual cut so the selected footage can be inspected independently.

This keeps the final narration and the final video grounded in the same selected scenes.

## Safety and source boundaries

The editor only processes the episode file supplied to AniMeXe through its local/authorized media boundary. It does not implement stream bypass, DRM decryption, proxy evasion, or copyright-detection evasion.

Creative transforms are presentation features. They are not a mechanism to bypass platform protections.

## Checkpoint recovery

The full production checkpoint chain is now:

```text
input
  → inspected
  → scenes
  → transcript
  → story
  → edit_plan
  → script
  → tts
  → matching
  → timeline
  → render
```

Each checkpoint is tied to the source fingerprint. A changed episode must not reuse an old edit plan.
