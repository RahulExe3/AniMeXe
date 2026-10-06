from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..editing import EditPlanManifest
from .timeline import RenderError


class VisualCutError(RenderError):
    """Raised when a narration-free visual cut cannot be rendered."""


class VisualCutRenderer:
    """Render selected episode clips in one FFmpeg filter pass, with no audio."""

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

        # The old implementation created one independent [0:v] trim/scale/fps
        # branch per clip and then concatenated all branches. With many detected
        # scenes that makes FFmpeg repeatedly process the same source frames.
        # Select all required intervals in one pass instead, then normalize the
        # already-selected frames once. This preserves chronological clip order
        # and keeps rendering close to a single decode + encode operation.
        clips = sorted(plan.clips, key=lambda clip: (clip.source_start_seconds, clip.source_end_seconds))
        previous_end = -1.0
        intervals: list[str] = []
        for clip in clips:
            start = float(clip.source_start_seconds)
            end = float(clip.source_end_seconds)
            if end <= start:
                raise VisualCutError(f"invalid clip interval: {start:.3f}-{end:.3f}")
            if start < previous_end - 0.001:
                raise VisualCutError("visual-cut clips overlap; cannot safely render as a single-pass selection")
            intervals.append(f"between(t,{start:.3f},{end:.3f})")
            previous_end = end

        select_expression = "+".join(intervals)
        video_filter = (
            f"select='{select_expression}',"
            "setpts=N/FRAME_RATE/TB,"
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={self.fps}"
        )

        command = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source_video),
            "-vf",
            video_filter,
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-threads",
            "0",
            "-y",
            str(output_path),
        ]

        # Keep a generous safety limit, but do not make the timeout scale
        # linearly with the requested output duration. The renderer now performs
        # one source decode and one encode rather than N independent branches.
        timeout_seconds = max(300, min(900, int(plan.total_duration_seconds * 5)))
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
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
