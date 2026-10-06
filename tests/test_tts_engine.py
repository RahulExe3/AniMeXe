from io import BytesIO
from pathlib import Path
import wave

from animexe.narration import NarrationScriptManifest, NarrationSegment
from animexe.tts import GeminiTTSSynthesizer, SyntheticTTSSynthesizer, TTSManifest


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



def _wav_bytes() -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes((b"\x00\x00") * 2400)
    return buffer.getvalue()


class _FakeGeminiClient:
    def __init__(self) -> None:
        self.models = self
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)

        class Part:
            inline_data = type("InlineData", (), {"data": _wav_bytes()})()

        class Content:
            parts = [Part()]

        class Candidate:
            content = Content()

        return type("Response", (), {"candidates": [Candidate()]})()


def test_gemini_tts_writes_measured_wav_audio(tmp_path: Path) -> None:
    client = _FakeGeminiClient()
    manifest = GeminiTTSSynthesizer(
        client=client,
        voice="Kore",
    ).synthesize(_script(), output_dir=tmp_path)

    assert manifest.provider == "gemini"
    assert manifest.voice == "Kore"
    assert len(manifest.segments) == 4
    assert all(segment.sample_rate == 24000 for segment in manifest.segments)
    assert all(segment.channels == 1 for segment in manifest.segments)
    assert all((tmp_path / segment.audio).exists() for segment in manifest.segments)
    assert client.calls
    assert client.calls[0]["config"]["response_modalities"] == ["AUDIO"]
