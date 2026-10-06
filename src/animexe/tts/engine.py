from __future__ import annotations

import base64
import json
import math
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..narration import NarrationScriptManifest


class TTSError(RuntimeError):
    """Raised when TTS synthesis or audio validation fails."""


class TTSSynthesizer(Protocol):
    def synthesize(
        self,
        script: NarrationScriptManifest,
        *,
        output_dir: Path,
        source_script: str = "script.json",
    ) -> "TTSManifest": ...


@dataclass(frozen=True)
class TTSSegment:
    segment_id: str
    text: str
    audio: str
    duration_seconds: float
    sample_rate: int
    channels: int
    scene_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "text": self.text,
            "audio": self.audio,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "scene_ids": list(self.scene_ids),
        }


@dataclass(frozen=True)
class TTSManifest:
    schema_version: int
    episode_id: str | None
    input_path: str
    input_sha256: str
    source_script: str
    provider: str
    language: str
    script: str
    segments: tuple[TTSSegment, ...]
    total_duration_seconds: float
    checkpoint: str = "TTS"
    voice: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "input_path": self.input_path,
            "input_sha256": self.input_sha256,
            "source_script": self.source_script,
            "provider": self.provider,
            "language": self.language,
            "script": self.script,
            "segments": [segment.to_dict() for segment in self.segments],
            "total_duration_seconds": self.total_duration_seconds,
            "checkpoint": self.checkpoint,
            "voice": self.voice,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read(cls, path: Path) -> "TTSManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["segments"] = tuple(
            TTSSegment(
                segment_id=item["segment_id"],
                text=item["text"],
                audio=item["audio"],
                duration_seconds=float(item["duration_seconds"]),
                sample_rate=int(item["sample_rate"]),
                channels=int(item["channels"]),
                scene_ids=tuple(item.get("scene_ids", [])),
            )
            for item in payload.get("segments", [])
        )
        return cls(**payload)


class SyntheticTTSSynthesizer:
    """Create deterministic real WAV audio for end-to-end pipeline tests."""

    def __init__(
        self,
        *,
        words_per_minute: int = 145,
        sample_rate: int = 24000,
    ) -> None:
        if words_per_minute < 60 or words_per_minute > 220:
            raise ValueError("words_per_minute must be between 60 and 220")
        if sample_rate < 8000:
            raise ValueError("sample_rate must be at least 8000")
        self.words_per_minute = words_per_minute
        self.sample_rate = sample_rate

    def synthesize(
        self,
        script: NarrationScriptManifest,
        *,
        output_dir: Path,
        source_script: str = "script.json",
    ) -> TTSManifest:
        output_dir.mkdir(parents=True, exist_ok=True)

        items: list[tuple[str, str, tuple[str, ...]]] = [
            ("hook", script.hook, script.hook_scene_ids)
        ]
        items.extend(
            (segment.segment_id, segment.text, segment.scene_ids)
            for segment in script.segments
        )
        items.append(("ending", script.ending, script.ending_scene_ids))

        rendered: list[TTSSegment] = []
        for index, (segment_id, text_value, scene_ids) in enumerate(items, start=1):
            duration = max(0.45, self._estimated_duration(text_value))
            audio_path = output_dir / f"{index:04d}_{_safe_name(segment_id)}.wav"
            self._render_tone(audio_path, duration)
            measured, sample_rate, channels = _probe_audio(audio_path)
            rendered.append(
                TTSSegment(
                    segment_id=segment_id,
                    text=text_value,
                    audio=audio_path.name,
                    duration_seconds=measured,
                    sample_rate=sample_rate,
                    channels=channels,
                    scene_ids=scene_ids,
                )
            )

        total = sum(segment.duration_seconds for segment in rendered)
        return TTSManifest(
            schema_version=1,
            episode_id=script.episode_id,
            input_path=script.input_path,
            input_sha256=script.input_sha256,
            source_script=source_script,
            provider="synthetic",
            language=script.language,
            script=script.script,
            segments=tuple(rendered),
            total_duration_seconds=round(total, 3),
            voice="test-tone",
        )

    def _estimated_duration(self, text: str) -> float:
        words = max(1, len(re.findall(r"\b[\w']+\b", text, flags=re.UNICODE)))
        return words / self.words_per_minute * 60.0

    def _render_tone(self, path: Path, duration: float) -> None:
        frame_count = max(1, int(round(duration * self.sample_rate)))
        amplitude = 5000
        frequency = 440
        period = max(1, int(self.sample_rate / frequency))
        frames = bytearray()
        for index in range(frame_count):
            phase = index % period
            sample = amplitude if phase < period // 2 else -amplitude
            frames.extend(int(sample).to_bytes(2, byteorder="little", signed=True))
        try:
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.sample_rate)
                wav.writeframes(bytes(frames))
        except (OSError, wave.Error) as exc:
            raise TTSError(f"synthetic TTS could not write WAV: {exc}") from exc


class GeminiTTSSynthesizer:
    """Generate real narration with Gemini 3.8 Flash TTS."""

    def __init__(
        self,
        *,
        model: str = "gemini-3.8-flash-tts",
        api_key_env: str = "GEMINI_API_KEY",
        voice: str = "Kore",
        style: str = (
            "natural, conversational, expressive YouTube narrator; "
            "clear sentence endings; natural pauses; believable Hinglish delivery"
        ),
    ) -> None:
        if not model.strip():
            raise ValueError("Gemini TTS model cannot be empty")
        if not api_key_env.strip():
            raise ValueError("Gemini TTS API key environment variable cannot be empty")
        if not voice.strip():
            raise ValueError("Gemini TTS voice cannot be empty")
        if not style.strip():
            raise ValueError("Gemini TTS style cannot be empty")
        self.model = model
        self.api_key_env = api_key_env
        self.voice = voice
        self.style = style
        self._client = None

    def synthesize(
        self,
        script: NarrationScriptManifest,
        *,
        output_dir: Path,
        source_script: str = "script.json",
    ) -> TTSManifest:
        output_dir.mkdir(parents=True, exist_ok=True)
        client = self._client_or_create()

        items: list[tuple[str, str, tuple[str, ...]]] = [
            ("hook", script.hook, script.hook_scene_ids)
        ]
        items.extend(
            (segment.segment_id, segment.text, segment.scene_ids)
            for segment in script.segments
        )
        items.append(("ending", script.ending, script.ending_scene_ids))

        rendered: list[TTSSegment] = []
        for index, (segment_id, text_value, scene_ids) in enumerate(items, start=1):
            audio_path = output_dir / f"{index:04d}_{_safe_name(segment_id)}.wav"
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=[{
                        "role": "user",
                        "parts": [{
                            "text": text_value,
                            "speech_metadata": {"style": self.style},
                        }],
                    }],
                    config={
                        "response_modalities": ["AUDIO"],
                        "speech_config": {
                            "voice_config": {"voice": self.voice},
                        },
                    },
                )
            except Exception as exc:
                raise TTSError(
                    f"Gemini TTS request failed for {segment_id}: {exc}"
                ) from exc

            audio_data = _extract_gemini_audio(response)
            if not audio_data:
                raise TTSError(f"Gemini TTS returned no audio for {segment_id}")
            try:
                audio_path.write_bytes(audio_data)
            except OSError as exc:
                raise TTSError(f"could not write Gemini TTS audio {audio_path}: {exc}") from exc

            duration, sample_rate, channels = _probe_audio(audio_path)
            rendered.append(
                TTSSegment(
                    segment_id=segment_id,
                    text=text_value,
                    audio=audio_path.name,
                    duration_seconds=duration,
                    sample_rate=sample_rate,
                    channels=channels,
                    scene_ids=scene_ids,
                )
            )

        total = sum(segment.duration_seconds for segment in rendered)
        return TTSManifest(
            schema_version=1,
            episode_id=script.episode_id,
            input_path=script.input_path,
            input_sha256=script.input_sha256,
            source_script=source_script,
            provider="gemini",
            language=script.language,
            script=script.script,
            segments=tuple(rendered),
            total_duration_seconds=round(total, 3),
            voice=self.voice,
        )

    def _client_or_create(self):
        if self._client is not None:
            return self._client
        api_key = __import__("os").environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise TTSError(
                f"Gemini TTS API key is missing; set {self.api_key_env} in the environment"
            )
        try:
            from google import genai
        except ImportError as exc:
            raise TTSError(
                "google-genai is not installed; install the project dependencies first"
            ) from exc
        self._client = genai.Client(api_key=api_key)
        return self._client


def _extract_gemini_audio(response: object) -> bytes:
    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline_data = getattr(part, "inline_data", None)
                data = getattr(inline_data, "data", None) if inline_data else None
                if isinstance(data, bytes):
                    return data
                if isinstance(data, str) and data.strip():
                    try:
                        return base64.b64decode(data)
                    except (ValueError, base64.binascii.Error):
                        continue
    except Exception:
        return b""
    return b""


class CommandTTSSynthesizer:
    """Bridge to an external/local TTS runner without baking a model into AniMeXe."""

    def __init__(
        self,
        command: tuple[str, ...],
        *,
        voice: str | None = None,
        timeout_seconds: int = 180,
    ) -> None:
        if not command:
            raise ValueError("TTS command cannot be empty")
        if timeout_seconds < 1:
            raise ValueError("TTS command timeout must be positive")
        self.command = command
        self.voice = voice
        self.timeout_seconds = timeout_seconds

    def synthesize(
        self,
        script: NarrationScriptManifest,
        *,
        output_dir: Path,
        source_script: str = "script.json",
    ) -> TTSManifest:
        _require_media_tools()
        output_dir.mkdir(parents=True, exist_ok=True)

        items: list[tuple[str, str, tuple[str, ...]]] = [
            ("hook", script.hook, script.hook_scene_ids)
        ]
        items.extend(
            (segment.segment_id, segment.text, segment.scene_ids)
            for segment in script.segments
        )
        items.append(("ending", script.ending, script.ending_scene_ids))

        rendered: list[TTSSegment] = []
        for index, (segment_id, text_value, scene_ids) in enumerate(items, start=1):
            safe_id = _safe_name(segment_id)
            audio_path = output_dir / f"{index:04d}_{safe_id}.wav"
            text_path = output_dir / f"{index:04d}_{safe_id}.txt"
            text_path.write_text(text_value, encoding="utf-8")
            command = tuple(
                value.format(
                    text_file=str(text_path),
                    output_file=str(audio_path),
                    language=script.language,
                    script=script.script,
                    segment_id=segment_id,
                    voice=self.voice or "",
                )
                for value in self.command
            )
            completed = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                raise TTSError(
                    f"TTS command failed for {segment_id}: "
                    f"{completed.stderr.strip() or completed.stdout.strip() or 'unknown error'}"
                )
            if not audio_path.exists():
                raise TTSError(
                    f"TTS command did not create expected audio: {audio_path}"
                )

            duration, sample_rate, channels = _probe_audio(audio_path)
            rendered.append(
                TTSSegment(
                    segment_id=segment_id,
                    text=text_value,
                    audio=audio_path.name,
                    duration_seconds=duration,
                    sample_rate=sample_rate,
                    channels=channels,
                    scene_ids=scene_ids,
                )
            )

        total = sum(segment.duration_seconds for segment in rendered)
        return TTSManifest(
            schema_version=1,
            episode_id=script.episode_id,
            input_path=script.input_path,
            input_sha256=script.input_sha256,
            source_script=source_script,
            provider="command",
            language=script.language,
            script=script.script,
            segments=tuple(rendered),
            total_duration_seconds=round(total, 3),
            voice=self.voice,
        )


def _require_media_tools() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise TTSError("ffmpeg and ffprobe are required for command TTS")


def _probe_audio(path: Path) -> tuple[float, int, int]:
    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            duration = frames / float(sample_rate)
            if duration > 0 and sample_rate > 0 and channels > 0:
                return duration, sample_rate, channels
    except (OSError, wave.Error):
        pass
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise TTSError(
            f"ffprobe failed for {path}: "
            f"{completed.stderr.strip() or 'unknown error'}"
        )
    try:
        payload = json.loads(completed.stdout)
        streams = [
            stream
            for stream in payload.get("streams", [])
            if stream.get("codec_type") == "audio"
        ]
        if not streams:
            raise ValueError("no audio stream")
        stream = streams[0]
        duration = float(stream.get("duration") or payload["format"]["duration"])
        sample_rate = int(stream.get("sample_rate") or 0)
        channels = int(stream.get("channels") or 0)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TTSError(f"invalid audio probe result for {path}") from exc
    if duration <= 0 or sample_rate <= 0 or channels <= 0:
        raise TTSError(f"invalid audio properties for {path}")
    return duration, sample_rate, channels


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")[:80] or "segment"
