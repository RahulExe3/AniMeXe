"""Live smoke test for real AnimeParadise episode resolution and short media download.

Uses a short public sample only; it does not save a full episode. Verifies the
real API lookup, HLS manifest, frame decoding, and writing a playable clip.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import requests

from animexe.metadata.models import AnimeMetadata
from animexe.providers.animeparadise import AnimeParadiseProvider


@pytest.mark.live
def test_live_animeparadise_fetches_episode_and_downloads_clip() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.fail("Live AnimeParadise verification requires ffmpeg on PATH.")

    provider = AnimeParadiseProvider(timeout_seconds=20)
    metadata = AnimeMetadata(
        id="anilist:52991",
        title="Frieren: Beyond Journey's End",
        titles=("Frieren: Beyond Journey's End", "Sousou no Frieren", "Frieren"),
        anilist_id=52991,
        episodes=28,
        source_provider="anilist",
    )
    source = provider.resolve_anilist_episode(metadata, 1)
    assert source.provider == "animeparadise"
    assert source.protocol == "hls"
    assert source.reference.startswith("https://stream.animeparadise.moe/m3u8?")

    headers = dict(source.headers)
    response = requests.get(source.reference, headers=headers, timeout=(10, 20))
    try:
        response.raise_for_status()
        assert response.text.lstrip().startswith("#EXTM3U"), (
            "Resolved stream URL did not return an HLS manifest; "
            f"content-type={response.headers.get('Content-Type')!r}"
        )
    finally:
        response.close()

    with TemporaryDirectory(prefix="animexe-animeparadise-live-") as directory:
        directory_path = Path(directory)
        header_text = "".join(f"{name}: {value}\r\n" for name, value in headers.items())
        base_command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
        if header_text:
            base_command.extend(["-headers", header_text])

        frame = directory_path / "frame.png"
        frame_command = [*base_command, "-i", source.reference, "-t", "8",
                         "-map", "0:v:0", "-frames:v", "1", "-an", str(frame)]
        frame_result = subprocess.run(
            frame_command, capture_output=True, text=True, timeout=75
        )
        assert frame_result.returncode == 0, (
            "HLS manifest resolved, but FFmpeg could not decode a frame: "
            f"{(frame_result.stderr or '').strip()[-800:]}"
        )
        assert frame.is_file() and frame.stat().st_size > 1024, (
            "FFmpeg did not produce a valid-looking frame from the resolved episode."
        )

        # Actually download a short playable clip to disk; deliberately not the full episode.
        clip = directory_path / "episode-sample.mp4"
        clip_command = [
            *base_command, "-i", source.reference, "-t", "10",
            "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-movflags", "+faststart", str(clip),
        ]
        clip_result = subprocess.run(
            clip_command, capture_output=True, text=True, timeout=90
        )
        assert clip_result.returncode == 0, (
            "FFmpeg could decode a frame but could not download/write a playable clip: "
            f"{(clip_result.stderr or '').strip()[-1000:]}"
        )
        assert clip.is_file() and clip.stat().st_size > 10_000, (
            "FFmpeg did not write a substantial clip file from the resolved episode."
        )
