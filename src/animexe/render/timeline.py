from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..matching import SceneMatchManifest
from ..tts import TTSManifest


class RenderError(RuntimeError):
    """Raised when timeline construction or rendering prerequisites fail."""


@dataclass(frozen=True)
class TimelineClip:
    index: int
    segment_id: str
    scene_id: str
    source_start_seconds: float
    source_end_seconds: float
    duration_seconds: float
    timeline_start_seconds: float
    timeline_end_seconds: float
    narration_audio: str

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "segment_id": self.segment_id,
            "scene_id": self.scene_id,
            "source_start_seconds": self.source_start_seconds,
            "source_end_seconds": self.source_end_seconds,
            "duration_seconds": self.duration_seconds,
            "timeline_start_seconds": self.timeline_start_seconds,
            "timeline_end_seconds": self.timeline_end_seconds,
            "narration_audio": self.narration_audio,
        }


@dataclass(frozen=True)
class TimelineAudio:
    segment_id: str
    audio: str
    start_seconds: float
    duration_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "audio": self.audio,
            "start_seconds": self.start_seconds,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class TimelineSubtitle:
    segment_id: str
    text: str
    start_seconds: float
    end_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "text": self.text,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
        }


@dataclass(frozen=True)
class TimelineManifest:
    schema_version: int
    episode_id: str | None
    input_path: str
    input_sha256: str
    source_matching: str
    source_tts: str
    clips: tuple[TimelineClip, ...]
    narration_audio: tuple[TimelineAudio, ...]
    subtitles: tuple[TimelineSubtitle, ...]
    total_duration_seconds: float
    checkpoint: str = "timeline"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "input_path": self.input_path,
            "input_sha256": self.input_sha256,
            "source_matching": self.source_matching,
            "source_tts": self.source_tts,
            "clips": [clip.to_dict() for clip in self.clips],
            "narration_audio": [item.to_dict() for item in self.narration_audio],
            "subtitles": [item.to_dict() for item in self.subtitles],
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
    def read(cls, path: Path) -> "TimelineManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["clips"] = tuple(TimelineClip(**item) for item in payload.get("clips", []))
        payload["narration_audio"] = tuple(
            TimelineAudio(**item) for item in payload.get("narration_audio", [])
        )
        payload["subtitles"] = tuple(
            TimelineSubtitle(**item) for item in payload.get("subtitles", [])
        )
        return cls(**payload)


class TimelineBuilder:
    """Build an edit timeline from measured TTS audio and scene matches."""

    def build(
        self,
        matching: SceneMatchManifest,
        tts: TTSManifest,
        *,
        source_matching: str = "matching.json",
        source_tts: str = "tts.json",
    ) -> TimelineManifest:
        self._validate_inputs(matching, tts)
        tts_by_id = {segment.segment_id: segment for segment in tts.segments}
        clips_by_segment: dict[str, list] = {}
        for clip in matching.clips:
            clips_by_segment.setdefault(clip.segment_id, []).append(clip)

        timeline_clips: list[TimelineClip] = []
        audio_events: list[TimelineAudio] = []
        subtitles: list[TimelineSubtitle] = []
        cursor = 0.0

        for segment in tts.segments:
            segment_clips = clips_by_segment.get(segment.segment_id, [])
            if not segment_clips:
                raise RenderError(
                    f"matching manifest has no clips for TTS segment {segment.segment_id}"
                )

            segment_start = cursor
            for clip in segment_clips:
                start = cursor
                end = cursor + clip.duration_seconds
                timeline_clips.append(
                    TimelineClip(
                        index=len(timeline_clips) + 1,
                        segment_id=clip.segment_id,
                        scene_id=clip.scene_id,
                        source_start_seconds=clip.source_start_seconds,
                        source_end_seconds=clip.source_end_seconds,
                        duration_seconds=clip.duration_seconds,
                        timeline_start_seconds=round(start, 3),
                        timeline_end_seconds=round(end, 3),
                        narration_audio=clip.narration_audio,
                    )
                )
                cursor = end

            audio_events.append(
                TimelineAudio(
                    segment_id=segment.segment_id,
                    audio=segment.audio,
                    start_seconds=round(segment_start, 3),
                    duration_seconds=segment.duration_seconds,
                )
            )
            subtitles.append(
                TimelineSubtitle(
                    segment_id=segment.segment_id,
                    text=segment.text,
                    start_seconds=round(segment_start, 3),
                    end_seconds=round(segment_start + segment.duration_seconds, 3),
                )
            )

            matched_video = cursor - segment_start
            if matched_video + 0.15 < segment.duration_seconds:
                raise RenderError(
                    f"timeline video for {segment.segment_id} is "
                    f"{matched_video:.2f}s but narration audio is {segment.duration_seconds:.2f}s"
                )

        return TimelineManifest(
            schema_version=1,
            episode_id=matching.episode_id or tts.episode_id,
            input_path=matching.input_path,
            input_sha256=matching.input_sha256 or tts.input_sha256,
            source_matching=source_matching,
            source_tts=source_tts,
            clips=tuple(timeline_clips),
            narration_audio=tuple(audio_events),
            subtitles=tuple(subtitles),
            total_duration_seconds=round(cursor, 3),
        )

    @staticmethod
    def _validate_inputs(
        matching: SceneMatchManifest,
        tts: TTSManifest,
    ) -> None:
        if matching.input_path != tts.input_path:
            raise RenderError("matching and TTS manifests reference different inputs")
        if matching.input_sha256 and tts.input_sha256:
            if matching.input_sha256 != tts.input_sha256:
                raise RenderError("matching and TTS fingerprints do not match")
        if not matching.clips:
            raise RenderError("matching manifest contains no clips")
        if not tts.segments:
            raise RenderError("TTS manifest contains no audio segments")
