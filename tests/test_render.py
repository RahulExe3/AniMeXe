from pathlib import Path
from types import SimpleNamespace

from animexe.matching import NarrationClip, SceneMatchManifest
from animexe.render import FFmpegRenderer, TimelineBuilder
from animexe.tts import TTSManifest, TTSSegment


def _timeline() -> tuple:
    matching = SceneMatchManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source_scenes="scenes.json",
        source_tts="tts.json",
        clips=(
            NarrationClip("hook", "0001_hook.wav", "scene_0001", 0, 3, 3, 0.9),
        ),
        total_narration_duration_seconds=3,
    )
    tts = TTSManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source_script="script.json",
        provider="synthetic",
        language="hinglish",
        script="roman",
        segments=(
            TTSSegment("hook", "Hook", "0001_hook.wav", 3, 24000, 1, ("scene_0001",)),
        ),
        total_duration_seconds=3,
    )
    return TimelineBuilder().build(matching, tts)


def test_renderer_builds_ducked_bgm_filter_and_validates_output(tmp_path: Path, monkeypatch) -> None:
    timeline = _timeline()
    source = tmp_path / "episode.mkv"
    narration_dir = tmp_path / "audio"
    narration_dir.mkdir()
    (narration_dir / "0001_hook.wav").write_bytes(b"audio")
    bgm = tmp_path / "bgm.wav"
    bgm.write_bytes(b"bgm")
    source.write_bytes(b"source")
    output = tmp_path / "out.mp4"

    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"mp4")
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout='{"streams":[{"codec_type":"video"},{"codec_type":"audio"}],"format":{"duration":"3.0"}}',
        )

    monkeypatch.setattr("animexe.render.ffmpeg.subprocess.run", fake_run)
    monkeypatch.setattr(FFmpegRenderer, "_require_tools", staticmethod(lambda: None))

    rendered = FFmpegRenderer().render(
        timeline,
        source_video=source,
        narration_dir=narration_dir,
        output_path=output,
        background_music=bgm,
        bgm_volume=0.12,
        bgm_ducking_ratio=8.0,
    )

    assert rendered == output
    ffmpeg_command = commands[0]
    assert "-stream_loop" in ffmpeg_command
    filter_graph = ffmpeg_command[ffmpeg_command.index("-filter_complex") + 1]
    assert "sidechaincompress" in filter_graph
    assert "volume=0.1200" in filter_graph
    assert output.exists()
