# AniMeXe GitHub Actions

AniMeXe will use GitHub Actions as a worker after the local pipeline is stable. The operational design follows the successful patterns already used by YTAutoPilot.

## Modes
- dry-run: validate configuration, state, scheduler decisions, and workspace creation.
- analyze: inspect media, detect scenes, process transcripts, and build story analysis.
- visual-cut: build the semantic edit plan and upload a narration-free visual preview.
- render: run the complete production pipeline and upload artifacts.
- scheduled: run the central scheduler up to the configured daily output limit.

Publishing is excluded from the initial workflow.

## Worker sequence
checkout -> install/check FFmpeg -> setup Python -> restore caches -> load configuration -> load state -> run scheduler -> process selected jobs -> validate -> upload artifacts -> persist state -> fetch origin/main -> rebase -> push state.

## Caching
Cache pip packages, the Python environment where practical, and model files. Cache keys must include dependency or model versions.

## Runner
Baseline: Ubuntu 24.04, Python 3.11, FFmpeg/ffprobe, Noto fonts when needed, CPU-first processing. GPU must not be a hard requirement.

## State persistence
Actions commits only small machine-readable state. Before pushing, fetch main and rebase. Never blindly overwrite newer scheduler state.

## Concurrency
Use one production concurrency group so scheduled workers cannot select the same daily slots at the same time. The scheduler must re-check state before claiming a job.

## Artifacts
Upload job report, episode manifest, story, script, narration manifest, subtitles, timeline, render manifest, and final MP4.

## Secrets
Credentials belong in GitHub Actions secrets. Provider URLs, model names, feature flags, and performance settings belong in configuration or Actions variables. Never commit credentials.

## Scheduling gate
Do not enable production schedules until one local render, one GitHub Actions render, state persistence, checkpoint recovery, and duplicate-job protection have all been verified.

## Current workflows

### `ci.yml`

Runs on pushes to `main`, pull requests targeting `main`, and manual dispatch. It compiles the package and runs the unit-test suite.

### `full-pipeline-smoke.yml`

Manual full-pipeline smoke test. It creates a tiny synthetic episode, runs Gemini semantic story understanding, creates the `edit_plan` checkpoint, generates cut-aware narration, Gemini Flash TTS, constrained scene matching, timeline generation, FFmpeg rendering, checkpoint recovery, and final stream validation. The Gemini response cache is restored/saved around the run.

### `episode-visual-cut.yml`

Manual visual-selection workflow. It analyzes an episode, builds the semantic edit plan, and produces a video-only artifact with no source audio, narration, TTS, BGM, SFX, or subtitles.

Synthetic mode is the CI-safe default. Workspace mode requires the episode file to already be provisioned on the runner.

## First workflow quality gate
Verify workflow success, final MP4, video stream, narration audio, subtitles, muted source audio, plausible duration, readable artifacts, exactly-once state advancement, and checkpoint-based retry recovery.