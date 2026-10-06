from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .timeline import RenderError, TimelineManifest


class FFmpegRenderer:
    """Render a timeline with muted source audio and measured narration audio."""

    def __init__(
        self,
        *,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ) -> None:
        if width <= 0 or height <= 0 or fps <= 0:
            raise ValueError("render dimensions and fps must be positive")
        self.width = width
        self.height = height
        self.fps = fps

    def render(
        self,
        timeline: TimelineManifest,
        *,
        source_video: Path,
        narration_dir: Path,
        output_path: Path,
        subtitles: bool = True,
    ) -> Path:
        self._require_tools()
        if not source_video.is_file():
            raise RenderError(f"source video not found: {source_video}")
        if not timeline.clips:
            raise RenderError("timeline contains no video clips")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        subtitle_path = output_path.with_suffix(".srt")
        self._write_srt(timeline, subtitle_path)

        command = ["ffmpeg", "-v", "error", "-i", str(source_video)]
        for item in timeline.narration_audio:
            audio_path = narration_dir / item.audio
            if not audio_path.is_file():
                raise RenderError(f"narration audio not found: {audio_path}")
            command.extend(["-i", str(audio_path)])

        filters: list[str] = []
        video_labels: list[str] = []
        split_inputs = "".join(f"[src{index}]" for index in range(len(timeline.clips)))
        filters.append(
            f"[0:v]split={len(timeline.clips)}{split_inputs}"
        )

        for index, clip in enumerate(timeline.clips):
            label = f"v{index}"
            video_labels.append(f"[{label}]")
            filters.append(
                f"[src{index}]trim=start={clip.source_start_seconds:.3f}:end={clip.source_end_seconds:.3f},"
                f"setpts=PTS-STARTPTS,scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,fps={self.fps}[{label}]"
            )

        filters.append(
            "".join(video_labels)
            + f"concat=n={len(video_labels)}:v=1:a=0[vconcat]"
        )

        video_output = "[vconcat]"
        if subtitles:
            video_filter_path = _escape_filter_path(subtitle_path.resolve())
            filters.append(
                f"[vconcat]subtitles='{video_filter_path}':"
                "force_style='FontName=Arial,FontSize=18,Outline=2,Shadow=1,"
                "MarginV=40,Alignment=2'[vout]"
            )
            video_output = "[vout]"

        audio_labels: list[str] = []
        for index, event in enumerate(timeline.narration_audio, start=1):
            input_index = index
            label = f"a{index}"
            audio_labels.append(f"[{label}]")
            delay_ms = int(round(event.start_seconds * 1000))
            filters.append(
                f"[{input_index}:a]adelay={delay_ms}:all=1[{label}]"
            )

        if len(audio_labels) == 1:
            filters.append(f"{audio_labels[0]}anull[aout]")
        else:
            filters.append(
                "".join(audio_labels)
                + f"amix=inputs={len(audio_labels)}:duration=longest:dropout_transition=0[aout]"
            )

        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                video_output,
                "-map",
                "[aout]",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-movflags",
                "+faststart",
                "-y",
                str(output_path),
            ]
        )

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(180, int(timeline.total_duration_seconds * 10)),
            check=False,
        )
        if completed.returncode != 0:
            raise RenderError(
                f"ffmpeg render failed: "
                f"{completed.stderr.strip() or 'unknown error'}"
            )
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RenderError(f"ffmpeg did not create a usable output: {output_path}")
        return output_path

    @staticmethod
    def _write_srt(timeline: TimelineManifest, path: Path) -> None:
        lines: list[str] = []
        for index, item in enumerate(timeline.subtitles, start=1):
            lines.extend(
                [
                    str(index),
                    f"{_srt_time(item.start_seconds)} --> {_srt_time(item.end_seconds)}",
                    _clean_srt_text(item.text),
                    "",
                ]
            )
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _require_tools() -> None:
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise RenderError("ffmpeg and ffprobe are required for rendering")


def _srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _clean_srt_text(value: str) -> str:
    return " ".join(value.replace("\n", " ").split())


def _escape_filter_path(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\:").replace("'", "\\'")
