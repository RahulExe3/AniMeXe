import shutil

import pytest

from animexe.editing import EditPlanManifest, PlannedClip
from animexe.render import VisualCutRenderer


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg required")
def test_visual_cut_is_video_only(tmp_path):
    from pathlib import Path
    import subprocess

    source = tmp_path / "source.mkv"
    output = tmp_path / "cut.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=15:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    plan = EditPlanManifest(
        schema_version=1,
        episode_id="test",
        input_path=str(source),
        input_sha256="x",
        source_story="story.json",
        source_scenes="scenes.json",
        target_duration_seconds=1,
        min_duration_seconds=1,
        max_duration_seconds=2,
        max_clip_duration_seconds=2,
        selected_event_ids=("event_1",),
        clips=(
            PlannedClip("clip_001", "event_1", "scene_001", 0, 1, 1, 1, "test"),
        ),
        total_duration_seconds=1,
    )
    VisualCutRenderer(width=320, height=180, fps=15).render(
        source, plan, output_path=output
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(output)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.strip() == "video"
