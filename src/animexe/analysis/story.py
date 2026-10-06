from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .scenes import SceneAnalysisManifest
from .transcript import TranscriptAnalysisManifest


class StoryAnalysisError(RuntimeError):
    """Raised when story evidence cannot be assembled reliably."""


@dataclass(frozen=True)
class StoryEvent:
    event_id: str
    scene_ids: tuple[str, ...]
    start_seconds: float
    end_seconds: float
    text: str
    importance: float
    kind: str = "dialogue"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "scene_ids": list(self.scene_ids),
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "text": self.text,
            "importance": self.importance,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class StoryEvidence:
    characters: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": list(self.characters),
            "locations": list(self.locations),
            "keywords": list(self.keywords),
        }


@dataclass(frozen=True)
class EpisodeStoryManifest:
    schema_version: int
    episode_id: str | None
    input_path: str
    input_sha256: str
    source_transcript: str
    source_scenes: str
    method: str
    evidence: StoryEvidence
    events: tuple[StoryEvent, ...] = field(default_factory=tuple)
    ending_event_id: str | None = None
    continuity_notes: tuple[str, ...] = ()
    checkpoint: str = "story"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "input_path": self.input_path,
            "input_sha256": self.input_sha256,
            "source_transcript": self.source_transcript,
            "source_scenes": self.source_scenes,
            "method": self.method,
            "evidence": self.evidence.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "ending_event_id": self.ending_event_id,
            "continuity_notes": list(self.continuity_notes),
            "checkpoint": self.checkpoint,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read(cls, path: Path) -> "EpisodeStoryManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence = StoryEvidence(**payload["evidence"])
        payload["evidence"] = evidence
        payload["events"] = tuple(
            StoryEvent(
                event_id=item["event_id"],
                scene_ids=tuple(item.get("scene_ids", [])),
                start_seconds=float(item["start_seconds"]),
                end_seconds=float(item["end_seconds"]),
                text=item["text"],
                importance=float(item["importance"]),
                kind=item.get("kind", "dialogue"),
            )
            for item in payload.get("events", [])
        )
        payload["continuity_notes"] = tuple(payload.get("continuity_notes", []))
        return cls(**payload)


class ExtractiveStoryAnalyzer:
    """Build deterministic story evidence from transcript + scene timing."""

    def analyze(
        self,
        transcript: TranscriptAnalysisManifest,
        scenes: SceneAnalysisManifest,
    ) -> EpisodeStoryManifest:
        if transcript.input_path != scenes.input_path:
            raise StoryAnalysisError("transcript and scene manifests reference different input files")
        if transcript.input_sha256 and scenes.input_sha256:
            if transcript.input_sha256 != scenes.input_sha256:
                raise StoryAnalysisError("transcript and scene fingerprints do not match")
        if transcript.transcript_status != "READY":
            raise StoryAnalysisError("transcript is not ready for story analysis")

        events: list[StoryEvent] = []
        for index, segment in enumerate(transcript.segments, start=1):
            scene_count = max(1, len(segment.scene_ids))
            duration = max(0.1, segment.end_seconds - segment.start_seconds)
            importance = min(
                1.0,
                0.25
                + min(0.35, len(segment.text) / 160.0)
                + min(0.20, len(segment.scene_ids) / 4.0)
                + (0.20 if scene_count == 1 and duration >= 2.0 else 0.0),
            )
            events.append(
                StoryEvent(
                    event_id=f"event_{index:04d}",
                    scene_ids=segment.scene_ids,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    text=segment.text,
                    importance=round(importance, 3),
                    kind="dialogue",
                )
            )

        keywords = self._keywords(transcript)
        characters = self._capitalized_entities(transcript)
        ending = events[-1].event_id if events else None
        notes = (
            "Extractive evidence only; semantic character/location resolution is not yet authoritative.",
        )

        return EpisodeStoryManifest(
            schema_version=1,
            episode_id=transcript.episode_id or scenes.episode_id,
            input_path=transcript.input_path,
            input_sha256=transcript.input_sha256 or scenes.input_sha256,
            source_transcript="transcript.json",
            source_scenes="scenes.json",
            method="extractive",
            evidence=StoryEvidence(
                characters=tuple(characters),
                locations=(),
                keywords=tuple(keywords),
            ),
            events=tuple(events),
            ending_event_id=ending,
            continuity_notes=notes,
        )

    @staticmethod
    def _keywords(transcript: TranscriptAnalysisManifest) -> list[str]:
        stop_words = {
            "the", "and", "that", "this", "with", "from", "your", "have", "what",
            "when", "where", "there", "they", "them", "then", "will", "just",
            "you", "for", "are", "was", "were", "into", "about", "not", "but",
        }
        counts: dict[str, int] = {}
        for segment in transcript.segments:
            for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", segment.text.lower()):
                if word in stop_words:
                    continue
                counts[word] = counts.get(word, 0) + 1
        return [
            word
            for word, _ in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:20]
        ]

    @staticmethod
    def _capitalized_entities(transcript: TranscriptAnalysisManifest) -> list[str]:
        counts: dict[str, int] = {}
        for segment in transcript.segments:
            for value in re.findall(r"\b[A-Z][a-z]{2,}\b", segment.text):
                if value.lower() in {"The", "This", "That", "What", "When", "Where"}:
                    continue
                counts[value] = counts.get(value, 0) + 1
        return [
            value
            for value, _ in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:20]
        ]
