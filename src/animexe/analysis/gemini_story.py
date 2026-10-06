from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from .scenes import SceneAnalysisManifest
from .story import (
    EpisodeStoryManifest,
    StoryEvent,
    StoryEvidence,
)
from .transcript import TranscriptAnalysisManifest


class GeminiStoryError(RuntimeError):
    """Raised when Gemini-backed story understanding cannot complete."""


class _ResponseClient(Protocol):
    class models:
        @staticmethod
        def generate_content(*args: Any, **kwargs: Any) -> Any: ...


STORY_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "episode_summary": {"type": "string"},
        "characters": {"type": "array", "items": {"type": "string"}},
        "locations": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "relationships": {"type": "array", "items": {"type": "string"}},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "scene_ids": {"type": "array", "items": {"type": "string"}},
                    "start_seconds": {"type": "number"},
                    "end_seconds": {"type": "number"},
                    "description": {"type": "string"},
                    "importance": {"type": "number"},
                    "kind": {"type": "string"},
                },
                "required": [
                    "event_id",
                    "scene_ids",
                    "start_seconds",
                    "end_seconds",
                    "description",
                    "importance",
                    "kind",
                ],
            },
        },
        "ending": {"type": "string"},
        "continuity_notes": {"type": "array", "items": {"type": "string"}},
        "narration_points": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": [
        "episode_summary",
        "characters",
        "locations",
        "keywords",
        "relationships",
        "events",
        "ending",
        "continuity_notes",
        "narration_points",
        "confidence",
    ],
}


class GeminiStoryAnalyzer:
    """Understand an episode with Gemini using transcript evidence plus scene frames."""

    def __init__(
        self,
        *,
        model: str = "gemini-3.8-flash",
        api_key_env: str = "GEMINI_API_KEY",
        temperature: float = 0.2,
        thinking_level: str = "medium",
        max_output_tokens: int = 12000,
        max_frames: int = 32,
        client: _ResponseClient | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("Gemini model cannot be empty")
        if not api_key_env.strip():
            raise ValueError("Gemini API key environment variable cannot be empty")
        if temperature < 0:
            raise ValueError("Gemini temperature cannot be negative")
        if thinking_level not in {"low", "medium", "high"}:
            raise ValueError("Gemini thinking_level must be low, medium, or high")
        if max_output_tokens < 1:
            raise ValueError("Gemini max_output_tokens must be positive")
        if max_frames < 0:
            raise ValueError("Gemini max_frames cannot be negative")

        self.model = model
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.thinking_level = thinking_level
        self.max_output_tokens = max_output_tokens
        self.max_frames = max_frames
        self._client = client

    def analyze(
        self,
        transcript: TranscriptAnalysisManifest,
        scenes: SceneAnalysisManifest,
        *,
        scene_manifest_dir: Path | None = None,
        source_transcript: str = "transcript.json",
        source_scenes: str = "scenes.json",
    ) -> EpisodeStoryManifest:
        self._validate_inputs(transcript, scenes)

        prompt = self._build_prompt(transcript, scenes)
        contents: list[Any] = [prompt]
        contents.extend(
            self._frame_parts(
                scenes,
                scene_manifest_dir=scene_manifest_dir,
            )
        )

        try:
            response = self._client_or_create().models.generate_content(
                model=self.model,
                contents=contents,
                config=self._generation_config(),
            )
        except Exception as exc:
            raise GeminiStoryError(f"Gemini story request failed: {exc}") from exc

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise GeminiStoryError("Gemini returned an empty story response")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiStoryError("Gemini returned invalid JSON") from exc

        return self._manifest_from_payload(
            payload,
            transcript,
            scenes,
            source_transcript=source_transcript,
            source_scenes=source_scenes,
            model=self.model,
        )

    def _client_or_create(self) -> _ResponseClient:
        if self._client is not None:
            return self._client

        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise GeminiStoryError(
                f"Gemini API key is missing; set {self.api_key_env} in the environment"
            )

        try:
            from google import genai
        except ImportError as exc:
            raise GeminiStoryError(
                "google-genai is not installed; install the project dependencies first"
            ) from exc

        self._client = genai.Client(api_key=api_key)
        return self._client

    def _generation_config(self) -> Any:
        try:
            from google.genai import types
        except ImportError as exc:
            raise GeminiStoryError(
                "google-genai is not installed; install the project dependencies first"
            ) from exc

        kwargs = {
            "max_output_tokens": self.max_output_tokens,
            "response_mime_type": "application/json",
            "response_schema": STORY_RESPONSE_SCHEMA,
        }
        if self.model.startswith("gemini-3"):
            kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=self.thinking_level
            )
        else:
            kwargs["temperature"] = self.temperature
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _validate_inputs(
        transcript: TranscriptAnalysisManifest,
        scenes: SceneAnalysisManifest,
    ) -> None:
        if transcript.input_path != scenes.input_path:
            raise GeminiStoryError(
                "transcript and scene manifests reference different input files"
            )
        if transcript.input_sha256 and scenes.input_sha256:
            if transcript.input_sha256 != scenes.input_sha256:
                raise GeminiStoryError(
                    "transcript and scene fingerprints do not match"
                )
        if transcript.transcript_status != "READY":
            raise GeminiStoryError("transcript is not ready for story understanding")
        if not scenes.scenes:
            raise GeminiStoryError("scene manifest contains no scenes")

    @staticmethod
    def _build_prompt(
        transcript: TranscriptAnalysisManifest,
        scenes: SceneAnalysisManifest,
    ) -> str:
        scene_rows = [
            {
                "scene_id": scene.scene_id,
                "index": scene.index,
                "start_seconds": scene.start_seconds,
                "end_seconds": scene.end_seconds,
                "duration_seconds": scene.duration_seconds,
            }
            for scene in scenes.scenes
        ]
        transcript_rows = [
            {
                "segment_id": segment.segment_id,
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "scene_ids": list(segment.scene_ids),
                "text": segment.text,
            }
            for segment in transcript.segments
        ]

        return (
            "You are the semantic story-understanding layer of AniMeXe. "
            "Analyze this single anime episode from the supplied transcript and scene frames. "
            "Build a factual intermediate representation for a later original episode explanation. "
            "Do not invent events, characters, locations, relationships, or dialogue. "
            "Use scene_ids exactly as supplied. Keep events chronological. "
            "Use concise factual descriptions rather than screenplay prose. "
            "Treat subtitle text as evidence, not as the final narration script. "
            "Separate what is explicitly supported from uncertain interpretation. "
            "The ending should describe the episode's final meaningful story state. "
            "Narration points should be original explanation points, not copied subtitle lines. "
            "Return only JSON matching the provided schema.\n\n"
            f"SCENES:\n{json.dumps(scene_rows, ensure_ascii=False)}\n\n"
            f"TRANSCRIPT SEGMENTS:\n{json.dumps(transcript_rows, ensure_ascii=False)}"
        )

    def _frame_parts(
        self,
        scenes: SceneAnalysisManifest,
        *,
        scene_manifest_dir: Path | None,
    ) -> list[Any]:
        if not scene_manifest_dir or self.max_frames == 0:
            return []

        try:
            from google.genai import types
        except ImportError as exc:
            raise GeminiStoryError(
                "google-genai is not installed; install the project dependencies first"
            ) from exc

        parts: list[Any] = []
        added = 0
        for scene in scenes.scenes:
            if added >= self.max_frames:
                break
            if not scene.representative_frame:
                continue

            frame_path = (scene_manifest_dir / scene.representative_frame).resolve()
            if not frame_path.exists() or not frame_path.is_file():
                continue

            try:
                data = frame_path.read_bytes()
            except OSError:
                continue
            parts.append(
                types.Part.from_bytes(
                    data=data,
                    mime_type="image/jpeg",
                )
            )
            parts.append(
                (
                    f"Visual reference for scene {scene.scene_id} at "
                    f"{scene.representative_time_seconds:.3f}s."
                )
            )
            added += 1

        return parts

    @classmethod
    def _manifest_from_payload(
        cls,
        payload: Any,
        transcript: TranscriptAnalysisManifest,
        scenes: SceneAnalysisManifest,
        *,
        source_transcript: str,
        source_scenes: str,
        model: str,
    ) -> EpisodeStoryManifest:
        if not isinstance(payload, dict):
            raise GeminiStoryError("Gemini story response must be a JSON object")

        required = (
            "episode_summary",
            "characters",
            "locations",
            "keywords",
            "relationships",
            "events",
            "ending",
            "continuity_notes",
            "narration_points",
            "confidence",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise GeminiStoryError(
                "Gemini story response is missing fields: " + ", ".join(missing)
            )

        scene_ids = {scene.scene_id for scene in scenes.scenes}
        events: list[StoryEvent] = []
        seen_event_ids: set[str] = set()
        for item in payload["events"]:
            if not isinstance(item, dict):
                raise GeminiStoryError("Gemini event entries must be objects")

            event_id = str(item.get("event_id", "")).strip()
            event_scene_ids = tuple(str(value).strip() for value in item.get("scene_ids", []))
            if not event_id:
                raise GeminiStoryError("Gemini returned an event without event_id")
            if event_id in seen_event_ids:
                raise GeminiStoryError(f"Gemini returned duplicate event_id: {event_id}")
            seen_event_ids.add(event_id)
            if not event_scene_ids or any(value not in scene_ids for value in event_scene_ids):
                raise GeminiStoryError(
                    f"Gemini event {event_id} references an unknown scene_id"
                )

            try:
                start = float(item["start_seconds"])
                end = float(item["end_seconds"])
                importance = float(item["importance"])
            except (KeyError, TypeError, ValueError) as exc:
                raise GeminiStoryError(
                    f"Gemini event {event_id} contains invalid timing or importance"
                ) from exc

            if end < start:
                raise GeminiStoryError(
                    f"Gemini event {event_id} has end_seconds before start_seconds"
                )
            if not 0.0 <= importance <= 1.0:
                raise GeminiStoryError(
                    f"Gemini event {event_id} importance must be between 0 and 1"
                )

            description = str(item.get("description", "")).strip()
            if not description:
                raise GeminiStoryError(
                    f"Gemini event {event_id} has an empty description"
                )

            events.append(
                StoryEvent(
                    event_id=event_id,
                    scene_ids=event_scene_ids,
                    start_seconds=start,
                    end_seconds=end,
                    text=description,
                    importance=round(importance, 3),
                    kind=str(item.get("kind", "story")).strip() or "story",
                )
            )

        try:
            confidence = float(payload["confidence"])
        except (TypeError, ValueError) as exc:
            raise GeminiStoryError("Gemini confidence must be numeric") from exc
        if not 0.0 <= confidence <= 1.0:
            raise GeminiStoryError("Gemini confidence must be between 0 and 1")

        def _string_tuple(key: str) -> tuple[str, ...]:
            value = payload[key]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise GeminiStoryError(f"Gemini field {key} must be a list of strings")
            return tuple(item.strip() for item in value if item.strip())

        characters = _string_tuple("characters")
        locations = _string_tuple("locations")
        keywords = _string_tuple("keywords")
        relationships = _string_tuple("relationships")
        continuity_notes = _string_tuple("continuity_notes")
        narration_points = _string_tuple("narration_points")

        summary = str(payload["episode_summary"]).strip()
        ending = str(payload["ending"]).strip()
        if not summary:
            raise GeminiStoryError("Gemini episode_summary cannot be empty")
        if not ending:
            raise GeminiStoryError("Gemini ending cannot be empty")

        ending_event_id = events[-1].event_id if events else None
        return EpisodeStoryManifest(
            schema_version=2,
            episode_id=transcript.episode_id or scenes.episode_id,
            input_path=transcript.input_path,
            input_sha256=transcript.input_sha256 or scenes.input_sha256,
            source_transcript=source_transcript,
            source_scenes=source_scenes,
            method="gemini",
            evidence=StoryEvidence(
                characters=characters,
                locations=locations,
                keywords=keywords,
            ),
            events=tuple(events),
            ending_event_id=ending_event_id,
            continuity_notes=continuity_notes,
            summary=summary,
            relationships=relationships,
            ending=ending,
            narration_points=narration_points,
            confidence=round(confidence, 3),
            model=model,
        )
