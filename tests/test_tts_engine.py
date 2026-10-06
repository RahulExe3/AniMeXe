from pathlib import Path

from animexe.narration import NarrationScriptManifest, NarrationSegment
from animexe.tts import SyntheticTTSSynthesizer, TTSManifest


def _script() -> NarrationScriptManifest:
    return NarrationScriptManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source_story="/tmp/story.json",
        language="hinglish",
        script="roman",
        style="conversational",
        target_duration_seconds=120,
        min_duration_seconds=105,
        max_duration_seconds=135,
        words_per_minute=145,
        hook="Everything changes when Gon arrives.",
        hook_scene_ids=("scene_0001",),
        segments=(
            NarrationSegment(
                "segment_0001",
                "The group makes an important decision.",
                ("scene_0001",),
                ("event_0001",),
                "setup",
                0,
                1,
            ),
            NarrationSegment(
                "segment_0002",
                "Now the journey finally begins.",
                ("scene_0002",),
                ("event_0002",),
                "resolution",
                1,
                2,
            ),
        ),
        ending="And this sets up what comes next.",
        ending_scene_ids=("scene_0002",),
        word_count=13,
        estimated_duration_seconds=5.38,
    )


def test_synthetic_tts_writes_real_audio(tmp_path: Path) -> None:
    manifest = SyntheticTTSSynthesizer(words_per_minute=145).synthesize(
        _script(),
        output_dir=tmp_path,
    )

    assert isinstance(manifest, TTSManifest)
    assert manifest.provider == "synthetic"
    assert manifest.language == "hinglish"
    assert manifest.script == "roman"
    assert len(manifest.segments) == 4
    assert manifest.total_duration_seconds > 0
    for segment in manifest.segments:
        assert (tmp_path / segment.audio).exists()
        assert segment.duration_seconds > 0
        assert segment.sample_rate == 24000
        assert segment.channels == 1
