from pathlib import Path

import pytest

from animexe.analysis import EpisodeInspector, EpisodeAnalysisManifest, InspectionError


def test_inspector_normalizes_ffprobe_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    episode = tmp_path / "episode.mkv"
    episode.write_bytes(b"fake media")

    payload = {
        "format": {
            "format_name": "matroska,webm",
            "format_long_name": "Matroska / WebM",
            "duration": "1420.500",
            "start_time": "0.000",
            "bit_rate": "3200000",
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "codec_long_name": "H.264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "24000/1001",
                "r_frame_rate": "24000/1001",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "sample_rate": "48000",
                "tags": {"language": "jpn"},
            },
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {"language": "eng", "title": "English"},
            },
        ],
    }

    class FakeCompleted:
        stdout = "ffprobe version 7.0\n"

    def fake_run(*args, **kwargs):
        command = args[0]
        if command[1] == "-version":
            return FakeCompleted()
        FakeCompleted.stdout = __import__("json").dumps(payload)
        return FakeCompleted()

    monkeypatch.setattr("animexe.analysis.inspector.subprocess.run", fake_run)
    inspector = EpisodeInspector(ffprobe_binary="ffprobe")

    manifest = inspector.inspect(episode, episode_id="demo-s1-e1")

    assert manifest.episode_id == "demo-s1-e1"
    assert manifest.duration_seconds == 1420.5
    assert manifest.video_streams == 1
    assert manifest.audio_streams == 1
    assert manifest.subtitle_streams == 1
    assert manifest.streams[0].width == 1920
    assert manifest.streams[1].channels == 2
    assert manifest.streams[2].language == "eng"
    assert manifest.checkpoint == "inspected"
    assert len(manifest.input_sha256) == 64


def test_manifest_round_trips(tmp_path: Path) -> None:
    manifest = EpisodeAnalysisManifest(
        schema_version=1,
        episode_id=None,
        input_path="/tmp/demo.mkv",
        input_size_bytes=10,
        input_sha256="a" * 64,
        inspected_at="2026-10-06T00:00:00+00:00",
        ffprobe_version="ffprobe version 7.0",
        format_name="matroska",
        format_long_name="Matroska",
        duration_seconds=10.0,
        start_time_seconds=0.0,
        bit_rate=1000,
    )
    path = tmp_path / "manifest.json"
    manifest.write(path)

    loaded = EpisodeAnalysisManifest.read(path)

    assert loaded == manifest


def test_inspector_rejects_missing_input(tmp_path: Path) -> None:
    with pytest.raises(InspectionError, match="does not exist"):
        EpisodeInspector(ffprobe_binary="ffprobe").inspect(tmp_path / "missing.mkv")
