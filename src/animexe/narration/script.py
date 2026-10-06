from __future__ import annotations

import json
import os
import re
import time

import requests
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..analysis.story import EpisodeStoryManifest
from ..analysis.transcript import TranscriptAnalysisManifest


class NarrationScriptError(RuntimeError):
    """Raised when narration-script generation cannot complete reliably."""


class _ResponseClient(Protocol):
    class models:
        @staticmethod
        def generate_content(*args: Any, **kwargs: Any) -> Any: ...


SCRIPT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "hook_scene_ids": {"type": "array", "items": {"type": "string"}},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segment_id": {"type": "string"},
                    "text": {"type": "string"},
                    "scene_ids": {"type": "array", "items": {"type": "string"}},
                    "story_event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "purpose": {"type": "string"},
                    "start_seconds": {"type": "number"},
                    "end_seconds": {"type": "number"},
                },
                "required": [
                    "segment_id",
                    "text",
                    "scene_ids",
                    "story_event_ids",
                    "purpose",
                    "start_seconds",
                    "end_seconds",
                ],
            },
        },
        "ending": {"type": "string"},
        "ending_scene_ids": {"type": "array", "items": {"type": "string"}},
        "word_count": {"type": "integer"},
        "estimated_duration_seconds": {"type": "number"},
    },
    "required": [
        "hook",
        "hook_scene_ids",
        "segments",
        "ending",
        "ending_scene_ids",
        "word_count",
        "estimated_duration_seconds",
    ],
}


_FORMAT_ARTIFACTS = re.compile(r"(?:^|\s)(?:---+|___+|\*\*\*+)(?:\s|$)", re.MULTILINE)
_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_STAGE_DIRECTION = re.compile(
    r"\[[^\]]+\]|\([^)]*\b(?:pause|laughs?|music|sfx)\b[^)]*\)",
    re.I,
)


@dataclass(frozen=True)
class NarrationSegment:
    segment_id: str
    text: str
    scene_ids: tuple[str, ...]
    story_event_ids: tuple[str, ...]
    purpose: str
    start_seconds: float
    end_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "text": self.text,
            "scene_ids": list(self.scene_ids),
            "story_event_ids": list(self.story_event_ids),
            "purpose": self.purpose,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
        }


@dataclass(frozen=True)
class NarrationScriptManifest:
    schema_version: int
    episode_id: str | None
    input_path: str
    input_sha256: str
    source_story: str
    language: str
    script: str
    style: str
    target_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    words_per_minute: int
    hook: str
    hook_scene_ids: tuple[str, ...]
    segments: tuple[NarrationSegment, ...]
    ending: str
    ending_scene_ids: tuple[str, ...]
    word_count: int
    estimated_duration_seconds: float
    checkpoint: str = "script"
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "input_path": self.input_path,
            "input_sha256": self.input_sha256,
            "source_story": self.source_story,
            "language": self.language,
            "script": self.script,
            "style": self.style,
            "target_duration_seconds": self.target_duration_seconds,
            "min_duration_seconds": self.min_duration_seconds,
            "max_duration_seconds": self.max_duration_seconds,
            "words_per_minute": self.words_per_minute,
            "hook": self.hook,
            "hook_scene_ids": list(self.hook_scene_ids),
            "segments": [segment.to_dict() for segment in self.segments],
            "ending": self.ending,
            "ending_scene_ids": list(self.ending_scene_ids),
            "word_count": self.word_count,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "checkpoint": self.checkpoint,
            "model": self.model,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read(cls, path: Path) -> "NarrationScriptManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["hook_scene_ids"] = tuple(payload.get("hook_scene_ids", []))
        payload["ending_scene_ids"] = tuple(payload.get("ending_scene_ids", []))
        payload["segments"] = tuple(
            NarrationSegment(
                segment_id=item["segment_id"],
                text=item["text"],
                scene_ids=tuple(item.get("scene_ids", [])),
                story_event_ids=tuple(item.get("story_event_ids", [])),
                purpose=item.get("purpose", "explanation"),
                start_seconds=float(item["start_seconds"]),
                end_seconds=float(item["end_seconds"]),
            )
            for item in payload.get("segments", [])
        )
        return cls(**payload)


class GeminiNarrationScriptGenerator:
    """Generate an original spoken episode explanation from a semantic story manifest."""

    VALID_LANGUAGES = {"english", "hinglish"}
    VALID_SCRIPTS = {"latin", "roman"}

    def __init__(
        self,
        *,
        model: str = "gemini-3.8-flash",
        api_key_env: str = "GEMINI_API_KEY",
        temperature: float = 0.3,
        thinking_level: str = "medium",
        max_output_tokens: int = 8000,
        target_duration_seconds: float = 120.0,
        min_duration_seconds: float = 105.0,
        max_duration_seconds: float = 135.0,
        words_per_minute: int = 145,
        client: _ResponseClient | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("Gemini model cannot be empty")
        if not api_key_env.strip():
            raise ValueError("Gemini API key environment variable cannot be empty")
        if temperature < 0:
            raise ValueError("Gemini temperature cannot be negative")
        if max_output_tokens < 1:
            raise ValueError("Gemini max_output_tokens must be positive")
        if target_duration_seconds <= 0:
            raise ValueError("target_duration_seconds must be positive")
        if min_duration_seconds <= 0 or max_duration_seconds <= 0:
            raise ValueError("duration bounds must be positive")
        if min_duration_seconds > max_duration_seconds:
            raise ValueError("min_duration_seconds cannot exceed max_duration_seconds")
        if not min_duration_seconds <= target_duration_seconds <= max_duration_seconds:
            raise ValueError("target_duration_seconds must be within the duration bounds")
        if words_per_minute < 60 or words_per_minute > 220:
            raise ValueError("words_per_minute must be between 60 and 220")
        self.model = model
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.thinking_level = thinking_level
        self.max_output_tokens = max_output_tokens
        self.target_duration_seconds = target_duration_seconds
        self.min_duration_seconds = min_duration_seconds
        self.max_duration_seconds = max_duration_seconds
        self.words_per_minute = words_per_minute
        self._client = client

    def generate(
        self,
        story: EpisodeStoryManifest,
        *,
        transcript: TranscriptAnalysisManifest | None = None,
        language: str = "hinglish",
        script: str = "roman",
        style: str = "conversational",
        source_story: str = "story.json",
    ) -> NarrationScriptManifest:
        language = language.strip().lower()
        script = script.strip().lower()
        if language not in self.VALID_LANGUAGES:
            raise NarrationScriptError(
                f"unsupported narration language: {language}; choose from {sorted(self.VALID_LANGUAGES)}"
            )
        if script not in self.VALID_SCRIPTS:
            raise NarrationScriptError(
                f"unsupported narration script: {script}; choose from {sorted(self.VALID_SCRIPTS)}"
            )
        if language == "english" and script != "latin":
            raise NarrationScriptError("English narration must use script=latin")
        if language == "hinglish" and script != "roman":
            raise NarrationScriptError("Hinglish narration must use script=roman")
        if not story.summary.strip() or not story.events:
            raise NarrationScriptError(
                "story manifest does not contain enough semantic information for narration"
            )
        self._validate_transcript_alignment(story, transcript)

        target_words = round(self.target_duration_seconds / 60.0 * self.words_per_minute)
        min_words = round(self.min_duration_seconds / 60.0 * self.words_per_minute)
        max_words = round(self.max_duration_seconds / 60.0 * self.words_per_minute)
        prompt = self._build_prompt(
            story,
            language=language,
            script=script,
            style=style,
            target_words=target_words,
            min_words=min_words,
            max_words=max_words,
        )

        try:
            if self._client is not None:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=[prompt],
                    config=self._generation_config(),
                )
                response_text = getattr(response, "text", None)
                used_model = self.model
            else:
                response_text, used_model = self._rest_generate(prompt)
        except Exception as exc:
            raise NarrationScriptError(
                f"Gemini narration-script request failed: {exc}"
            ) from exc

        if not isinstance(response_text, str) or not response_text.strip():
            raise NarrationScriptError("Gemini returned an empty narration script")

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise NarrationScriptError(
                "Gemini returned invalid narration-script JSON"
            ) from exc

        return self._manifest_from_payload(
            payload,
            story,
            transcript=transcript,
            language=language,
            script=script,
            style=style,
            source_story=source_story,
            model=used_model,
        )

    def _rest_generate(self) -> _ResponseClient:
        if self._client is not None:
            return self._client
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise NarrationScriptError(
                f"Gemini API key is missing; set {self.api_key_env} in the environment"
            )
        try:
            from google import genai
        except ImportError as exc:
            raise NarrationScriptError(
                "google-genai is not installed; install the project dependencies first"
            ) from exc
        self._client = genai.Client(api_key=api_key)
        return self._client

    def _generation_config(self) -> Any:
        try:
            from google.genai import types
        except ImportError as exc:
            raise NarrationScriptError(
                "google-genai is not installed; install the project dependencies first"
            ) from exc
        kwargs = {
            "max_output_tokens": self.max_output_tokens,
            "response_mime_type": "application/json",
            "response_schema": SCRIPT_RESPONSE_SCHEMA,
        }
        if self.model.startswith("gemini-3"):
            kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=self.thinking_level
            )
        else:
            kwargs["temperature"] = self.temperature
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _validate_transcript_alignment(
        story: EpisodeStoryManifest,
        transcript: TranscriptAnalysisManifest | None,
    ) -> None:
        if transcript is None:
            return
        if story.input_path != transcript.input_path:
            raise NarrationScriptError(
                "story and transcript manifests reference different input files"
            )
        if story.input_sha256 and transcript.input_sha256:
            if story.input_sha256 != transcript.input_sha256:
                raise NarrationScriptError(
                    "story and transcript fingerprints do not match"
                )

    def _build_prompt(
        self,
        story: EpisodeStoryManifest,
        *,
        language: str,
        script: str,
        style: str,
        target_words: int,
        min_words: int,
        max_words: int,
    ) -> str:
        event_rows = [
            {
                "event_id": event.event_id,
                "scene_ids": list(event.scene_ids),
                "start_seconds": event.start_seconds,
                "end_seconds": event.end_seconds,
                "description": event.text,
                "importance": event.importance,
                "kind": event.kind,
            }
            for event in story.events
        ]
        if language == "english":
            language_instruction = (
                "Write natural spoken English in Latin script. "
                "Use simple, conversational phrasing suitable for a YouTube narrator."
            )
        else:
            language_instruction = (
                "Write natural spoken Hinglish in Roman script. "
                "Use Hindi as the conversational base with English terms only where a speaker "
                "would naturally use them. Do not force English words into every sentence and "
                "do not translate Hindi mechanically."
            )

        return (
            "You are AniMeXe's original narration-script writer. "
            "Turn the supplied semantic episode story into an engaging spoken explanation. "
            "The story manifest is the factual source of truth. "
            "Preserve event order and only reference real scene IDs and story event IDs. "
            "Explain what happens rather than reading or paraphrasing subtitles line by line. "
            "Do not invent events, motives, relationships, characters, locations, or outcomes. "
            "Do not copy dialogue or subtitle sentences. Prefer original explanation and paraphrase. "
            "This is voice narration, not an article: no markdown, headings, bullets, stage directions, "
            "emoji, decorative separators, repeated punctuation, or AI-style filler. "
            "Never use em-dash or underscore separator patterns such as '---' or '___'. "
            f"{language_instruction} "
            f"Use a {style} tone with a strong opening hook and a clear ending. "
            f"Target about {target_words} words and stay between {min_words} and {max_words} words. "
            "Keep the main explanation chronological. "
            "Each body segment should map to the smallest useful set of story events and scenes. "
            "start_seconds/end_seconds are approximate narration-timeline anchors only; later TTS "
            "will replace them with measured audio timing. "
            "Return only JSON matching the supplied schema.\n\n"
            f"EPISODE SUMMARY:\n{story.summary}\n\n"
            f"CHARACTERS:\n{json.dumps(list(story.evidence.characters), ensure_ascii=False)}\n\n"
            f"LOCATIONS:\n{json.dumps(list(story.evidence.locations), ensure_ascii=False)}\n\n"
            f"RELATIONSHIPS:\n{json.dumps(list(story.relationships), ensure_ascii=False)}\n\n"
            f"NARRATION POINTS:\n{json.dumps(list(story.narration_points), ensure_ascii=False)}\n\n"
            f"ENDING:\n{story.ending}\n\n"
            f"EVENTS:\n{json.dumps(event_rows, ensure_ascii=False)}"
        )

    def _manifest_from_payload(
        self,
        payload: Any,
        story: EpisodeStoryManifest,
        *,
        transcript: TranscriptAnalysisManifest | None,
        language: str,
        script: str,
        style: str,
        source_story: str,
    ) -> NarrationScriptManifest:
        if not isinstance(payload, dict):
            raise NarrationScriptError("Gemini narration response must be a JSON object")

        required = (
            "hook",
            "hook_scene_ids",
            "segments",
            "ending",
            "ending_scene_ids",
            "word_count",
            "estimated_duration_seconds",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise NarrationScriptError(
                "Gemini narration response is missing fields: " + ", ".join(missing)
            )

        valid_scene_ids = {scene_id for event in story.events for scene_id in event.scene_ids}
        valid_event_ids = {event.event_id for event in story.events}
        if not valid_scene_ids:
            raise NarrationScriptError("story manifest contains no usable scene IDs")

        hook = str(payload["hook"]).strip()
        ending = str(payload["ending"]).strip()
        if not hook or not ending:
            raise NarrationScriptError("narration hook and ending are required")
        self._validate_text_quality(hook, "hook")
        self._validate_text_quality(ending, "ending")

        hook_scene_ids = self._validate_scene_ids(
            payload["hook_scene_ids"], valid_scene_ids, "hook"
        )
        ending_scene_ids = self._validate_scene_ids(
            payload["ending_scene_ids"], valid_scene_ids, "ending"
        )

        raw_segments = payload["segments"]
        if not isinstance(raw_segments, list) or not raw_segments:
            raise NarrationScriptError("narration must contain at least one segment")

        segments: list[NarrationSegment] = []
        seen_ids: set[str] = set()
        previous_end = -1.0
        text_parts = [hook]

        for item in raw_segments:
            if not isinstance(item, dict):
                raise NarrationScriptError("narration segment entries must be objects")
            segment_id = str(item.get("segment_id", "")).strip()
            text_value = str(item.get("text", "")).strip()
            if not segment_id or not text_value:
                raise NarrationScriptError("narration segments require IDs and text")
            if segment_id in seen_ids:
                raise NarrationScriptError(
                    f"duplicate narration segment_id: {segment_id}"
                )
            seen_ids.add(segment_id)

            self._validate_text_quality(text_value, segment_id)
            scene_values = self._validate_scene_ids(
                item.get("scene_ids", []), valid_scene_ids, segment_id
            )
            event_values = self._validate_event_ids(
                item.get("story_event_ids", []), valid_event_ids, segment_id
            )
            if not event_values:
                raise NarrationScriptError(
                    f"narration segment {segment_id} must reference at least one story event"
                )

            try:
                start = float(item["start_seconds"])
                end = float(item["end_seconds"])
            except (KeyError, TypeError, ValueError) as exc:
                raise NarrationScriptError(
                    f"narration segment {segment_id} has invalid timing"
                ) from exc
            if start < 0 or end <= start or start < previous_end:
                raise NarrationScriptError(
                    f"narration segment {segment_id} has non-chronological timing"
                )
            previous_end = end

            segments.append(
                NarrationSegment(
                    segment_id=segment_id,
                    text=text_value,
                    scene_ids=scene_values,
                    story_event_ids=event_values,
                    purpose=str(item.get("purpose", "explanation")).strip()
                    or "explanation",
                    start_seconds=start,
                    end_seconds=end,
                )
            )
            text_parts.append(text_value)

        text_parts.append(ending)
        combined_text = " ".join(text_parts)
        self._validate_text_quality(combined_text, "script")

        if transcript is not None:
            self._validate_copy_risk(combined_text, transcript)

        actual_word_count = self._word_count(combined_text)
        min_words = round(self.min_duration_seconds / 60.0 * self.words_per_minute)
        max_words = round(self.max_duration_seconds / 60.0 * self.words_per_minute)
        if not min_words <= actual_word_count <= max_words:
            raise NarrationScriptError(
                f"narration word count {actual_word_count} is outside the configured range "
                f"{min_words}-{max_words}"
            )

        try:
            reported_word_count = int(payload["word_count"])
            reported_duration = float(payload["estimated_duration_seconds"])
        except (TypeError, ValueError, KeyError) as exc:
            raise NarrationScriptError(
                "narration word_count and estimated_duration_seconds must be numeric"
            ) from exc

        if abs(reported_word_count - actual_word_count) > max(
            12, round(actual_word_count * 0.08)
        ):
            raise NarrationScriptError(
                "narration word_count disagrees materially with generated text"
            )

        estimated_duration = actual_word_count / self.words_per_minute * 60.0
        if not self.min_duration_seconds <= estimated_duration <= self.max_duration_seconds:
            raise NarrationScriptError(
                f"estimated narration duration {estimated_duration:.1f}s is outside "
                f"{self.min_duration_seconds:.1f}-{self.max_duration_seconds:.1f}s"
            )
        if abs(reported_duration - estimated_duration) > max(
            18.0, estimated_duration * 0.20
        ):
            raise NarrationScriptError(
                "Gemini estimated_duration_seconds disagrees materially with generated text"
            )

        return NarrationScriptManifest(
            schema_version=1,
            episode_id=story.episode_id,
            input_path=story.input_path,
            input_sha256=story.input_sha256,
            source_story=source_story,
            language=language,
            script=script,
            style=style,
            target_duration_seconds=self.target_duration_seconds,
            min_duration_seconds=self.min_duration_seconds,
            max_duration_seconds=self.max_duration_seconds,
            words_per_minute=self.words_per_minute,
            hook=hook,
            hook_scene_ids=hook_scene_ids,
            segments=tuple(segments),
            ending=ending,
            ending_scene_ids=ending_scene_ids,
            word_count=actual_word_count,
            estimated_duration_seconds=round(estimated_duration, 3),
            model=self.model,
        )

    @staticmethod
    def _validate_scene_ids(
        value: Any,
        valid_ids: set[str],
        label: str,
    ) -> tuple[str, ...]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise NarrationScriptError(
                f"narration {label} scene_ids must be a list of strings"
            )
        values = tuple(item.strip() for item in value if item.strip())
        if not values:
            raise NarrationScriptError(
                f"narration {label} must reference at least one scene"
            )
        unknown = [item for item in values if item not in valid_ids]
        if unknown:
            raise NarrationScriptError(
                f"narration {label} references unknown scene IDs: {', '.join(unknown)}"
            )
        return values

    @staticmethod
    def _validate_event_ids(
        value: Any,
        valid_ids: set[str],
        label: str,
    ) -> tuple[str, ...]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise NarrationScriptError(
                f"narration segment {label} story_event_ids must be a list of strings"
            )
        values = tuple(item.strip() for item in value if item.strip())
        unknown = [item for item in values if item not in valid_ids]
        if unknown:
            raise NarrationScriptError(
                f"narration segment {label} references unknown story events: {', '.join(unknown)}"
            )
        return values

    @staticmethod
    def _validate_text_quality(value: str, label: str) -> None:
        if _FORMAT_ARTIFACTS.search(value) or _MARKDOWN_HEADING.search(value):
            raise NarrationScriptError(
                f"narration {label} contains markdown/decorative formatting"
            )
        if _STAGE_DIRECTION.search(value) or "—" in value:
            raise NarrationScriptError(
                f"narration {label} contains stage directions or decorative em-dash formatting"
            )
        if re.search(r"([!?.,])\1{3,}", value):
            raise NarrationScriptError(
                f"narration {label} contains repeated punctuation"
            )

    @staticmethod
    def _word_count(text_value: str) -> int:
        return len(re.findall(r"\b[\w']+\b", text_value, flags=re.UNICODE))

    @classmethod
    def _validate_copy_risk(
        cls,
        script_text: str,
        transcript: TranscriptAnalysisManifest,
    ) -> None:
        script_words = cls._normalized_words(script_text)
        transcript_words = cls._normalized_words(
            " ".join(segment.text for segment in transcript.segments)
        )
        if len(script_words) < 9 or len(transcript_words) < 9:
            return
        script_ngrams = {
            tuple(script_words[index:index + 9])
            for index in range(len(script_words) - 8)
        }
        transcript_ngrams = {
            tuple(transcript_words[index:index + 9])
            for index in range(len(transcript_words) - 8)
        }
        if script_ngrams & transcript_ngrams:
            raise NarrationScriptError(
                "narration contains an exact 9-word subtitle overlap; rewrite as original explanation"
            )

    @staticmethod
    def _normalized_words(text_value: str) -> list[str]:
        return re.findall(r"\b[\w']+\b", text_value.lower(), flags=re.UNICODE)
