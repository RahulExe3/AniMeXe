from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class StreamManifest:
    index: int
    codec_type: str
    codec_name: str | None = None
    codec_long_name: str | None = None
    width: int | None = None
    height: int | None = None
    avg_frame_rate: str | None = None
    r_frame_rate: str | None = None
    duration: float | None = None
    channels: int | None = None
    sample_rate: int | None = None
    language: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class EpisodeAnalysisManifest:
    """Stable checkpoint produced after technical episode inspection."""

    schema_version: int
    episode_id: str | None
    input_path: str
    input_size_bytes: int
    input_sha256: str
    inspected_at: str
    ffprobe_version: str | None
    format_name: str | None
    format_long_name: str | None
    duration_seconds: float | None
    start_time_seconds: float | None
    bit_rate: int | None
    streams: tuple[StreamManifest, ...] = field(default_factory=tuple)
    video_streams: int = 0
    audio_streams: int = 0
    subtitle_streams: int = 0
    checkpoint: str = "inspected"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EpisodeAnalysisManifest":
        streams = tuple(StreamManifest(**item) for item in payload.get("streams", []))
        values = dict(payload)
        values["streams"] = streams
        return cls(**values)

    @classmethod
    def read(cls, path: Path) -> "EpisodeAnalysisManifest":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
