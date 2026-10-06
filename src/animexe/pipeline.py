from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .analysis import (
    EpisodeAnalysisManifest,
    EpisodeInspector,
    EpisodeStoryManifest,
    GeminiStoryAnalyzer,
    SceneAnalysisManifest,
    SceneIndexer,
    SubtitleTranscriptExtractor,
    TranscriptAnalysisManifest,
)
from .config import AppConfig
from .matching import SceneMatchManifest, SceneMatcher
from .narration import GeminiNarrationScriptGenerator, NarrationScriptManifest
from .paths import ProjectPaths
from .render import FFmpegRenderer, TimelineBuilder, TimelineManifest
from .tts import (
    CommandTTSSynthesizer,
    GeminiTTSSynthesizer,
    SyntheticTTSSynthesizer,
    TTSManifest,
)


class PipelineError(RuntimeError):
    """Raised when the episode production pipeline cannot complete."""


@dataclass(frozen=True)
class PipelineResult:
    input_path: str
    output_path: str
    checkpoints: dict[str, str]
    resumed: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "checkpoints": dict(self.checkpoints),
            "resumed": list(self.resumed),
        }


class EpisodePipeline:
    """Run the complete local-media production pipeline with checkpoint reuse."""

    def __init__(self, paths: ProjectPaths, config: AppConfig) -> None:
        self.paths = paths
        self.config = config

    def run(
        self,
        input_path: Path,
        *,
        anime_id: str | None = None,
        episode_number: int | None = None,
        season: int = 1,
    ) -> PipelineResult:
        source = input_path.expanduser().resolve()
        if not source.is_file():
            raise PipelineError(f"input episode not found: {source}")
        if anime_id is not None and episode_number is None:
            raise PipelineError("episode_number is required when anime_id is provided")
        if episode_number is not None and episode_number < 1:
            raise PipelineError("episode number must be >= 1")
        if season < 1:
            raise PipelineError("season must be >= 1")

        stem = source.stem
        analysis_dir = self.paths.workspace / "analysis" / stem
        narration_dir = self.paths.workspace / "narration" / stem
        analysis_dir.mkdir(parents=True, exist_ok=True)
        narration_dir.mkdir(parents=True, exist_ok=True)

        episode_id = (
            f"{anime_id}-s{season}-e{episode_number}"
            if anime_id and episode_number is not None
            else None
        )
        resumed: list[str] = []
        checkpoints: dict[str, str] = {}

        analysis_path = self.paths.workspace / "analysis" / f"{stem}.analysis.json"
        if analysis_path.exists():
            try:
                analysis = EpisodeAnalysisManifest.read(analysis_path)
                if str(source) != analysis.input_path:
                    raise PipelineError("existing analysis checkpoint belongs to a different input")
                resumed.append("inspected")
            except (OSError, ValueError, TypeError) as exc:
                raise PipelineError(f"invalid analysis checkpoint: {exc}") from exc
        else:
            analysis = EpisodeInspector().inspect(source, episode_id=episode_id)
            analysis.write(analysis_path)
        checkpoints["inspected"] = str(analysis_path)

        scenes_path = analysis_dir / "scenes.json"
        if scenes_path.exists():
            try:
                scenes = SceneAnalysisManifest.read(scenes_path)
                if scenes.input_path != str(source):
                    raise PipelineError("existing scene checkpoint belongs to a different input")
                resumed.append("scenes")
            except (OSError, ValueError, TypeError) as exc:
                raise PipelineError(f"invalid scene checkpoint: {exc}") from exc
        else:
            scenes = SceneIndexer(
                threshold=self.config.episode.scene_threshold,
                min_scene_duration_seconds=self.config.episode.scene_min_duration,
                frame_width=self.config.episode.scene_frame_width,
            ).index(
                source,
                output_dir=analysis_dir,
                episode_manifest=analysis,
                episode_id=episode_id,
                extract_frames=True,
            )
            scenes.write(scenes_path)
        checkpoints["scenes"] = str(scenes_path)

        transcript_path = analysis_dir / "transcript.json"
        source_srt = analysis_dir / "source.srt"
        if transcript_path.exists():
            try:
                transcript = TranscriptAnalysisManifest.read(transcript_path)
                if transcript.input_path != str(source):
                    raise PipelineError("existing transcript checkpoint belongs to a different input")
                resumed.append("transcript")
            except (OSError, ValueError, TypeError) as exc:
                raise PipelineError(f"invalid transcript checkpoint: {exc}") from exc
        else:
            transcript = SubtitleTranscriptExtractor().extract(
                source,
                output_dir=analysis_dir,
                episode_manifest=analysis,
                scene_manifest=scenes,
                episode_id=episode_id,
            )
            transcript.write(transcript_path)
        checkpoints["transcript"] = str(transcript_path)
        if source_srt.exists():
            checkpoints["source_srt"] = str(source_srt)

        story_path = analysis_dir / "story.json"
        if story_path.exists():
            try:
                story = EpisodeStoryManifest.read(story_path)
                if story.input_path != str(source):
                    raise PipelineError("existing story checkpoint belongs to a different input")
                resumed.append("story")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise PipelineError(f"invalid story checkpoint: {exc}") from exc
        else:
            if self.config.llm.provider.strip().lower() != "gemini":
                raise PipelineError(
                    f"unsupported story provider: {self.config.llm.provider}"
                )
            story = GeminiStoryAnalyzer(
                model=self.config.llm.model,
                api_key_env=self.config.llm.api_key_env,
                temperature=self.config.llm.temperature,
                thinking_level=self.config.llm.thinking_level,
                max_output_tokens=self.config.llm.max_output_tokens,
                max_frames=self.config.llm.max_frames,
            ).analyze(
                transcript,
                scenes,
                scene_manifest_dir=analysis_dir,
                source_transcript=str(transcript_path),
                source_scenes=str(scenes_path),
            )
            story.write(story_path)
        checkpoints["story"] = str(story_path)

        script_path = narration_dir / "script.json"
        if script_path.exists():
            try:
                script = NarrationScriptManifest.read(script_path)
                if script.input_path != str(source):
                    raise PipelineError("existing script checkpoint belongs to a different input")
                resumed.append("script")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise PipelineError(f"invalid script checkpoint: {exc}") from exc
        else:
            script = GeminiNarrationScriptGenerator(
                model=self.config.llm.model,
                api_key_env=self.config.llm.api_key_env,
                temperature=self.config.llm.temperature,
                thinking_level=self.config.llm.thinking_level,
                max_output_tokens=self.config.llm.max_output_tokens,
                target_duration_seconds=self.config.narration.target_duration_seconds,
                min_duration_seconds=self.config.narration.min_duration_seconds,
                max_duration_seconds=self.config.narration.max_duration_seconds,
                words_per_minute=self.config.narration.words_per_minute,
            ).generate(
                story,
                transcript=transcript,
                language=self.config.narration.language,
                script=self.config.narration.script,
                style=self.config.narration.style,
                source_story=str(story_path),
            )
            script.write(script_path)
        checkpoints["script"] = str(script_path)

        tts_dir = narration_dir / "audio"
        tts_path = narration_dir / "tts.json"
        if tts_path.exists():
            try:
                tts = TTSManifest.read(tts_path)
                if tts.input_path != str(source):
                    raise PipelineError("existing TTS checkpoint belongs to a different input")
                resumed.append("tts")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise PipelineError(f"invalid TTS checkpoint: {exc}") from exc
        else:
            tts_provider = self.config.tts.provider
            if tts_provider == "synthetic":
                synthesizer = SyntheticTTSSynthesizer(
                    words_per_minute=self.config.narration.words_per_minute
                )
            elif tts_provider == "command":
                synthesizer = CommandTTSSynthesizer(
                    self.config.tts.command,
                    voice=self.config.tts.voice,
                    timeout_seconds=self.config.tts.timeout_seconds,
                )
            elif tts_provider == "gemini":
                synthesizer = GeminiTTSSynthesizer(
                    model=self.config.tts.model,
                    api_key_env=self.config.tts.api_key_env,
                    voice=self.config.tts.voice or "Kore",
                    style=self.config.tts.style,
                )
            else:
                raise PipelineError(f"unsupported TTS provider: {tts_provider}")
            tts = synthesizer.synthesize(
                script,
                output_dir=tts_dir,
                source_script=str(script_path),
            )
            tts.write(tts_path)
        checkpoints["tts"] = str(tts_path)

        matching_path = narration_dir / "matching.json"
        if matching_path.exists():
            matching = SceneMatchManifest.read(matching_path)
            resumed.append("matching")
        else:
            matching = SceneMatcher(
                max_clip_duration=self.config.video.max_clip_duration
            ).match(
                scenes,
                tts,
                source_scenes=str(scenes_path),
                source_tts=str(tts_path),
            )
            matching.write(matching_path)
        checkpoints["matching"] = str(matching_path)

        timeline_path = narration_dir / "timeline.json"
        if timeline_path.exists():
            timeline = TimelineManifest.read(timeline_path)
            resumed.append("timeline")
        else:
            timeline = TimelineBuilder().build(
                matching,
                tts,
                source_matching=str(matching_path),
                source_tts=str(tts_path),
            )
            timeline.write(timeline_path)
        checkpoints["timeline"] = str(timeline_path)

        output_path = self.paths.workspace / "output" / f"{stem}.mp4"
        if output_path.exists() and output_path.stat().st_size > 0:
            resumed.append("render")
        else:
            FFmpegRenderer(
                width=self.config.video.width,
                height=self.config.video.height,
                fps=self.config.video.fps,
            ).render(
                timeline,
                source_video=source,
                narration_dir=tts_dir,
                output_path=output_path,
                subtitles=self.config.subtitles.enabled and self.config.subtitles.burn_in,
            )
        checkpoints["render"] = str(output_path)

        return PipelineResult(
            input_path=str(source),
            output_path=str(output_path),
            checkpoints=checkpoints,
            resumed=tuple(resumed),
        )
