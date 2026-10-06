from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import (
    EpisodeAnalysisManifest,
    EpisodeInspector,
    SceneAnalysisManifest,
    InspectionError,
    SceneDetectionError,
    SceneIndexer,
    SubtitleTranscriptExtractor,
    TranscriptAnalysisManifest,
    TranscriptError,
    EpisodeStoryManifest,
    ExtractiveStoryAnalyzer,
    StoryAnalysisError,
    GeminiStoryAnalyzer,
    GeminiStoryError,
)
from .config import load_config
from .logging import configure_logging
from .metadata import MetadataLibrary, MetadataService
from .models import AnimeRecord, EpisodeRecord
from .narration import (
    GeminiNarrationScriptGenerator,
    NarrationScriptError,
    NarrationScriptManifest,
)
from .tts import CommandTTSSynthesizer, GeminiTTSSynthesizer, SyntheticTTSSynthesizer, TTSError
from .matching import MatchError, SceneMatchManifest, SceneMatcher
from .render import FFmpegRenderer, RenderError, TimelineBuilder, TimelineManifest
from .paths import ProjectPaths
from .providers import ProviderBroker, build_registry
from .scheduler import Scheduler
from .state import StateStore


def _project_paths() -> ProjectPaths:
    paths = ProjectPaths.discover()
    paths.ensure()
    return paths


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="animexe",
        description="AniMeXe anime episode automation engine",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="logging level (default: INFO)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the canonical AniMeXe directories and state files")
    sub.add_parser("status", help="show current persisted state")

    anime = sub.add_parser("anime", help="manage anime records")
    anime_sub = anime.add_subparsers(dest="anime_command", required=True)
    anime_sub.add_parser("list", help="list anime records")

    add_anime = anime_sub.add_parser("add", help="add one anime record")
    add_anime.add_argument("id")
    add_anime.add_argument("title")
    add_anime.add_argument("--season", type=int, default=1)
    add_anime.add_argument("--priority", type=int, default=0)

    episode = sub.add_parser("episode", help="inspect episode records")
    episode_sub = episode.add_subparsers(dest="episode_command", required=True)
    episode_list = episode_sub.add_parser("list", help="list episodes")
    episode_list.add_argument("--anime-id")

    episode_inspect = episode_sub.add_parser(
        "inspect",
        help="run ffprobe inspection and write an analysis manifest",
    )
    episode_inspect.add_argument("input_path", type=Path)
    episode_inspect.add_argument("--anime-id")
    episode_inspect.add_argument("--episode-number", type=int)
    episode_inspect.add_argument("--season", type=int, default=1)
    episode_inspect.add_argument("--output", type=Path)
    episode_inspect.add_argument(
        "--no-hash-input",
        action="store_true",
        help="skip the full SHA-256 input fingerprint",
    )

    episode_scenes = episode_sub.add_parser(
        "scenes",
        help="detect scenes and extract representative frames",
    )
    episode_scenes.add_argument("input_path", type=Path)
    episode_scenes.add_argument("--analysis-manifest", type=Path)
    episode_scenes.add_argument("--anime-id")
    episode_scenes.add_argument("--episode-number", type=int)
    episode_scenes.add_argument("--season", type=int, default=1)
    episode_scenes.add_argument("--output", type=Path)
    episode_scenes.add_argument(
        "--no-frames",
        action="store_true",
        help="build the scene index without extracting representative frames",
    )

    episode_transcript = episode_sub.add_parser(
        "transcript",
        help="extract embedded subtitles and align them to scenes",
    )
    episode_transcript.add_argument("input_path", type=Path)
    episode_transcript.add_argument("--analysis-manifest", type=Path)
    episode_transcript.add_argument("--scene-manifest", type=Path)
    episode_transcript.add_argument("--anime-id")
    episode_transcript.add_argument("--episode-number", type=int)
    episode_transcript.add_argument("--season", type=int, default=1)
    episode_transcript.add_argument("--output", type=Path)

    episode_story = episode_sub.add_parser(
        "story",
        help="assemble structured story evidence from transcript and scenes",
    )
    episode_story.add_argument("input_path", type=Path)
    episode_story.add_argument("--transcript-manifest", type=Path)
    episode_story.add_argument("--scene-manifest", type=Path)
    episode_story.add_argument("--analysis-manifest", type=Path)
    episode_story.add_argument("--anime-id")
    episode_story.add_argument("--episode-number", type=int)
    episode_story.add_argument("--season", type=int, default=1)
    episode_story.add_argument("--output", type=Path)
    episode_story.add_argument(
        "--mode",
        choices=("extractive", "gemini"),
        default="extractive",
        help="story analysis backend (default: extractive)",
    )

    episode_script = episode_sub.add_parser(
        "script",
        help="generate an original narration script from story understanding",
    )
    episode_script.add_argument("input_path", type=Path)
    episode_script.add_argument("--story-manifest", type=Path)
    episode_script.add_argument("--transcript-manifest", type=Path)
    episode_script.add_argument("--anime-id")
    episode_script.add_argument("--episode-number", type=int)
    episode_script.add_argument("--season", type=int, default=1)
    episode_script.add_argument("--output", type=Path)
    episode_script.add_argument(
        "--provider",
        choices=("gemini",),
        default=None,
        help="narration-script provider (default: configured llm provider)",
    )
    episode_script.add_argument(
        "--language",
        choices=("english", "hinglish"),
        default=None,
        help="narration language (default: configured narration.language)",
    )
    episode_script.add_argument(
        "--script",
        choices=("latin", "roman"),
        default=None,
        help="writing system: latin for English, roman for Hinglish",
    )

    episode_tts = episode_sub.add_parser(
        "tts",
        help="synthesize narration audio and write the TTS checkpoint",
    )
    episode_tts.add_argument("input_path", type=Path)
    episode_tts.add_argument("--script-manifest", type=Path)
    episode_tts.add_argument("--anime-id")
    episode_tts.add_argument("--episode-number", type=int)
    episode_tts.add_argument("--season", type=int, default=1)
    episode_tts.add_argument("--output", type=Path)
    episode_tts.add_argument(
        "--provider",
        choices=("synthetic", "command", "gemini"),
        default=None,
        help="TTS backend (default: configured tts.provider)",
    )

    episode_match = episode_sub.add_parser(
        "match",
        help="match measured narration audio to source scenes",
    )
    episode_match.add_argument("input_path", type=Path)
    episode_match.add_argument("--scene-manifest", type=Path)
    episode_match.add_argument("--tts-manifest", type=Path)
    episode_match.add_argument("--anime-id")
    episode_match.add_argument("--episode-number", type=int)
    episode_match.add_argument("--season", type=int, default=1)
    episode_match.add_argument("--output", type=Path)
    episode_match.add_argument("--max-clip-duration", type=float, default=None)

    episode_timeline = episode_sub.add_parser(
        "timeline",
        help="build the declarative render timeline",
    )
    episode_timeline.add_argument("input_path", type=Path)
    episode_timeline.add_argument("--matching-manifest", type=Path)
    episode_timeline.add_argument("--tts-manifest", type=Path)
    episode_timeline.add_argument("--anime-id")
    episode_timeline.add_argument("--episode-number", type=int)
    episode_timeline.add_argument("--season", type=int, default=1)
    episode_timeline.add_argument("--output", type=Path)

    episode_render = episode_sub.add_parser(
        "render",
        help="render the final MP4 from the declarative timeline",
    )
    episode_render.add_argument("input_path", type=Path)
    episode_render.add_argument("--timeline-manifest", type=Path)
    episode_render.add_argument("--tts-dir", type=Path)
    episode_render.add_argument("--anime-id")
    episode_render.add_argument("--episode-number", type=int)
    episode_render.add_argument("--season", type=int, default=1)
    episode_render.add_argument("--output", type=Path)
    episode_render.add_argument(
        "--no-subtitles",
        action="store_true",
        help="do not burn narration subtitles into the video",
    )

    providers = sub.add_parser("provider", help="inspect configured episode providers")
    provider_sub = providers.add_subparsers(dest="provider_command", required=True)
    provider_sub.add_parser("status", help="check health of every configured provider")
    provider_check = provider_sub.add_parser("check", help="probe one episode across configured providers")
    provider_check.add_argument("anime_id", help="provider-independent anime id, e.g. anilist:21")
    provider_check.add_argument("--episode-number", type=int, required=True)
    provider_check.add_argument("--language", choices=("sub", "dub"), default="sub")

    sub.add_parser("plan", help="show the scheduler's next job plan")

    metadata = sub.add_parser("metadata", help="query normalized anime metadata")
    metadata_sub = metadata.add_subparsers(dest="metadata_command", required=True)

    metadata_search = metadata_sub.add_parser("search", help="search anime metadata")
    metadata_search.add_argument("query")
    metadata_search.add_argument("--limit", type=int, default=None)

    metadata_get = metadata_sub.add_parser("get", help="fetch one anime by metadata provider id")
    metadata_get.add_argument("provider", choices=("anilist", "jikan"))
    metadata_get.add_argument("id")

    metadata_sync = metadata_sub.add_parser("sync", help="fetch metadata and upsert it into the anime library")
    metadata_sync.add_argument("provider", choices=("anilist", "jikan"))
    metadata_sync.add_argument("id")

    return parser


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)

    paths = _project_paths()
    store = StateStore(paths.data)

    if args.command == "init":
        store.ensure()
        print(f"Initialized AniMeXe at {paths.root}")
        return

    if args.command == "status":
        anime = store.list_anime()
        episodes = store.list_episodes()
        scheduler = store.load_scheduler()
        _print_json(
            {
                "root": str(paths.root),
                "anime": len(anime),
                "episodes": len(episodes),
                "active_anime": sum(item.active for item in anime),
                "successful_outputs_today": scheduler.successful_outputs_today,
                "daily_output_limit": scheduler.daily_output_limit,
                "strategy": scheduler.strategy,
            }
        )
        return

    if args.command == "anime":
        if args.anime_command == "list":
            _print_json([item.__dict__ for item in store.list_anime()])
            return

        if args.anime_command == "add":
            record = AnimeRecord(
                id=args.id,
                title=args.title,
                season=args.season,
                priority=args.priority,
                status="DISCOVERED",
                release_state="NOT_YET_RELEASED",
            )
            store.save_anime(record)
            print(f"Added anime: {record.title} (S{record.season})")
            return

    if args.command == "episode":
        if args.episode_command == "list":
            _print_json(
                [item.__dict__ for item in store.list_episodes(args.anime_id)]
            )
            return

        if args.episode_command == "inspect":
            if (args.anime_id is None) != (args.episode_number is None):
                parser.error("--anime-id and --episode-number must be supplied together")
            if args.season < 1:
                parser.error("--season must be >= 1")
            if args.episode_number is not None and args.episode_number < 1:
                parser.error("--episode-number must be >= 1")

            episode_id = None
            if args.anime_id:
                assert args.episode_number is not None
                episode_id = (
                    f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                )

            inspector = EpisodeInspector()
            try:
                manifest = inspector.inspect(
                    args.input_path,
                    episode_id=episode_id,
                    hash_input=not args.no_hash_input,
                )
            except InspectionError as exc:
                parser.error(str(exc))

            output_path = args.output or (
                paths.workspace
                / "analysis"
                / f"{args.input_path.stem}.analysis.json"
            )
            manifest.write(output_path)

            if args.anime_id:
                assert args.episode_number is not None
                existing = {
                    item.id: item
                    for item in store.list_episodes(args.anime_id)
                }.get(episode_id)
                record = existing or EpisodeRecord(
                    id=episode_id,
                    anime_id=args.anime_id,
                    episode_number=args.episode_number,
                )
                record.status = "PROCESSING"
                record.current_checkpoint = "inspected"
                record.failure_reason = None
                record.provider = "local"
                record.source_reference = str(
                    args.input_path.expanduser().resolve()
                )
                record.analysis_manifest = str(output_path)
                store.save_episode(record)

            _print_json(manifest.to_dict() | {"manifest_path": str(output_path)})
            return

    if args.command == "episode":
        if args.episode_command == "scenes":
            if (args.anime_id is None) != (args.episode_number is None):
                parser.error("--anime-id and --episode-number must be supplied together")
            if args.season < 1:
                parser.error("--season must be >= 1")
            if args.episode_number is not None and args.episode_number < 1:
                parser.error("--episode-number must be >= 1")

            config_path = paths.config / "config.yml"
            if not config_path.exists():
                config_path = paths.config / "config.example.yml"
            app_config = load_config(config_path)
            if not app_config.episode.scene_detection:
                parser.error("episode.scene_detection is disabled in configuration")

            episode_manifest_path = args.analysis_manifest
            if episode_manifest_path is None:
                episode_manifest_path = (
                    paths.workspace
                    / "analysis"
                    / f"{args.input_path.stem}.analysis.json"
                )

            if episode_manifest_path.exists():
                try:
                    episode_manifest = EpisodeAnalysisManifest.read(episode_manifest_path)
                except (OSError, ValueError, TypeError) as exc:
                    parser.error(f"could not read analysis manifest: {exc}")
            else:
                inspector = EpisodeInspector()
                try:
                    episode_id = None
                    if args.anime_id:
                        assert args.episode_number is not None
                        episode_id = f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                    episode_manifest = inspector.inspect(
                        args.input_path,
                        episode_id=episode_id,
                    )
                    episode_manifest.write(episode_manifest_path)
                except InspectionError as exc:
                    parser.error(str(exc))

            output_dir = (
                args.output.parent
                if args.output
                else paths.workspace / "analysis" / args.input_path.stem
            )
            scene_manifest_path = args.output or (output_dir / "scenes.json")

            indexer = SceneIndexer(
                threshold=app_config.episode.scene_threshold,
                min_scene_duration_seconds=app_config.episode.scene_min_duration,
                frame_width=app_config.episode.scene_frame_width,
            )
            try:
                scene_manifest = indexer.index(
                    args.input_path,
                    output_dir=output_dir,
                    episode_manifest=episode_manifest,
                    episode_id=episode_manifest.episode_id,
                    extract_frames=not args.no_frames,
                )
            except SceneDetectionError as exc:
                parser.error(str(exc))

            scene_manifest.write(scene_manifest_path)

            if args.anime_id:
                assert args.episode_number is not None
                episode_id = f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                existing = {
                    item.id: item
                    for item in store.list_episodes(args.anime_id)
                }.get(episode_id)
                record = existing or EpisodeRecord(
                    id=episode_id,
                    anime_id=args.anime_id,
                    episode_number=args.episode_number,
                )
                record.status = "PROCESSING"
                record.current_checkpoint = "scenes"
                record.failure_reason = None
                record.provider = "local"
                record.source_reference = str(
                    args.input_path.expanduser().resolve()
                )
                record.analysis_manifest = str(episode_manifest_path)
                record.scene_manifest = str(scene_manifest_path)
                store.save_episode(record)

            _print_json(
                scene_manifest.to_dict()
                | {
                    "analysis_manifest_path": str(episode_manifest_path),
                    "scene_manifest_path": str(scene_manifest_path),
                }
            )
            return

    if args.command == "episode":
        if args.episode_command == "transcript":
            if (args.anime_id is None) != (args.episode_number is None):
                parser.error("--anime-id and --episode-number must be supplied together")
            if args.season < 1:
                parser.error("--season must be >= 1")
            if args.episode_number is not None and args.episode_number < 1:
                parser.error("--episode-number must be >= 1")

            episode_manifest_path = args.analysis_manifest or (
                paths.workspace
                / "analysis"
                / f"{args.input_path.stem}.analysis.json"
            )
            scene_manifest_path = args.scene_manifest or (
                paths.workspace
                / "analysis"
                / args.input_path.stem
                / "scenes.json"
            )

            try:
                episode_manifest = EpisodeAnalysisManifest.read(episode_manifest_path)
            except (OSError, ValueError, TypeError) as exc:
                parser.error(f"could not read analysis manifest: {exc}")

            try:
                from .analysis.scenes import SceneAnalysisManifest
                scene_manifest = SceneAnalysisManifest.read(scene_manifest_path)
            except (OSError, ValueError, TypeError) as exc:
                parser.error(f"could not read scene manifest: {exc}")

            output_dir = (
                args.output.parent
                if args.output
                else paths.workspace / "analysis" / args.input_path.stem
            )
            transcript_manifest_path = args.output or (output_dir / "transcript.json")

            extractor = SubtitleTranscriptExtractor()
            try:
                transcript_manifest = extractor.extract(
                    args.input_path,
                    output_dir=output_dir,
                    episode_manifest=episode_manifest,
                    scene_manifest=scene_manifest,
                    episode_id=episode_manifest.episode_id,
                )
            except TranscriptError as exc:
                parser.error(str(exc))

            transcript_manifest.write(transcript_manifest_path)

            if args.anime_id:
                assert args.episode_number is not None
                episode_id = f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                existing = {
                    item.id: item
                    for item in store.list_episodes(args.anime_id)
                }.get(episode_id)
                record = existing or EpisodeRecord(
                    id=episode_id,
                    anime_id=args.anime_id,
                    episode_number=args.episode_number,
                )
                record.status = "PROCESSING"
                record.current_checkpoint = "transcript"
                record.failure_reason = None
                record.provider = "local"
                record.source_reference = str(
                    args.input_path.expanduser().resolve()
                )
                record.analysis_manifest = str(episode_manifest_path)
                record.scene_manifest = str(scene_manifest_path)
                record.transcript_manifest = str(transcript_manifest_path)
                store.save_episode(record)

            _print_json(
                transcript_manifest.to_dict()
                | {
                    "analysis_manifest_path": str(episode_manifest_path),
                    "scene_manifest_path": str(scene_manifest_path),
                    "transcript_manifest_path": str(transcript_manifest_path),
                }
            )
            return

    if args.command == "episode":
        if args.episode_command == "story":
            if (args.anime_id is None) != (args.episode_number is None):
                parser.error("--anime-id and --episode-number must be supplied together")
            if args.season < 1:
                parser.error("--season must be >= 1")
            if args.episode_number is not None and args.episode_number < 1:
                parser.error("--episode-number must be >= 1")

            transcript_path = args.transcript_manifest or (
                paths.workspace
                / "analysis"
                / args.input_path.stem
                / "transcript.json"
            )
            scene_path = args.scene_manifest or (
                paths.workspace
                / "analysis"
                / args.input_path.stem
                / "scenes.json"
            )
            analysis_path = args.analysis_manifest or (
                paths.workspace
                / "analysis"
                / f"{args.input_path.stem}.analysis.json"
            )

            try:
                transcript_manifest = TranscriptAnalysisManifest.read(transcript_path)
                scene_manifest = SceneAnalysisManifest.read(scene_path)
                EpisodeAnalysisManifest.read(analysis_path)
            except (OSError, ValueError, TypeError) as exc:
                parser.error(f"could not read analysis manifests: {exc}")

            output_path = args.output or (
                paths.workspace
                / "analysis"
                / args.input_path.stem
                / "story.json"
            )

            config_path = paths.config / "config.yml"
            if not config_path.exists():
                config_path = paths.config / "config.example.yml"
            app_config = load_config(config_path)

            try:
                if args.mode == "gemini":
                    if app_config.llm.provider.lower() != "gemini":
                        parser.error(
                            f"llm.provider is configured as {app_config.llm.provider!r}; "
                            "set it to gemini before using --mode gemini"
                        )
                    story_manifest = GeminiStoryAnalyzer(
                        model=app_config.llm.model,
                        api_key_env=app_config.llm.api_key_env,
                        temperature=app_config.llm.temperature,
                        max_output_tokens=app_config.llm.max_output_tokens,
                        max_frames=app_config.llm.max_frames,
                    ).analyze(
                        transcript_manifest,
                        scene_manifest,
                        scene_manifest_dir=scene_path.parent,
                        source_transcript=str(transcript_path),
                        source_scenes=str(scene_path),
                    )
                else:
                    story_manifest = ExtractiveStoryAnalyzer().analyze(
                        transcript_manifest,
                        scene_manifest,
                        source_transcript=str(transcript_path),
                        source_scenes=str(scene_path),
                    )
            except (StoryAnalysisError, GeminiStoryError) as exc:
                parser.error(str(exc))

            story_manifest.write(output_path)

            if args.anime_id:
                assert args.episode_number is not None
                episode_id = f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                existing = {
                    item.id: item
                    for item in store.list_episodes(args.anime_id)
                }.get(episode_id)
                record = existing or EpisodeRecord(
                    id=episode_id,
                    anime_id=args.anime_id,
                    episode_number=args.episode_number,
                )
                record.status = "PROCESSING"
                record.current_checkpoint = "story"
                record.failure_reason = None
                record.provider = "local"
                record.source_reference = str(
                    args.input_path.expanduser().resolve()
                )
                record.analysis_manifest = str(analysis_path)
                record.scene_manifest = str(scene_path)
                record.transcript_manifest = str(transcript_path)
                record.story_manifest = str(output_path)
                store.save_episode(record)

            _print_json(
                story_manifest.to_dict()
                | {
                    "analysis_manifest_path": str(analysis_path),
                    "scene_manifest_path": str(scene_path),
                    "transcript_manifest_path": str(transcript_path),
                    "story_manifest_path": str(output_path),
                }
            )
            return

    if args.command == "episode":
        if args.episode_command == "script":
            if (args.anime_id is None) != (args.episode_number is None):
                parser.error("--anime-id and --episode-number must be supplied together")
            if args.season < 1:
                parser.error("--season must be >= 1")
            if args.episode_number is not None and args.episode_number < 1:
                parser.error("--episode-number must be >= 1")

            story_path = args.story_manifest or (
                paths.workspace
                / "analysis"
                / args.input_path.stem
                / "story.json"
            )
            transcript_path = args.transcript_manifest or (
                paths.workspace
                / "analysis"
                / args.input_path.stem
                / "transcript.json"
            )

            try:
                story_manifest = EpisodeStoryManifest.read(story_path)
                transcript_manifest = TranscriptAnalysisManifest.read(transcript_path)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                parser.error(f"could not read story/transcript manifests: {exc}")

            config_path = paths.config / "config.yml"
            if not config_path.exists():
                config_path = paths.config / "config.example.yml"
            app_config = load_config(config_path)

            provider = (args.provider or app_config.llm.provider).strip().lower()
            if provider != "gemini":
                parser.error(
                    f"narration script provider {provider!r} is not implemented; "
                    "set llm.provider to gemini"
                )

            language = args.language or app_config.narration.language
            script_format = args.script or app_config.narration.script
            output_path = args.output or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "script.json"
            )

            try:
                generator = GeminiNarrationScriptGenerator(
                    model=app_config.llm.model,
                    api_key_env=app_config.llm.api_key_env,
                    temperature=app_config.llm.temperature,
                    max_output_tokens=app_config.llm.max_output_tokens,
                    target_duration_seconds=app_config.narration.target_duration_seconds,
                    min_duration_seconds=app_config.narration.min_duration_seconds,
                    max_duration_seconds=app_config.narration.max_duration_seconds,
                    words_per_minute=app_config.narration.words_per_minute,
                )
                script_manifest = generator.generate(
                    story_manifest,
                    transcript=transcript_manifest,
                    language=language,
                    script=script_format,
                    style=app_config.narration.style,
                    source_story=str(story_path),
                )
            except NarrationScriptError as exc:
                parser.error(str(exc))

            script_manifest.write(output_path)

            if args.anime_id:
                assert args.episode_number is not None
                episode_id = f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                existing = {
                    item.id: item
                    for item in store.list_episodes(args.anime_id)
                }.get(episode_id)
                record = existing or EpisodeRecord(
                    id=episode_id,
                    anime_id=args.anime_id,
                    episode_number=args.episode_number,
                )
                record.status = "PROCESSING"
                record.current_checkpoint = "script"
                record.failure_reason = None
                record.provider = "local"
                record.source_reference = str(
                    args.input_path.expanduser().resolve()
                )
                record.analysis_manifest = str(
                    paths.workspace
                    / "analysis"
                    / f"{args.input_path.stem}.analysis.json"
                )
                record.scene_manifest = str(
                    paths.workspace
                    / "analysis"
                    / args.input_path.stem
                    / "scenes.json"
                )
                record.transcript_manifest = str(transcript_path)
                record.story_manifest = str(story_path)
                record.script_manifest = str(output_path)
                store.save_episode(record)

            _print_json(
                script_manifest.to_dict()
                | {
                    "story_manifest_path": str(story_path),
                    "transcript_manifest_path": str(transcript_path),
                    "script_manifest_path": str(output_path),
                }
            )
            return

    if args.command == "episode":
        if args.episode_command == "tts":
            if (args.anime_id is None) != (args.episode_number is None):
                parser.error("--anime-id and --episode-number must be supplied together")
            if args.season < 1:
                parser.error("--season must be >= 1")
            if args.episode_number is not None and args.episode_number < 1:
                parser.error("--episode-number must be >= 1")

            script_path = args.script_manifest or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "script.json"
            )
            try:
                script_manifest = NarrationScriptManifest.read(script_path)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                parser.error(f"could not read narration script manifest: {exc}")

            config_path = paths.config / "config.yml"
            if not config_path.exists():
                config_path = paths.config / "config.example.yml"
            app_config = load_config(config_path)

            provider = (args.provider or app_config.tts.provider).strip().lower()
            output_dir = (
                args.output.parent
                if args.output
                else paths.workspace / "narration" / args.input_path.stem / "audio"
            )
            output_manifest = args.output or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "tts.json"
            )

            try:
                if provider == "synthetic":
                    synthesizer = SyntheticTTSSynthesizer(
                        words_per_minute=app_config.narration.words_per_minute,
                    )
                elif provider == "gemini":
                    synthesizer = GeminiTTSSynthesizer(
                        model=app_config.tts.model,
                        api_key_env=app_config.tts.api_key_env,
                        voice=app_config.tts.voice or "Kore",
                        style=app_config.tts.style,
                    )
                else:
                    synthesizer = CommandTTSSynthesizer(
                        tuple(app_config.tts.command),
                        voice=app_config.tts.voice,
                        timeout_seconds=app_config.tts.timeout_seconds,
                    )
                tts_manifest = synthesizer.synthesize(
                    script_manifest,
                    output_dir=output_dir,
                    source_script=str(script_path),
                )
            except TTSError as exc:
                parser.error(str(exc))

            tts_manifest.write(output_manifest)

            if args.anime_id:
                assert args.episode_number is not None
                episode_id = f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                existing = {
                    item.id: item
                    for item in store.list_episodes(args.anime_id)
                }.get(episode_id)
                record = existing or EpisodeRecord(
                    id=episode_id,
                    anime_id=args.anime_id,
                    episode_number=args.episode_number,
                )
                record.status = "PROCESSING"
                record.current_checkpoint = "TTS"
                record.failure_reason = None
                record.provider = "local"
                record.source_reference = str(
                    args.input_path.expanduser().resolve()
                )
                record.script_manifest = str(script_path)
                record.tts_manifest = str(output_manifest)
                store.save_episode(record)

            _print_json(
                tts_manifest.to_dict()
                | {
                    "script_manifest_path": str(script_path),
                    "tts_manifest_path": str(output_manifest),
                }
            )
            return

    if args.command == "episode":
        if args.episode_command == "match":
            if (args.anime_id is None) != (args.episode_number is None):
                parser.error("--anime-id and --episode-number must be supplied together")
            if args.season < 1:
                parser.error("--season must be >= 1")
            if args.episode_number is not None and args.episode_number < 1:
                parser.error("--episode-number must be >= 1")

            scene_path = args.scene_manifest or (
                paths.workspace
                / "analysis"
                / args.input_path.stem
                / "scenes.json"
            )
            tts_path = args.tts_manifest or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "tts.json"
            )

            try:
                scene_manifest = SceneAnalysisManifest.read(scene_path)
                tts_manifest = TTSManifest.read(tts_path)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                parser.error(f"could not read scene/TTS manifests: {exc}")

            config_path = paths.config / "config.yml"
            if not config_path.exists():
                config_path = paths.config / "config.example.yml"
            app_config = load_config(config_path)

            max_clip_duration = (
                args.max_clip_duration
                if args.max_clip_duration is not None
                else app_config.video.max_clip_duration
            )
            if max_clip_duration <= 0:
                parser.error("--max-clip-duration must be positive")

            output_path = args.output or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "matching.json"
            )

            try:
                match_manifest = SceneMatcher(
                    max_clip_duration=max_clip_duration
                ).match(
                    scene_manifest,
                    tts_manifest,
                    source_scenes=str(scene_path),
                    source_tts=str(tts_path),
                )
            except MatchError as exc:
                parser.error(str(exc))

            match_manifest.write(output_path)

            if args.anime_id:
                assert args.episode_number is not None
                episode_id = f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                existing = {
                    item.id: item
                    for item in store.list_episodes(args.anime_id)
                }.get(episode_id)
                record = existing or EpisodeRecord(
                    id=episode_id,
                    anime_id=args.anime_id,
                    episode_number=args.episode_number,
                )
                record.status = "PROCESSING"
                record.current_checkpoint = "matching"
                record.failure_reason = None
                record.provider = "local"
                record.source_reference = str(
                    args.input_path.expanduser().resolve()
                )
                record.tts_manifest = str(tts_path)
                record.matching_manifest = str(output_path)
                store.save_episode(record)

            _print_json(
                match_manifest.to_dict()
                | {
                    "scene_manifest_path": str(scene_path),
                    "tts_manifest_path": str(tts_path),
                    "matching_manifest_path": str(output_path),
                }
            )
            return

    if args.command == "episode":
        if args.episode_command == "timeline":
            if (args.anime_id is None) != (args.episode_number is None):
                parser.error("--anime-id and --episode-number must be supplied together")
            if args.season < 1:
                parser.error("--season must be >= 1")
            if args.episode_number is not None and args.episode_number < 1:
                parser.error("--episode-number must be >= 1")

            matching_path = args.matching_manifest or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "matching.json"
            )
            tts_path = args.tts_manifest or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "tts.json"
            )
            output_path = args.output or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "timeline.json"
            )
            try:
                matching_manifest = SceneMatchManifest.read(matching_path)
                tts_manifest = TTSManifest.read(tts_path)
                timeline_manifest = TimelineBuilder().build(
                    matching_manifest,
                    tts_manifest,
                    source_matching=str(matching_path),
                    source_tts=str(tts_path),
                )
            except (OSError, ValueError, TypeError, KeyError, RenderError) as exc:
                parser.error(f"could not build render timeline: {exc}")

            timeline_manifest.write(output_path)

            if args.anime_id:
                assert args.episode_number is not None
                episode_id = f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                existing = {
                    item.id: item
                    for item in store.list_episodes(args.anime_id)
                }.get(episode_id)
                record = existing or EpisodeRecord(
                    id=episode_id,
                    anime_id=args.anime_id,
                    episode_number=args.episode_number,
                )
                record.status = "PROCESSING"
                record.current_checkpoint = "timeline"
                record.failure_reason = None
                record.provider = "local"
                record.source_reference = str(
                    args.input_path.expanduser().resolve()
                )
                record.matching_manifest = str(matching_path)
                record.tts_manifest = str(tts_path)
                record.timeline_manifest = str(output_path)
                store.save_episode(record)

            _print_json(
                timeline_manifest.to_dict()
                | {
                    "matching_manifest_path": str(matching_path),
                    "tts_manifest_path": str(tts_path),
                    "timeline_manifest_path": str(output_path),
                }
            )
            return

        if args.episode_command == "render":
            if (args.anime_id is None) != (args.episode_number is None):
                parser.error("--anime-id and --episode-number must be supplied together")
            if args.season < 1:
                parser.error("--season must be >= 1")
            if args.episode_number is not None and args.episode_number < 1:
                parser.error("--episode-number must be >= 1")

            timeline_path = args.timeline_manifest or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "timeline.json"
            )
            timeline_dir = args.tts_dir or (
                paths.workspace
                / "narration"
                / args.input_path.stem
                / "audio"
            )
            output_path = args.output or (
                paths.workspace
                / "output"
                / f"{args.input_path.stem}.mp4"
            )

            try:
                timeline_manifest = TimelineManifest.read(timeline_path)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                parser.error(f"could not read timeline manifest: {exc}")

            config_path = paths.config / "config.yml"
            if not config_path.exists():
                config_path = paths.config / "config.example.yml"
            app_config = load_config(config_path)

            try:
                rendered = FFmpegRenderer(
                    width=app_config.video.width,
                    height=app_config.video.height,
                    fps=app_config.video.fps,
                ).render(
                    timeline_manifest,
                    source_video=args.input_path,
                    narration_dir=timeline_dir,
                    output_path=output_path,
                    subtitles=app_config.subtitles.enabled
                    and app_config.subtitles.burn_in
                    and not args.no_subtitles,
                )
            except RenderError as exc:
                parser.error(str(exc))

            if args.anime_id:
                assert args.episode_number is not None
                episode_id = f"{args.anime_id}-s{args.season}-e{args.episode_number}"
                existing = {
                    item.id: item
                    for item in store.list_episodes(args.anime_id)
                }.get(episode_id)
                record = existing or EpisodeRecord(
                    id=episode_id,
                    anime_id=args.anime_id,
                    episode_number=args.episode_number,
                )
                record.status = "RENDERED"
                record.current_checkpoint = "render"
                record.failure_reason = None
                record.provider = "local"
                record.source_reference = str(
                    args.input_path.expanduser().resolve()
                )
                record.timeline_manifest = str(timeline_path)
                record.render_output = str(rendered)
                store.save_episode(record)

            _print_json(
                {
                    "render_output": str(rendered),
                    "timeline_manifest_path": str(timeline_path),
                }
            )
            return

    if args.command == "provider":
        config_path = paths.config / "config.yml"
        if not config_path.exists():
            config_path = paths.config / "config.example.yml"
        app_config = load_config(config_path)
        registry = build_registry(app_config, paths.root)

        if args.provider_command == "status":
            result = []
            for name in registry.names():
                provider = registry.get(name)
                health = provider.check_health()
                result.append({
                    "provider": health.provider,
                    "status": health.status,
                    "checked_at": health.checked_at,
                    "detail": health.detail,
                })
            _print_json(result)
            return

        if args.provider_command == "check":
            if args.episode_number < 1:
                parser.error("--episode-number must be >= 1")
            broker = ProviderBroker(registry)
            probes = broker.probe_episode(
                args.anime_id,
                args.episode_number,
                language=args.language,
            )
            selected = broker.best_catalog_provider(probes)
            _print_json({
                "probes": [
                    {
                        "provider": item.provider,
                        "score": round(item.score, 3),
                        "elapsed_ms": round(item.elapsed_ms, 1),
                        "catalog_available": item.catalog_available,
                        "availability": (
                            None if item.availability is None else item.availability.__dict__
                        ),
                        "error": item.error,
                    }
                    for item in probes
                ],
                "selected_catalog_provider": None if selected is None else selected.provider,
            })
            return

    if args.command == "plan":
        scheduler_state = store.load_scheduler()
        planner = Scheduler(scheduler_state)
        plans = planner.plan(store.list_anime(), store.list_episodes())
        _print_json([plan.__dict__ for plan in plans])
        return

    if args.command == "metadata":
        config_path = paths.config / "config.yml"
        if not config_path.exists():
            config_path = paths.config / "config.example.yml"
        app_config = load_config(config_path)
        service = MetadataService.create(
            anilist_endpoint=app_config.metadata.anilist_endpoint,
            jikan_base_url=app_config.metadata.jikan_base_url,
        )

        if args.metadata_command == "search":
            limit = args.limit or app_config.metadata.search_limit
            results = service.search(args.query, limit=limit)
            _print_json([
                {
                    "provider": result.provider,
                    "error": result.error,
                    "metadata": (
                        None
                        if result.metadata is None
                        else {
                            key: value
                            for key, value in result.metadata.__dict__.items()
                            if key != "raw"
                        }
                    ),
                }
                for result in results
            ])
            return

        if args.metadata_command == "get":
            metadata = service.get_anime(args.provider, args.id)
            _print_json({
                key: value
                for key, value in metadata.__dict__.items()
                if key != "raw"
            })
            return

        if args.metadata_command == "sync":
            metadata = service.get_anime(args.provider, args.id)
            record = MetadataLibrary(store).upsert(metadata)
            _print_json(record.__dict__)
            return

    parser.error("unsupported command")
