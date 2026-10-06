from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .manifest import EpisodeAnalysisManifest
from .scenes import SceneAnalysisManifest


class TranscriptError(RuntimeError):
    """Raised when transcript extraction or parsing fails."""


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    scene_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "text": self.text,
            "scene_ids": list(self.scene_ids),
        }


@dataclass(frozen=True)
class TranscriptAnalysisManifest:
    schema_version: int
    episode_id: str | None
    input_path: str
    input_sha256: str
    source: str
    language: str | None
    subtitle_stream_index: int | None
    transcript_status: str
    segments: tuple[TranscriptSegment, ...] = field(default_factory=tuple)
    checkpoint: str = "transcript"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "input_path": self.input_path,
            "input_sha256": self.input_sha256,
            "source": self.source,
            "language": self.language,
            "subtitle_stream_index": self.subtitle_stream_index,
            "transcript_status": self.transcript_status,
            "segments": [segment.to_dict() for segment in self.segments],
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
    def read(cls, path: Path) -> "TranscriptAnalysisManifest":
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["segments"] = tuple(
            TranscriptSegment(
                segment_id=item["segment_id"],
                start_seconds=float(item["start_seconds"]),
                end_seconds=float(item["end_seconds"]),
                text=item["text"],
                scene_ids=tuple(item.get("scene_ids", [])),
            )
            for item in payload.get("segments", [])
        )
        return cls(**payload)


class SubtitleTranscriptExtractor:
    """Extract timed embedded subtitles and align them to detected scenes."""

    def __init__(
        self,
        *,
        ffmpeg_binary: str | None = None,
        preferred_languages: tuple[str, ...] = ("eng", "en", "hin", "hi"),
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary or shutil.which("ffmpeg") or "ffmpeg"
        self.preferred_languages = tuple(
            value.lower() for value in preferred_languages if value.strip()
        )

    def extract(
        self,
        input_path: Path,
        *,
        output_dir: Path,
        episode_manifest: EpisodeAnalysisManifest,
        scene_manifest: SceneAnalysisManifest,
        episode_id: str | None = None,
    ) -> TranscriptAnalysisManifest:
        path = input_path.expanduser().resolve()
        self._validate_inputs(path, episode_manifest, scene_manifest)

        stream = self._select_subtitle_stream(episode_manifest)
        if stream is None:
            raise TranscriptError(
                "no embedded text subtitle stream is available; install/configure "
                "an ASR backend for audio transcription"
            )

        subtitle_path = output_dir / "source.srt"
        self._extract_subtitle(path, stream.index, subtitle_path)
        segments = self._parse_srt(subtitle_path.read_text(encoding="utf-8-sig"))
        if not segments:
            raise TranscriptError("embedded subtitle stream produced no timed captions")

        aligned = tuple(
            TranscriptSegment(
                segment_id=f"segment_{index:04d}",
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                text=text,
                scene_ids=self._scene_ids_for_interval(
                    start,
                    end,
                    scene_manifest,
                ),
            )
            for index, (start, end, text) in enumerate(segments, start=1)
        )

        return TranscriptAnalysisManifest(
            schema_version=1,
            episode_id=episode_id or episode_manifest.episode_id,
            input_path=str(path),
            input_sha256=episode_manifest.input_sha256,
            source="embedded_subtitle",
            language=stream.language,
            subtitle_stream_index=stream.index,
            transcript_status="READY",
            segments=aligned,
        )

    def _select_subtitle_stream(
        self,
        manifest: EpisodeAnalysisManifest,
    ):
        streams = [stream for stream in manifest.streams if stream.codec_type == "subtitle"]
        if not streams:
            return None

        preferred = self.preferred_languages
        for wanted in preferred:
            for stream in streams:
                if (stream.language or "").lower() == wanted:
                    return stream
        for stream in streams:
            if (stream.language or "").lower().startswith("en"):
                return stream
        return streams[0]

    def _extract_subtitle(
        self,
        input_path: Path,
        stream_index: int,
        output_path: Path,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [
                    self.ffmpeg_binary,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(input_path),
                    "-map",
                    f"0:{stream_index}",
                    "-c:s",
                    "srt",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError as exc:
            raise TranscriptError(
                "ffmpeg was not found; install FFmpeg and ensure ffmpeg is on PATH"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise TranscriptError("ffmpeg timed out while extracting subtitles") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip()
            raise TranscriptError(
                "ffmpeg subtitle extraction failed"
                + (f": {detail}" if detail else "")
            ) from exc

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise TranscriptError("ffmpeg produced an empty subtitle file")

    @staticmethod
    def _parse_srt(payload: str) -> list[tuple[float, float, str]]:
        blocks = re.split(r"\n\s*\n", payload.replace("\r\n", "\n").replace("\r", "\n"))
        parsed: list[tuple[float, float, str]] = []
        for block in blocks:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if len(lines) < 3:
                continue

            timing_index = 1 if re.fullmatch(r"\d+", lines[0]) else 0
            if timing_index >= len(lines):
                continue
            timing = lines[timing_index]
            match = re.match(
                r"(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{3})",
                timing,
            )
            if not match:
                continue

            text_lines = lines[timing_index + 1 :]
            text = re.sub(r"\{[^}]*\}", "", " ".join(text_lines))
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue

            start = SubtitleTranscriptExtractor._parse_timestamp(match.group(1))
            end = SubtitleTranscriptExtractor._parse_timestamp(match.group(2))
            if end > start:
                parsed.append((start, end, text))
        return parsed

    @staticmethod
    def _parse_timestamp(value: str) -> float:
        hours, minutes, rest = value.replace(",", ".").split(":")
        return (
            int(hours) * 3600
            + int(minutes) * 60
            + float(rest)
        )

    @staticmethod
    def _scene_ids_for_interval(
        start: float,
        end: float,
        scene_manifest: SceneAnalysisManifest,
    ) -> tuple[str, ...]:
        matches = []
        for scene in scene_manifest.scenes:
            overlap = max(
                0.0,
                min(end, scene.end_seconds) - max(start, scene.start_seconds),
            )
            if overlap > 0:
                matches.append(scene.scene_id)
        return tuple(matches)

    @staticmethod
    def _validate_inputs(
        input_path: Path,
        episode_manifest: EpisodeAnalysisManifest,
        scene_manifest: SceneAnalysisManifest,
    ) -> None:
        if not input_path.exists() or not input_path.is_file():
            raise TranscriptError(f"transcript input does not exist: {input_path}")
        if Path(episode_manifest.input_path).expanduser().resolve() != input_path:
            raise TranscriptError("episode analysis manifest belongs to a different input file")
        if episode_manifest.input_sha256:
            from hashlib import sha256

            digest = sha256()
            with input_path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != episode_manifest.input_sha256:
                raise TranscriptError("episode input fingerprint does not match the analysis manifest")
        if Path(scene_manifest.input_path).expanduser().resolve() != input_path:
            raise TranscriptError("scene manifest belongs to a different input file")
        if (
            episode_manifest.input_sha256
            and scene_manifest.input_sha256
            and episode_manifest.input_sha256 != scene_manifest.input_sha256
        ):
            raise TranscriptError("scene and episode analysis fingerprints do not match")
