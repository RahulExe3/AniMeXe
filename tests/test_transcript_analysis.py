from pathlib import Path
import hashlib

import pytest

from animexe.analysis.manifest import EpisodeAnalysisManifest, StreamManifest
from animexe.analysis.scenes import SceneAnalysisManifest, SceneRecord
from animexe.analysis.transcript import (
    SubtitleTranscriptExtractor,
    TranscriptAnalysisManifest,
    TranscriptError,
)


def _episode_manifest(path: Path) -> EpisodeAnalysisManifest:
    return EpisodeAnalysisManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path=str(path.resolve()),
        input_size_bytes=path.stat().st_size,
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        inspected_at="2026-10-06T00:00:00+00:00",
        ffprobe_version="ffprobe version 7",
        format_name="matroska",
        format_long_name="Matroska",
        duration_seconds=10.0,
        start_time_seconds=0.0,
        bit_rate=1000,
        streams=(
            StreamManifest(index=1, codec_type="subtitle", language="jpn"),
            StreamManifest(index=2, codec_type="subtitle", language="eng"),
        ),
        subtitle_streams=2,
    )


def _scene_manifest(path: Path) -> SceneAnalysisManifest:
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    scenes = (
        SceneRecord(
            scene_id="scene_0001",
            index=1,
            start_seconds=0.0,
            end_seconds=4.0,
            duration_seconds=4.0,
            representative_time_seconds=2.0,
        ),
        SceneRecord(
            scene_id="scene_0002",
            index=2,
            start_seconds=4.0,
            end_seconds=10.0,
            duration_seconds=6.0,
            representative_time_seconds=7.0,
        ),
    )
    return SceneAnalysisManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path=str(path.resolve()),
        input_sha256=source_hash,
        detection_method="pyscenedetect:ContentDetector",
        threshold=27.0,
        min_scene_duration_seconds=0.5,
        detected_scenes=2,
        frames_extracted=0,
        scenes=scenes,
    )


def test_subtitle_extraction_aligns_segments_to_scenes(tmp_path: Path) -> None:
    episode = tmp_path / "episode.mkv"
    episode.write_bytes(b"fake media")
    output = tmp_path / "analysis"
    srt = """1
00:00:01,000 --> 00:00:02,500
Hello <i>world</i>!

2
00:00:03,500 --> 00:00:05,500
Second line.
"""

    extractor = SubtitleTranscriptExtractor(ffmpeg_binary="ffmpeg")
    extractor._extract_subtitle = lambda input_path, stream_index, output_path: (
        output_path.parent.mkdir(parents=True, exist_ok=True),
        output_path.write_text(srt, encoding="utf-8"),
    )

    manifest = extractor.extract(
        episode,
        output_dir=output,
        episode_manifest=_episode_manifest(episode),
        scene_manifest=_scene_manifest(episode),
    )

    assert manifest.source == "embedded_subtitle"
    assert manifest.language == "eng"
    assert manifest.subtitle_stream_index == 2
    assert manifest.transcript_status == "READY"
    assert manifest.segments[0].text == "Hello world!"
    assert manifest.segments[0].scene_ids == ("scene_0001",)
    assert manifest.segments[1].scene_ids == ("scene_0001", "scene_0002")


def test_subtitle_extraction_requires_a_text_subtitle_stream(tmp_path: Path) -> None:
    episode = tmp_path / "episode.mkv"
    episode.write_bytes(b"fake media")
    manifest = _episode_manifest(episode)
    manifest = EpisodeAnalysisManifest(
        **{**manifest.to_dict(), "streams": (), "subtitle_streams": 0}
    )

    with pytest.raises(TranscriptError, match="no embedded text subtitle stream"):
        SubtitleTranscriptExtractor().extract(
            episode,
            output_dir=tmp_path / "analysis",
            episode_manifest=manifest,
            scene_manifest=_scene_manifest(episode),
        )


def test_transcript_manifest_round_trips(tmp_path: Path) -> None:
    manifest = TranscriptAnalysisManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source="embedded_subtitle",
        language="eng",
        subtitle_stream_index=2,
        transcript_status="READY",
    )
    path = tmp_path / "transcript.json"
    manifest.write(path)

    assert TranscriptAnalysisManifest.read(path) == manifest
