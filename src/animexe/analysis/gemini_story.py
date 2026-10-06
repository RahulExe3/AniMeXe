from __future__ import annotations

import base64
import hashlib
import json
import os
import time

import requests
from pathlib import Path
from typing import Any, Protocol

from .scenes import SceneAnalysisManifest
from .story import (
    EpisodeStoryManifest,
    StoryEvent,
    StoryEvidence,
)
from .transcript import TranscriptAnalysisManifest


STORY_CACHE_VERSION = 2
STORY_REQUIRED_FIELDS = (
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

        try:
            if self._client is not None:
                contents: list[Any] = [prompt]
                contents.extend(
                    self._frame_parts(
                        scenes,
                        scene_manifest_dir=scene_manifest_dir,
                    )
                )
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=self._generation_config(),
                )
                text = getattr(response, "text", None)
                used_model = self.model
            else:
                text, used_model = self._rest_generate(
                    prompt,
                    scenes,
                    scene_manifest_dir=scene_manifest_dir,
                )
        except Exception as exc:
            raise GeminiStoryError(f"Gemini story request failed: {exc}") from exc

        if not isinstance(text, str) or not text.strip():
            raise GeminiStoryError("Gemini returned an empty story response")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiStoryError("Gemini returned invalid JSON") from exc

        payload = self._unwrap_story_payload(payload)

        try:
            manifest = self._manifest_from_payload(
                payload,
                transcript,
                scenes,
                source_transcript=source_transcript,
                source_scenes=source_scenes,
                model=used_model,
            )
        except GeminiStoryError as first_error:
            if "missing fields:" not in str(first_error):
                raise

            repair_prompt = (
                "The previous Gemini story response was valid JSON but incomplete. "
                "Repair it into one complete story object. Return ONLY JSON. "
                "Preserve every valid field from the draft. Do not invent events, characters, "
                "locations, relationships, dialogue, or outcomes. For genuinely unsupported "
                "list fields, use an empty array. The events list must contain every meaningful "
                "event explicitly supported by the supplied transcript and scene evidence. "
                "The top-level object MUST contain exactly these fields: "
                + ", ".join(STORY_REQUIRED_FIELDS)
                + "\n\nORIGINAL TASK:\n"
                + prompt
                + "\n\nINCOMPLETE DRAFT:\n"
                + json.dumps(payload, ensure_ascii=False)
                + "\n\nVALIDATION ERROR:\n"
                + str(first_error)
            )
            last_error: Exception = first_error
            for _ in range(2):
                try:
                    repair_text, repair_model = self._rest_generate(
                        repair_prompt,
                        scenes,
                        scene_manifest_dir=scene_manifest_dir,
                    )
                    repaired = self._unwrap_story_payload(json.loads(repair_text))
                    manifest = self._manifest_from_payload(
                        repaired,
                        transcript,
                        scenes,
                        source_transcript=source_transcript,
                        source_scenes=source_scenes,
                        model=repair_model,
                    )
                    text = repair_text
                    used_model = repair_model
                    break
                except (json.JSONDecodeError, GeminiStoryError) as exc:
                    last_error = exc
                    repair_prompt += (
                        "\n\nREPAIR AGAIN. The last repair was still invalid: "
                        + str(exc)
                        + "\nDo not omit any required top-level field."
                    )
            else:
                raise GeminiStoryError(
                    "Gemini story response could not be repaired after two validation passes: "
                    + str(last_error)
                ) from last_error

        if self._client is None:
            self._save_cached_response(
                prompt,
                scenes=scenes,
                model=used_model,
                text=text,
                scene_manifest_dir=scene_manifest_dir,
            )
        return manifest

    def _rest_generate(
        self,
        prompt: str,
        scenes: SceneAnalysisManifest,
        *,
        scene_manifest_dir: Path | None,
    ) -> tuple[str, str]:
        """Generate story JSON using the same direct REST pattern as YTAutoPilot."""
        api_key = os.getenv(self.api_key_env, "").strip()
        if not api_key:
            raise GeminiStoryError(
                f"Gemini API key is missing; set {self.api_key_env} in the environment"
            )

        configured_model = (os.getenv("GEMINI_MODEL") or self.model).strip()
        fallback_env = os.getenv("GEMINI_FALLBACK_MODELS", "").strip()
        model_candidates: list[str] = []
        for candidate in (configured_model, self.model, *fallback_env.split(",")):
            candidate = candidate.strip()
            if candidate and candidate not in model_candidates:
                model_candidates.append(candidate)

        parts: list[dict[str, Any]] = [{"text": prompt}]
        if scene_manifest_dir and self.max_frames:
            added = 0
            for scene in scenes.scenes:
                if added >= self.max_frames:
                    break
                if not scene.representative_frame:
                    continue
                frame_path = (scene_manifest_dir / scene.representative_frame).resolve()
                if not frame_path.is_file():
                    continue
                try:
                    data = frame_path.read_bytes()
                except OSError:
                    continue
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": base64.b64encode(data).decode("ascii"),
                        }
                    }
                )
                parts.append(
                    {
                        "text": (
                            f"Visual reference for scene {scene.scene_id} at "
                            f"{scene.representative_time_seconds:.3f}s."
                        )
                    }
                )
                added += 1

        errors: list[str] = []
        cached = self._load_cached_response(
            prompt,
            scenes=scenes,
            model_candidates=model_candidates,
            scene_manifest_dir=scene_manifest_dir,
        )
        if cached is not None:
            return cached

        for candidate_model in model_candidates:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{candidate_model}:generateContent"
            )

            for attempt in range(3):
                try:
                    generation_config: dict[str, Any] = {
                        "maxOutputTokens": self.max_output_tokens,
                        "responseMimeType": "application/json",
                        "responseSchema": self._rest_schema(STORY_RESPONSE_SCHEMA),
                    }
                    candidate_lower = candidate_model.lower()
                    if candidate_lower.startswith("gemini-3"):
                        generation_config["thinkingConfig"] = {
                            "thinkingLevel": self.thinking_level
                        }
                    else:
                        generation_config["temperature"] = self.temperature

                    response = requests.post(
                        url,
                        params={"key": api_key},
                        json={
                            "contents": [{"parts": parts}],
                            "generationConfig": generation_config,
                        },
                        timeout=60,
                    )

                    if response.status_code in {429, 500, 502, 503, 504}:
                        errors.append(
                            f"{candidate_model} attempt {attempt + 1}: "
                            f"HTTP {response.status_code}"
                        )
                        if attempt < 2:
                            time.sleep(2 ** attempt)
                            continue
                        break

                    response.raise_for_status()
                    payload = response.json()
                    text = self._response_text(payload)
                    if text:
                        return text, candidate_model
                    errors.append(
                        f"{candidate_model} attempt {attempt + 1}: {self._response_diagnostic(payload)}"
                    )
                except requests.RequestException as exc:
                    detail = str(exc)
                    if isinstance(exc, requests.HTTPError) and exc.response is not None:
                        detail = (
                            f"HTTP {exc.response.status_code}: "
                            f"{exc.response.text[:1000]}"
                        )
                    errors.append(
                        f"{candidate_model} attempt {attempt + 1}: {detail}"
                    )
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    break

        raise GeminiStoryError(
            "Gemini REST generation failed after retries. "
            + " | ".join(errors[-8:])
        )

    @staticmethod
    def _rest_schema(schema: dict[str, Any]) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: (
                        value.upper()
                        if key == "type" and isinstance(value, str)
                        else convert(value)
                    )
                    for key, value in value.items()
                }
            if isinstance(value, list):
                return [convert(item) for item in value]
            return value

        return convert(schema)

    @staticmethod
    def _response_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        for candidate in payload.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content") or {}
            texts: list[str] = []
            for part in content.get("parts") or []:
                if not isinstance(part, dict) or part.get("thought"):
                    continue
                value = part.get("text")
                if isinstance(value, str) and value.strip():
                    texts.append(value)
            if texts:
                return "\n".join(texts).strip()
        return ""

    @staticmethod
    def _response_diagnostic(payload: Any) -> str:
        if not isinstance(payload, dict):
            return "empty or non-object response"
        feedback = payload.get("promptFeedback") or {}
        block_reason = feedback.get("blockReason")
        if block_reason:
            return f"no text; prompt block reason={block_reason}"
        finishes = [
            item.get("finishReason")
            for item in payload.get("candidates") or []
            if isinstance(item, dict) and item.get("finishReason")
        ]
        if finishes:
            return f"no text; finishReason={','.join(map(str, finishes))}"
        return "no text candidate"

    @staticmethod
    def _cache_root(scene_manifest_dir: Path | None) -> Path:
        configured = os.getenv("ANIMEXE_GEMINI_CACHE_DIR", "").strip()
        if configured:
            return Path(configured).expanduser()
        return Path.cwd() / "workspace" / "cache" / "gemini" / "story"

    def _cache_key(self, prompt: str, scenes: SceneAnalysisManifest, model: str) -> str:
        payload = {
            "version": STORY_CACHE_VERSION,
            "model": model,
            "prompt": prompt,
            "input_sha256": scenes.input_sha256,
            "max_frames": self.max_frames,
            "thinking_level": self.thinking_level,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def _load_cached_response(
        self,
        prompt: str,
        *,
        scenes: SceneAnalysisManifest,
        model_candidates: list[str],
        scene_manifest_dir: Path | None,
    ) -> tuple[str, str] | None:
        root = self._cache_root(scene_manifest_dir)
        for model in model_candidates:
            path = root / f"{self._cache_key(prompt, scenes, model)}.json"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            text = payload.get("text") if isinstance(payload, dict) else None
            cached_model = payload.get("model") if isinstance(payload, dict) else None
            if isinstance(text, str) and text.strip() and isinstance(cached_model, str):
                return text, cached_model
        return None

    def _save_cached_response(
        self,
        prompt: str,
        *,
        scenes: SceneAnalysisManifest,
        model: str,
        text: str,
        scene_manifest_dir: Path | None,
    ) -> None:
        root = self._cache_root(scene_manifest_dir)
        path = root / f"{self._cache_key(prompt, scenes, model)}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"version": STORY_CACHE_VERSION, "model": model, "text": text},
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            tmp.replace(path)
        except OSError:
            return

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

    @staticmethod
    def _unwrap_story_payload(payload: Any) -> Any:
        """Accept the exact story object or a harmless one-key JSON wrapper."""
        required = {
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
        }
        current = payload
        for _ in range(2):
            if not isinstance(current, dict):
                return current
            if required.issubset(current):
                return current
            if len(current) != 1:
                return current
            nested = next(iter(current.values()))
            if not isinstance(nested, dict):
                return current
            current = nested
        return current

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

        required = STORY_REQUIRED_FIELDS
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
