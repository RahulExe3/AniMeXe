from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..analysis.scenes import SceneAnalysisManifest, SceneRecord
from ..tts import TTSManifest


class MatchError(RuntimeError):
    """Raised when narration-to-scene matching cannot be completed."""


@dataclass(frozen=True)
class NarrationClip:
    segment_id: str
    narration_audio: str
    scene_id: str
    source_start_seconds: float
    source_end_seconds: float
    duration_seconds: float
    score: float
    reused: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "narration_audio": self.narration_audio,
            "scene_id": self.scene_id,
            "source_start_seconds": self.source_start_seconds,
            "source_end_seconds": self.source_end_seconds,
            "duration_seconds": self.duration_seconds,
            "score": self.score,
            "reused": self.reused,
        }


@dataclass(frozen=True)
class SceneMatchManifest:
    schema_version: int
    episode_id: str | None
    input_path: str
    input_sha256: str
    source_scenes: str
    source_tts: str
    clips: tuple[NarrationClip, ...]
    total_narration_duration_seconds: float
    source_edit_plan: str | None = None
    checkpoint: str = "matching"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "input_path": self.input_path,
            "input_sha256": self.input_sha256,
            "source_scenes": self.source_scenes,
            "source_tts": self.source_tts,
            "clips": [clip.to_dict() for clip in self.clips],
            "total_narration_duration_seconds": self.total_narration_duration_seconds,
            "source_edit_plan": self.source_edit_plan,
            "checkpoint": self.checkpoint,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read(cls, path: Path) -> "SceneMatchManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["clips"] = tuple(
            NarrationClip(
                segment_id=item["segment_id"],
                narration_audio=item["narration_audio"],
                scene_id=item["scene_id"],
                source_start_seconds=float(item["source_start_seconds"]),
                source_end_seconds=float(item["source_end_seconds"]),
                duration_seconds=float(item["duration_seconds"]),
                score=float(item["score"]),
                reused=bool(item.get("reused", False)),
            )
            for item in payload.get("clips", [])
        )
        return cls(**payload)


class SceneMatcher:
    """Convert script-linked scenes plus measured TTS durations into edit-ready clips."""

    def __init__(
        self,
        *,
        max_clip_duration: float = 8.0,
        allow_reuse: bool = True,
    ) -> None:
        if max_clip_duration <= 0:
            raise ValueError("max_clip_duration must be positive")
        self.max_clip_duration = max_clip_duration
        self.allow_reuse = allow_reuse

    def match(
        self,
        scenes: SceneAnalysisManifest,
        tts: TTSManifest,
        *,
        edit_plan: EditPlanManifest | None = None,
        source_scenes: str = "scenes.json",
        source_tts: str = "tts.json",
        source_edit_plan: str | None = None,
    ) -> SceneMatchManifest:
        self._validate_inputs(scenes, tts, edit_plan=edit_plan)
        scene_by_id = {scene.scene_id: scene for scene in scenes.scenes}
        plan_windows = (
            {
                clip.scene_id: (
                    clip.source_start_seconds,
                    clip.source_end_seconds,
                )
                for clip in edit_plan.clips
            }
            if edit_plan is not None
            else {}
        )
        allowed_scene_ids = set(plan_windows)
        scene_order = {scene.scene_id: scene.index for scene in scenes.scenes}
        used: set[str] = set()
        clips: list[NarrationClip] = []

        for audio in tts.segments:
            needed = audio.duration_seconds
            candidate_ids = [
                scene_id
                for scene_id in audio.scene_ids
                if not allowed_scene_ids or scene_id in allowed_scene_ids
            ]
            if not candidate_ids:
                candidate_ids = [
                    scene.scene_id
                    for scene in scenes.scenes
                    if (not allowed_scene_ids or scene.scene_id in allowed_scene_ids)
                    and (scene.scene_id not in used or self.allow_reuse)
                ]

            explicit = [
                scene_by_id[scene_id]
                for scene_id in candidate_ids
                if scene_id in scene_by_id
            ]
            ordered = self._expand_candidates(
                explicit,
                scenes.scenes,
                used=used,
                allow_reuse=self.allow_reuse,
                allowed_scene_ids=allowed_scene_ids or None,
            )

            if not ordered:
                raise MatchError(
                    f"no usable scenes available for narration segment {audio.segment_id}"
                )

            remaining = needed
            for scene, is_explicit in ordered:
                if remaining <= 0.01:
                    break
                reused = scene.scene_id in used
                if reused and not self.allow_reuse:
                    continue

                available_duration = (
                    plan_windows.get(scene.scene_id, (scene.start_seconds, scene.end_seconds))[1]
                    - plan_windows.get(scene.scene_id, (scene.start_seconds, scene.end_seconds))[0]
                )
                clip_duration = min(
                    remaining,
                    self.max_clip_duration,
                    max(0.05, available_duration),
                )
                bounds = plan_windows.get(scene.scene_id)
                start, end = self._window(scene, clip_duration, bounds=bounds)
                actual = end - start
                if actual <= 0.04:
                    continue

                explicit_bonus = 0.5 if is_explicit else 0.0
                fresh_bonus = 0.35 if not reused else 0.0
                duration_fit = min(1.0, actual / max(0.1, needed))
                score = round(
                    max(0.0, min(1.0, 0.15 + explicit_bonus + fresh_bonus + 0.5 * duration_fit)),
                    3,
                )

                clips.append(
                    NarrationClip(
                        segment_id=audio.segment_id,
                        narration_audio=audio.audio,
                        scene_id=scene.scene_id,
                        source_start_seconds=round(start, 3),
                        source_end_seconds=round(end, 3),
                        duration_seconds=round(actual, 3),
                        score=score,
                        reused=reused,
                    )
                )
                used.add(scene.scene_id)
                remaining -= actual

            if remaining > 0.15:
                raise MatchError(
                    f"narration segment {audio.segment_id} needs "
                    f"{needed:.2f}s but only {needed - remaining:.2f}s were matched"
                )

        return SceneMatchManifest(
            schema_version=1,
            episode_id=tts.episode_id or scenes.episode_id,
            input_path=tts.input_path,
            input_sha256=tts.input_sha256 or scenes.input_sha256,
            source_scenes=source_scenes,
            source_tts=source_tts,
            clips=tuple(clips),
            total_narration_duration_seconds=round(tts.total_duration_seconds, 3),
            source_edit_plan=source_edit_plan,
        )

    @staticmethod
    def _validate_inputs(
        scenes: SceneAnalysisManifest,
        tts: TTSManifest,
        *,
        edit_plan: EditPlanManifest | None = None,
    ) -> None:
        if scenes.input_path != tts.input_path:
            raise MatchError("scene and TTS manifests reference different input files")
        if scenes.input_sha256 and tts.input_sha256:
            if scenes.input_sha256 != tts.input_sha256:
                raise MatchError("scene and TTS fingerprints do not match")
        if not scenes.scenes:
            raise MatchError("scene manifest contains no scenes")
        if not tts.segments:
            raise MatchError("TTS manifest contains no audio segments")
        if edit_plan is not None:
            if edit_plan.input_path != scenes.input_path:
                raise MatchError("visual edit plan and scene manifest reference different inputs")
            if edit_plan.input_sha256 and scenes.input_sha256 and edit_plan.input_sha256 != scenes.input_sha256:
                raise MatchError("visual edit plan and scene fingerprints do not match")
            if not edit_plan.clips:
                raise MatchError("visual edit plan contains no clips")

    @staticmethod
    def _expand_candidates(
        explicit: list[SceneRecord],
        all_scenes: tuple[SceneRecord, ...] | list[SceneRecord],
        *,
        used: set[str],
        allow_reuse: bool,
        allowed_scene_ids: set[str] | None = None,
    ) -> list[tuple[SceneRecord, bool]]:
        all_items = [
            scene
            for scene in all_scenes
            if not allowed_scene_ids or scene.scene_id in allowed_scene_ids
        ]
        result: list[tuple[SceneRecord, bool]] = []
        seen: set[str] = set()

        for scene in sorted(explicit, key=lambda value: value.index):
            if scene.scene_id in seen:
                continue
            seen.add(scene.scene_id)
            if not allow_reuse and scene.scene_id in used:
                continue
            result.append((scene, True))

        if not explicit:
            anchor_indices = [scene.index for scene in all_items]
        else:
            anchor_indices = [scene.index for scene in explicit]

        if anchor_indices:
            center = sum(anchor_indices) / len(anchor_indices)
            extras = sorted(
                (
                    scene
                    for scene in all_items
                    if scene.scene_id not in seen
                    and (allow_reuse or scene.scene_id not in used)
                ),
                key=lambda scene: (abs(scene.index - center), scene.index),
            )
            result.extend((scene, False) for scene in extras)

        return result

    @staticmethod
    def _window(
        scene: SceneRecord,
        duration: float,
        *,
        bounds: tuple[float, float] | None = None,
    ) -> tuple[float, float]:
        lower, upper = bounds or (scene.start_seconds, scene.end_seconds)
        duration = min(duration, upper - lower)
        if duration >= upper - lower - 0.001:
            return lower, upper
        center = min(max(scene.representative_time_seconds, lower), upper)
        start = max(lower, center - duration / 2.0)
        end = min(upper, start + duration)
        if end - start < duration:
            start = max(lower, end - duration)
        return start, end
