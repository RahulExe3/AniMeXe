from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import EpisodeAnalysisManifest, StreamManifest


class InspectionError(RuntimeError):
    """Raised when an episode cannot be inspected reliably."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_version(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [executable, "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    first_line = result.stdout.strip().splitlines()
    return first_line[0].strip() if first_line else None


class EpisodeInspector:
    """Run ffprobe and normalize one local episode into an analysis manifest."""

    def __init__(self, ffprobe_binary: str | None = None) -> None:
        self.ffprobe_binary = ffprobe_binary or shutil.which("ffprobe") or "ffprobe"

    def inspect(
        self,
        input_path: Path,
        *,
        episode_id: str | None = None,
        hash_input: bool = True,
    ) -> EpisodeAnalysisManifest:
        path = input_path.expanduser().resolve()
        if not path.exists():
            raise InspectionError(f"episode input does not exist: {path}")
        if not path.is_file():
            raise InspectionError(f"episode input is not a file: {path}")

        stat = path.stat()
        try:
            probe = self._run_ffprobe(path)
        except FileNotFoundError as exc:
            raise InspectionError(
                "ffprobe was not found; install FFmpeg and ensure ffprobe is on PATH"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise InspectionError("ffprobe timed out while inspecting the episode") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip()
            raise InspectionError(
                f"ffprobe failed for {path.name}" + (f": {detail}" if detail else "")
            ) from exc

        format_data = probe.get("format") or {}
        streams = tuple(
            self._normalize_stream(stream)
            for stream in probe.get("streams", [])
            if isinstance(stream, dict)
        )

        video_streams = sum(item.codec_type == "video" for item in streams)
        audio_streams = sum(item.codec_type == "audio" for item in streams)
        subtitle_streams = sum(item.codec_type == "subtitle" for item in streams)

        return EpisodeAnalysisManifest(
            schema_version=1,
            episode_id=episode_id,
            input_path=str(path),
            input_size_bytes=stat.st_size,
            input_sha256=_file_sha256(path) if hash_input else "",
            inspected_at=_utc_now(),
            ffprobe_version=_probe_version(self.ffprobe_binary),
            format_name=format_data.get("format_name"),
            format_long_name=format_data.get("format_long_name"),
            duration_seconds=_optional_float(format_data.get("duration")),
            start_time_seconds=_optional_float(format_data.get("start_time")),
            bit_rate=_optional_int(format_data.get("bit_rate")),
            streams=streams,
            video_streams=video_streams,
            audio_streams=audio_streams,
            subtitle_streams=subtitle_streams,
            checkpoint="inspected",
        )

    def _run_ffprobe(self, path: Path) -> dict[str, Any]:
        result = subprocess.run(
            [
                self.ffprobe_binary,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        payload = json.loads(result.stdout or "{}")
        if not isinstance(payload, dict):
            raise InspectionError("ffprobe returned an invalid JSON object")
        return payload

    @staticmethod
    def _normalize_stream(stream: dict[str, Any]) -> StreamManifest:
        tags = stream.get("tags") or {}
        return StreamManifest(
            index=int(stream.get("index", -1)),
            codec_type=str(stream.get("codec_type", "unknown")),
            codec_name=stream.get("codec_name"),
            codec_long_name=stream.get("codec_long_name"),
            width=_optional_int(stream.get("width")),
            height=_optional_int(stream.get("height")),
            avg_frame_rate=stream.get("avg_frame_rate"),
            r_frame_rate=stream.get("r_frame_rate"),
            duration=_optional_float(stream.get("duration")),
            channels=_optional_int(stream.get("channels")),
            sample_rate=_optional_int(stream.get("sample_rate")),
            language=tags.get("language"),
            title=tags.get("title"),
        )
