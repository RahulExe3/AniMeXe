from animexe.matching import NarrationClip, SceneMatchManifest
from animexe.tts import TTSManifest, TTSSegment
from animexe.render import TimelineBuilder


def test_timeline_builder_creates_audio_and_subtitle_events() -> None:
    matching = SceneMatchManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source_scenes="scenes.json",
        source_tts="tts.json",
        clips=(
            NarrationClip("hook", "0001_hook.wav", "scene_0001", 0, 3, 3, 0.9),
            NarrationClip("segment_0001", "0002_segment.wav", "scene_0002", 3, 8, 5, 0.9),
            NarrationClip("ending", "0003_ending.wav", "scene_0003", 8, 10, 2, 0.9),
        ),
        total_narration_duration_seconds=10,
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
            TTSSegment("segment_0001", "Body", "0002_segment.wav", 5, 24000, 1, ("scene_0002",)),
            TTSSegment("ending", "End", "0003_ending.wav", 2, 24000, 1, ("scene_0003",)),
        ),
        total_duration_seconds=10,
    )

    timeline = TimelineBuilder().build(matching, tts)

    assert timeline.checkpoint == "timeline"
    assert timeline.total_duration_seconds == 10
    assert len(timeline.clips) == 3
    assert [item.start_seconds for item in timeline.narration_audio] == [0, 3, 8]
    assert [item.start_seconds for item in timeline.subtitles] == [0, 3, 8]
