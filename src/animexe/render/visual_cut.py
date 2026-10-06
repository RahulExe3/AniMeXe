from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..editing import EditPlanManifest, PlannedClip
from .timeline import RenderError


class VisualCutError(RenderError):
    """Raised when a narration-free visual cut cannot be rendered."""


class VisualCutRenderer:
    """Render only the selected episode clips, with no audio track."""

    def __init__(self, *, width: int = 1920, height: int = 1080, fps: int = 30) -> None:
        if width <= 0 or height <= 0 or fps <= 0:
            raise ValueError("render dimensions and fps must be positive")
        self.width = width
        self.height = height
        self.fps = fps

    def render(
        self,
        source_video: Path,
        plan: EditPlanManifest,
        *,
        output_path: Path,
    ) -> Path:
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise VisualCutError("ffmpeg and ffprobe are required for a visual cut")
        if not source_video.is_file():
            raise VisualCutError(f"source video not found: {source_video}")
        if not plan.clips:
            raise VisualCutError("edit plan contains no clips")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        filters: list[str] = []
        labels: list[str] = []
        for index, clip in enumerate(plan.clips):
            label = f"v{index}"
            labels.append(f"[{label}]")
            filters.append(
                f"[0:v]trim=start={clip.source_start_seconds:.3f}:end={clip.source_end_seconds:.3f},"
                f"setpts=PTS-STARTPTS,scale={self.width}:{self.height}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,fps={self.fps}[{label}]"
            )

        filters.append(
            "".join(labels)
            + f"concat=n={len(labels)}:v=1:a=0[vout]"
        )

        command = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source_video),
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(180, int(plan.total_duration_seconds * 10)),
            check=False,
        )
        if completed.returncode != 0:
            raise VisualCutError(
                "ffmpeg visual-cut render failed: "
                + (completed.stderr.strip() or "unknown error")
            )
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise VisualCutError(f"ffmpeg did not create a usable visual cut: {output_path}")

        self._validate_output(output_path)
        return output_path

    @staticmethod
    def _validate_output(path: Path) -> None:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise VisualCutError(
                "ffprobe could not validate visual cut: "
                + (completed.stderr.strip() or "unknown error")
            )
        try:
            payload = json.loads(completed.stdout)
            streams = payload.get("streams", [])
            duration = float((payload.get("format") or {}).get("duration") or 0)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise VisualCutError("ffprobe returned invalid visual-cut metadata") from exc

        kinds = {
            stream.get("codec_type")
            for stream in streams
            if isinstance(stream, dict)
        }
        if "video" not in kinds:
            raise VisualCutError("visual cut has no video stream")
        if "audio" in kinds:
            raise VisualCutError("visual cut unexpectedly contains an audio stream")
        if duration <= 0:
            raise VisualCutError("visual cut has an invalid duration")


__all__ = ["VisualCutError", "VisualCutRenderer"]
