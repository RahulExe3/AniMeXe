from animexe.analysis.scenes import SceneAnalysisManifest, SceneRecord
from animexe.tts import TTSAggregateError if False else TTSManifest, TTSSegment
from animexe.matching import SceneMatcher


def _scenes() -> SceneAnalysisManifest:
    return SceneAnalysisManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        detection_method="test",
        threshold=27.0,
        min_scene_duration_seconds=0.5,
        detected_scenes=3,
        frames_extracted=0,
        scenes=(
            SceneRecord("scene_0001", 1, 0, 4, 4, 2),
            SceneRecord("scene_0002", 2, 4, 10, 6, 7),
            SceneRecord("scene_0003", 3, 10, 16, 6, 13),
        ),
    )


def _tts() -> TTSManifest:
    return TTSManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source_script="/tmp/script.json",
        provider="synthetic",
        language="hinglish",
        script="roman",
        segments=(
            TTSSegment("hook", "Hook", "0001_hook.wav", 3.0, 24000, 1, ("scene_0001",)),
            TTSSegment("segment_0001", "Body", "0002_segment_0001.wav", 5.0, 24000, 1, ("scene_0002",)),
            TTSSegment("ending", "End", "0003_ending.wav", 2.0, 24000, 1, ("scene_0003",)),
        ),
        total_duration_seconds=10.0,
    )


def test_scene_matcher_uses_script_scene_candidates() -> None:
    manifest = SceneMatcher(max_clip_duration=8).match(_scenes(), _tts())

    assert manifest.checkpoint == "matching"
    assert len(manifest.clips) == 3
    assert [clip.scene_id for clip in manifest.clips] == [
        "scene_0001",
        "scene_0002",
        "scene_0003",
    ]
    assert sum(clip.duration_seconds for clip in manifest.clips) == 10.0


def test_scene_matcher_expands_when_one_scene_is_too_short() -> None:
    tts = TTSManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source_script="/tmp/script.json",
        provider="synthetic",
        language="hinglish",
        script="roman",
        segments=(
            TTSSegment("segment_0001", "Long", "audio.wav", 9.0, 24000, 1, ("scene_0001",)),
        ),
        total_duration_seconds=9.0,
    )

    manifest = SceneMatcher(max_clip_duration=8, allow_reuse=True).match(_scenes(), tts)

    assert sum(clip.duration_seconds for clip in manifest.clips) >= 8.85
    assert len(manifest.clips) >= 2
