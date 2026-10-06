from pathlib import Path

import pytest

from animexe.analysis.manifest import EpisodeAnalysisManifest
from animexe.analysis.scenes import SceneAnalysisManifest, SceneIndexer, SceneDetectionError


def test_scene_indexer_normalizes_detected_scenes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    episode = tmp_path / "episode.mkv"
    episode.write_bytes(b"fake media")
    output = tmp_path / "analysis"

    detected = [(0.0, 4.0), (4.0, 9.0)]

    monkeypatch.setattr(
        "scenedetect.detect",
        lambda *args, **kwargs: [],
    )
    indexer = SceneIndexer(ffmpeg_binary="ffmpeg")

    monkeypatch.setattr(indexer, "_detect", lambda path: detected)
    monkeypatch.setattr(
        indexer,
        "_extract_frame",
        lambda input_path, timestamp, output_path: (
            output_path.parent.mkdir(parents=True, exist_ok=True),
            output_path.write_bytes(b"jpeg"),
        ),
    )

    manifest = indexer.index(
        episode,
        output_dir=output,
        episode_manifest=EpisodeAnalysisManifest(
            schema_version=1,
            episode_id="demo-s1-e1",
            input_path=str(episode.resolve()),
            input_size_bytes=10,
            input_sha256="1d9291e53a29732dbb47911e9ad50757758a42771a6a15c64fe0a823b3500683",
            inspected_at="2026-10-06T00:00:00+00:00",
            ffprobe_version="ffprobe version 7",
            format_name="matroska",
            format_long_name="Matroska",
            duration_seconds=9.0,
            start_time_seconds=0.0,
            bit_rate=1000,
        ),
        extract_frames=True,
    )

    assert manifest.detected_scenes == 2
    assert manifest.frames_extracted == 2
    assert manifest.scenes[0].scene_id == "scene_0001"
    assert manifest.scenes[0].representative_time_seconds == 2.0
    assert manifest.scenes[1].representative_time_seconds == 6.5
    assert (output / "frames" / "scene_0001.jpg").exists()


def test_scene_indexer_falls_back_to_one_scene_when_detector_finds_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    episode = tmp_path / "episode.mkv"
    episode.write_bytes(b"fake media")

    indexer = SceneIndexer(ffmpeg_binary="ffmpeg")
    monkeypatch.setattr(indexer, "_detect", lambda path: [])

    manifest = indexer.index(
        episode,
        output_dir=tmp_path / "analysis",
        episode_manifest=EpisodeAnalysisManifest(
            schema_version=1,
            episode_id=None,
            input_path=str(episode.resolve()),
            input_size_bytes=10,
            input_sha256="1d9291e53a29732dbb47911e9ad50757758a42771a6a15c64fe0a823b3500683",
            inspected_at="2026-10-06T00:00:00+00:00",
            ffprobe_version="ffprobe version 7",
            format_name="matroska",
            format_long_name="Matroska",
            duration_seconds=12.5,
            start_time_seconds=0.0,
            bit_rate=1000,
        ),
        extract_frames=False,
    )

    assert manifest.detected_scenes == 1
    assert manifest.scenes[0].start_seconds == 0.0
    assert manifest.scenes[0].end_seconds == 12.5
    assert manifest.frames_extracted == 0


def test_scene_indexer_rejects_manifest_for_other_input(tmp_path: Path) -> None:
    episode = tmp_path / "episode.mkv"
    other = tmp_path / "other.mkv"
    episode.write_bytes(b"fake media")
    other.write_bytes(b"other")

    manifest = EpisodeAnalysisManifest(
        schema_version=1,
        episode_id=None,
        input_path=str(other.resolve()),
        input_size_bytes=5,
        input_sha256="d9298a10d1b0735837dc4bd85dac641b0f3cef27a47e5d53a54f2f3f5b2fcffa",
        inspected_at="2026-10-06T00:00:00+00:00",
        ffprobe_version="ffprobe version 7",
        format_name="matroska",
        format_long_name="Matroska",
        duration_seconds=12.5,
        start_time_seconds=0.0,
        bit_rate=1000,
    )

    with pytest.raises(SceneDetectionError, match="different input file"):
        SceneIndexer(ffmpeg_binary="ffmpeg").index(
            episode,
            output_dir=tmp_path / "analysis",
            episode_manifest=manifest,
            extract_frames=False,
        )


def test_scene_manifest_round_trips(tmp_path: Path) -> None:
    manifest = SceneAnalysisManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        detection_method="pyscenedetect:ContentDetector",
        threshold=27.0,
        min_scene_duration_seconds=0.5,
        detected_scenes=1,
        frames_extracted=0,
        scenes=(),
    )
    path = tmp_path / "scenes.json"
    manifest.write(path)

    loaded = SceneAnalysisManifest.read(path)

    assert loaded == manifest
