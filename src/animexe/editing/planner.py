from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..analysis.scenes import SceneAnalysisManifest, SceneRecord
from ..analysis.story import EpisodeStoryManifest, StoryEvent, StoryEvidence


class EditPlanError(RuntimeError):
    """Raised when a semantic visual edit plan cannot be built."""


@dataclass(frozen=True)
class PlannedClip:
    clip_id: str
    event_id: str
    scene_id: str
    source_start_seconds: float
    source_end_seconds: float
    duration_seconds: float
    importance: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "event_id": self.event_id,
            "scene_id": self.scene_id,
            "source_start_seconds": self.source_start_seconds,
            "source_end_seconds": self.source_end_seconds,
            "duration_seconds": self.duration_seconds,
            "importance": self.importance,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EditPlanManifest:
    schema_version: int
    episode_id: str | None
    input_path: str
    input_sha256: str
    source_story: str
    source_scenes: str
    target_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    max_clip_duration_seconds: float
    selected_event_ids: tuple[str, ...] = field(default_factory=tuple)
    clips: tuple[PlannedClip, ...] = field(default_factory=tuple)
    total_duration_seconds: float = 0.0
    checkpoint: str = "edit_plan"

    @property
    def scene_ids(self) -> tuple[str, ...]:
        return tuple(clip.scene_id for clip in self.clips)

    @property
    def event_ids(self) -> tuple[str, ...]:
        return tuple(self.selected_event_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "input_path": self.input_path,
            "input_sha256": self.input_sha256,
            "source_story": self.source_story,
            "source_scenes": self.source_scenes,
            "target_duration_seconds": self.target_duration_seconds,
            "min_duration_seconds": self.min_duration_seconds,
            "max_duration_seconds": self.max_duration_seconds,
            "max_clip_duration_seconds": self.max_clip_duration_seconds,
            "selected_event_ids": list(self.selected_event_ids),
            "clips": [clip.to_dict() for clip in self.clips],
            "total_duration_seconds": self.total_duration_seconds,
            "checkpoint": self.checkpoint,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read(cls, path: Path) -> "EditPlanManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["selected_event_ids"] = tuple(payload.get("selected_event_ids", []))
        payload["clips"] = tuple(
            PlannedClip(
                clip_id=item["clip_id"],
                event_id=item["event_id"],
                scene_id=item["scene_id"],
                source_start_seconds=float(item["source_start_seconds"]),
                source_end_seconds=float(item["source_end_seconds"]),
                duration_seconds=float(item["duration_seconds"]),
                importance=float(item["importance"]),
                reason=item.get("reason", ""),
            )
            for item in payload.get("clips", [])
        )
        payload["total_duration_seconds"] = float(
            payload.get(
                "total_duration_seconds",
                sum(clip.duration_seconds for clip in payload["clips"]),
            )
        )
        return cls(**payload)


class EditPlanner:
    """Choose a chronological set of important scenes before narration is generated."""

    def __init__(
        self,
        *,
        target_duration_seconds: float = 120.0,
        min_duration_seconds: float = 105.0,
        max_duration_seconds: float = 135.0,
        max_clip_duration_seconds: float = 8.0,
    ) -> None:
        if min_duration_seconds <= 0 or target_duration_seconds <= 0 or max_duration_seconds <= 0:
            raise ValueError("edit-plan duration bounds must be positive")
        if not min_duration_seconds <= target_duration_seconds <= max_duration_seconds:
            raise ValueError("target duration must be within edit-plan duration bounds")
        if max_clip_duration_seconds <= 0:
            raise ValueError("max_clip_duration_seconds must be positive")
        self.target_duration_seconds = target_duration_seconds
        self.min_duration_seconds = min_duration_seconds
        self.max_duration_seconds = max_duration_seconds
        self.max_clip_duration_seconds = max_clip_duration_seconds

    def plan(
        self,
        story: EpisodeStoryManifest,
        scenes: SceneAnalysisManifest,
        *,
        source_story: str = "story.json",
        source_scenes: str = "scenes.json",
    ) -> EditPlanManifest:
        self._validate_inputs(story, scenes)
        scene_by_id = {scene.scene_id: scene for scene in scenes.scenes}
        if not story.events:
            raise EditPlanError("story manifest contains no events")
        if not scene_by_id:
            raise EditPlanError("scene manifest contains no scenes")

        events = sorted(story.events, key=lambda event: (event.start_seconds, event.event_id))
        ending_id = story.ending_event_id or events[-1].event_id
        event_by_id = {event.event_id: event for event in events}

        mandatory: list[StoryEvent] = []
        for event_id in (events[0].event_id, ending_id):
            event = event_by_id.get(event_id)
            if event is not None and event not in mandatory:
                mandatory.append(event)

        ranked = sorted(
            events,
            key=lambda event: (
                -self._event_score(event, ending_id=ending_id),
                event.start_seconds,
                event.event_id,
            ),
        )

        selected_events: list[StoryEvent] = []
        selected_scene_ids: set[str] = set()
        selected_clips: list[PlannedClip] = []

        def add_event(event: StoryEvent) -> None:
            if event.event_id in {item.event_id for item in selected_events}:
                return
            added = False
            for scene_id in event.scene_ids:
                scene = scene_by_id.get(scene_id)
                if scene is None or scene.scene_id in selected_scene_ids:
                    continue
                remaining = self.target_duration_seconds - sum(
                    clip.duration_seconds for clip in selected_clips
                )
                if remaining <= 0.05:
                    break
                duration = min(
                    scene.duration_seconds,
                    self.max_clip_duration_seconds,
                    remaining,
                )
                if duration <= 0.05:
                    continue
                start, end = self._window(scene, duration)
                selected_scene_ids.add(scene.scene_id)
                selected_clips.append(
                    PlannedClip(
                        clip_id=f"clip_{len(selected_clips) + 1:03d}",
                        event_id=event.event_id,
                        scene_id=scene.scene_id,
                        source_start_seconds=round(start, 3),
                        source_end_seconds=round(end, 3),
                        duration_seconds=round(end - start, 3),
                        importance=round(event.importance, 3),
                        reason=event.kind or "story_event",
                    )
                )
                added = True
            if added:
                selected_events.append(event)

        for event in mandatory:
            add_event(event)
        for event in ranked:
            if sum(clip.duration_seconds for clip in selected_clips) >= self.target_duration_seconds - 0.05:
                break
            add_event(event)

        selected_clips.sort(
            key=lambda clip: (
                clip.source_start_seconds,
                clip.source_end_seconds,
                clip.clip_id,
            )
        )
        selected_clips = [
            PlannedClip(
                clip_id=f"clip_{index:03d}",
                event_id=clip.event_id,
                scene_id=clip.scene_id,
                source_start_seconds=clip.source_start_seconds,
                source_end_seconds=clip.source_end_seconds,
                duration_seconds=clip.duration_seconds,
                importance=clip.importance,
                reason=clip.reason,
            )
            for index, clip in enumerate(selected_clips, start=1)
        ]

        total = round(sum(clip.duration_seconds for clip in selected_clips), 3)
        if total <= 0:
            raise EditPlanError("edit plan selected no usable video")

        # Never exceed the configured hard maximum. The planner already caps at target,
        # but this also protects hand-edited configuration from producing oversized cuts.
        if total > self.max_duration_seconds:
            overflow = total - self.max_duration_seconds
            trimmed: list[PlannedClip] = []
            remaining_overflow = overflow
            for clip in reversed(selected_clips):
                if remaining_overflow <= 0.001:
                    trimmed.append(clip)
                    continue
                new_duration = max(0.05, clip.duration_seconds - remaining_overflow)
                end = clip.source_start_seconds + new_duration
                trimmed.append(
                    PlannedClip(
                        clip_id=clip.clip_id,
                        event_id=clip.event_id,
                        scene_id=clip.scene_id,
                        source_start_seconds=clip.source_start_seconds,
                        source_end_seconds=round(end, 3),
                        duration_seconds=round(new_duration, 3),
                        importance=clip.importance,
                        reason=clip.reason,
                    )
                )
                remaining_overflow -= clip.duration_seconds - new_duration
            selected_clips = list(reversed(trimmed))
            total = round(sum(clip.duration_seconds for clip in selected_clips), 3)

        return EditPlanManifest(
            schema_version=1,
            episode_id=story.episode_id or scenes.episode_id,
            input_path=story.input_path,
            input_sha256=story.input_sha256 or scenes.input_sha256,
            source_story=source_story,
            source_scenes=source_scenes,
            target_duration_seconds=self.target_duration_seconds,
            min_duration_seconds=self.min_duration_seconds,
            max_duration_seconds=self.max_duration_seconds,
            max_clip_duration_seconds=self.max_clip_duration_seconds,
            selected_event_ids=tuple(event.event_id for event in selected_events),
            clips=tuple(selected_clips),
            total_duration_seconds=total,
        )


    def plan_visual_only(
        self,
        scenes: SceneAnalysisManifest,
        *,
        source_story: str = "visual-only",
        source_scenes: str = "scenes.json",
    ) -> EditPlanManifest:
        """Build a deterministic visual-only cut directly from detected scenes."""
        if not scenes.scenes:
            raise EditPlanError("scene manifest contains no scenes")

        # Give every detected scene a neutral semantic score and let the normal
        # planner preserve first/last coverage while filling the requested duration.
        events = tuple(
            StoryEvent(
                event_id=f"visual_{scene.index:04d}",
                scene_ids=(scene.scene_id,),
                start_seconds=scene.start_seconds,
                end_seconds=scene.end_seconds,
                text=f"Visual scene {scene.index}",
                importance=0.5,
                kind="visual_scene",
            )
            for scene in scenes.scenes
        )
        story = EpisodeStoryManifest(
            schema_version=2,
            episode_id=scenes.episode_id,
            input_path=scenes.input_path,
            input_sha256=scenes.input_sha256,
            source_transcript="visual-only",
            source_scenes=source_scenes,
            method="visual_only",
            evidence=StoryEvidence(),
            events=events,
            ending_event_id=events[-1].event_id,
        )
        return self.plan(
            story,
            scenes,
            source_story=source_story,
            source_scenes=source_scenes,
        )

    @staticmethod
    def _validate_inputs(story: EpisodeStoryManifest, scenes: SceneAnalysisManifest) -> None:
        if story.input_path != scenes.input_path:
            raise EditPlanError("story and scene manifests reference different input files")
        if story.input_sha256 and scenes.input_sha256 and story.input_sha256 != scenes.input_sha256:
            raise EditPlanError("story and scene fingerprints do not match")

    @staticmethod
    def _event_score(event: StoryEvent, *, ending_id: str) -> float:
        score = max(0.0, min(1.0, event.importance))
        kind = event.kind.lower()
        if event.event_id == ending_id:
            score += 0.25
        if any(token in kind for token in ("reveal", "turn", "conflict", "action", "ending", "climax")):
            score += 0.10
        return score

    @staticmethod
    def _window(scene: SceneRecord, duration: float) -> tuple[float, float]:
        duration = min(duration, scene.duration_seconds)
        if duration >= scene.duration_seconds - 0.001:
            return scene.start_seconds, scene.end_seconds
        center = scene.representative_time_seconds
        start = max(scene.start_seconds, center - duration / 2.0)
        end = min(scene.end_seconds, start + duration)
        if end - start < duration:
            start = max(scene.start_seconds, end - duration)
        return start, end
