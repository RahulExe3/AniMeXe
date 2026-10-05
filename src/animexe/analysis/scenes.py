from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .manifest import EpisodeAnalysisManifest


class SceneDetectionError(RuntimeError):
    """Raised when scene detection or frame extraction cannot complete."""


@dataclass(frozen=True)
class SceneRecord:
    scene_id: str
    index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    representative_time_seconds: float
    representative_frame: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "index": self.index,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration_seconds": self.duration_seconds,
            "representative_time_seconds": self.representative_time_seconds,
            "representative_frame": self.representative_frame,
        }


@dataclass(frozen=True)
class SceneAnalysisManifest:
    """Scene index produced after technical inspection."""

    schema_version: int
    episode_id: str | None
    input_path: str
    detection_method: str
    threshold: float
    min_scene_duration_seconds: float
    detected_scenes: int
    frames_extracted: int
    scenes: tuple[SceneRecord, ...] = field(default_factory=tuple)
    checkpoint: str = "scenes"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "input_path": self.input_path,
            "detection_method": self.detection_method,
            "threshold": self.threshold,
            "min_scene_duration_seconds": self.min_scene_duration_seconds,
            "detected_scenes": self.detected_scenes,
            "frames_extracted": self.frames_extracted,
            "scenes": [scene.to_dict() for scene in self.scenes],
            "checkpoint": self.checkpoint,
        }

    def write(self, path: Path) -> None:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read(cls, path: Path) -> "SceneAnalysisManifest":
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        scenes = tuple(SceneRecord(**item) for item in payload.get("scenes", []))
        payload["scenes"] = scenes
        return cls(**payload)


class SceneIndexer:
    """Detect cuts and extract one compact representative frame per scene."""

    def __init__(
        self,
        *,
        ffmpeg_binary: str | None = None,
        threshold: float = 27.0,
        min_scene_duration_seconds: float = 0.5,
        frame_width: int = 640,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary or shutil.which("ffmpeg") or "ffmpeg"
        self.threshold = threshold
        self.min_scene_duration_seconds = min_scene_duration_seconds
        self.frame_width = frame_width

        if self.threshold <= 0:
            raise ValueError("scene threshold must be positive")
        if self.min_scene_duration_seconds <= 0:
            raise ValueError("minimum scene duration must be positive")
        if self.frame_width <= 0:
            raise ValueError("frame width must be positive")

    def index(
        self,
        input_path: Path,
        *,
        output_dir: Path,
        episode_manifest: EpisodeAnalysisManifest | None = None,
        episode_id: str | None = None,
        extract_frames: bool = True,
    ) -> SceneAnalysisManifest:
        path = input_path.expanduser().resolve()
        if not path.exists():
            raise SceneDetectionError(f"scene input does not exist: {path}")
        if not path.is_file():
            raise SceneDetectionError(f"scene input is not a file: {path}")

        if episode_manifest is not None:
            self._validate_manifest(path, episode_manifest)
            duration = episode_manifest.duration_seconds
        else:
            duration = None

        try:
            scene_list = self._detect(path)
        except FileNotFoundError as exc:
            raise SceneDetectionError(
                "scene detector is unavailable; install PySceneDetect and its OpenCV backend"
            ) from exc
        except Exception as exc:
            raise SceneDetectionError(f"scene detection failed: {exc}") from exc

        scenes = self._normalize_scenes(scene_list, duration)

        frame_root = output_dir / "frames"
        records: list[SceneRecord] = []
        for index, (start, end) in enumerate(scenes, start=1):
            duration_seconds = max(0.0, end - start)
            representative = start + (duration_seconds / 2.0)
            frame_path = None
            if extract_frames:
                frame_path = frame_root / f"scene_{index:04d}.jpg"
                self._extract_frame(path, representative, frame_path)

            records.append(
                SceneRecord(
                    scene_id=f"scene_{index:04d}",
                    index=index,
                    start_seconds=round(start, 3),
                    end_seconds=round(end, 3),
                    duration_seconds=round(duration_seconds, 3),
                    representative_time_seconds=round(representative, 3),
                    representative_frame=(
                        str(frame_path.relative_to(output_dir))
                        if frame_path is not None
                        else None
                    ),
                )
            )

        manifest = SceneAnalysisManifest(
            schema_version=1,
            episode_id=episode_id or (
                episode_manifest.episode_id if episode_manifest else None
            ),
            input_path=str(path),
            detection_method="pyscenedetect:ContentDetector",
            threshold=self.threshold,
            min_scene_duration_seconds=self.min_scene_duration_seconds,
            detected_scenes=len(records),
            frames_extracted=sum(
                scene.representative_frame is not None for scene in records
            ),
            scenes=tuple(records),
        )
        return manifest

    def _detect(self, path: Path) -> list[tuple[float, float]]:
        from scenedetect import ContentDetector, detect

        detected = detect(
            str(path),
            ContentDetector(
                threshold=self.threshold,
                min_scene_len=self.min_scene_duration_seconds,
            ),
            show_progress=False,
        )
        return [
            (float(start.get_seconds()), float(end.get_seconds()))
            for start, end in detected
        ]

    @staticmethod
    def _normalize_scenes(
        detected: list[tuple[float, float]],
        duration: float | None,
    ) -> list[tuple[float, float]]:
        cleaned = [
            (max(0.0, start), max(0.0, end))
            for start, end in detected
            if end > start
        ]
        cleaned.sort(key=lambda item: item[0])

        if not cleaned and duration and duration > 0:
            return [(0.0, duration)]

        if cleaned and duration and duration > cleaned[-1][1]:
            last_end = duration
            cleaned[-1] = (cleaned[-1][0], last_end)

        return cleaned

    def _extract_frame(self, input_path: Path, timestamp: float, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        safe_timestamp = max(0.0, timestamp)
        try:
            subprocess.run(
                [
                    self.ffmpeg_binary,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{safe_timestamp:.3f}",
                    "-i",
                    str(input_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale={self.frame_width}:-2",
                    "-q:v",
                    "3",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError as exc:
            raise SceneDetectionError(
                "ffmpeg was not found; install FFmpeg and ensure ffmpeg is on PATH"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SceneDetectionError("ffmpeg timed out while extracting a scene frame") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip()
            raise SceneDetectionError(
                "ffmpeg frame extraction failed"
                + (f": {detail}" if detail else "")
            ) from exc
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise SceneDetectionError(
                f"ffmpeg did not produce a representative frame: {output_path}"
            )

    @staticmethod
    def _validate_manifest(
        input_path: Path,
        manifest: EpisodeAnalysisManifest,
    ) -> None:
        manifest_path = Path(manifest.input_path).expanduser().resolve()
        if manifest_path != input_path:
            raise SceneDetectionError(
                "episode analysis manifest belongs to a different input file"
            )
        if manifest.duration_seconds is not None and manifest.duration_seconds <= 0:
            raise SceneDetectionError(
                "episode analysis manifest has an invalid duration"
            )
