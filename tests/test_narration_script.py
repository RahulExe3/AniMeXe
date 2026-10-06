from types import SimpleNamespace

import pytest

from animexe.analysis.scenes import SceneAnalysisManifest, SceneRecord
from animexe.analysis.story import EpisodeStoryManifest, StoryEvent, StoryEvidence
from animexe.analysis.transcript import TranscriptAnalysisManifest, TranscriptSegment
from animexe.narration.script import (
    GeminiNarrationScriptGenerator,
    NarrationScriptError,
)


class _FakeModels:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        import json
        return SimpleNamespace(text=json.dumps(self.payload))


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.models = _FakeModels(payload)


def _story() -> EpisodeStoryManifest:
    return EpisodeStoryManifest(
        schema_version=2,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source_transcript="transcript.json",
        source_scenes="scenes.json",
        method="gemini",
        evidence=StoryEvidence(
            characters=("Gon",),
            locations=("Forest",),
            keywords=("journey",),
        ),
        events=(
            StoryEvent("event_0001", ("scene_0001",), 0.0, 20.0, "Gon arrives.", 0.8, "arrival"),
            StoryEvent(
                "event_0002",
                ("scene_0002",),
                20.0,
                60.0,
                "The group decides to move.",
                0.9,
                "decision",
            ),
            StoryEvent(
                "event_0003",
                ("scene_0003",),
                60.0,
                100.0,
                "They begin the journey.",
                0.85,
                "transition",
            ),
        ),
        ending_event_id="event_0003",
        summary="Gon arrives, the group makes a decision, and the journey begins.",
        relationships=("Gon travels with the group.",),
        ending="The group begins moving into the forest.",
        narration_points=("Gon arrives.", "The group decides to move.", "The journey starts."),
        confidence=0.92,
        model="gemini-test",
    )


def _transcript() -> TranscriptAnalysisManifest:
    return TranscriptAnalysisManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source="embedded_subtitle",
        language="eng",
        subtitle_stream_index=2,
        transcript_status="READY",
        segments=(
            TranscriptSegment(
                "segment_0001",
                1.0,
                2.5,
                "Hey, we need to move now before the storm reaches us.",
                ("scene_0001",),
            ),
        ),
    )


def _words(count: int) -> str:
    return " ".join(f"word{i}" for i in range(count))


def _payload(language: str) -> dict:
    words = _words(282)
    body = f"This episode moves forward with a clear decision. {words}"
    return {
        "hook": "Everything changes when Gon arrives.",
        "hook_scene_ids": ["scene_0001"],
        "segments": [
            {
                "segment_id": "segment_0001",
                "text": body[: len(body) // 3],
                "scene_ids": ["scene_0001"],
                "story_event_ids": ["event_0001"],
                "purpose": "setup",
                "start_seconds": 0.0,
                "end_seconds": 25.0,
            },
            {
                "segment_id": "segment_0002",
                "text": body[len(body) // 3 : 2 * len(body) // 3],
                "scene_ids": ["scene_0002"],
                "story_event_ids": ["event_0002"],
                "purpose": "turning_point",
                "start_seconds": 25.0,
                "end_seconds": 80.0,
            },
            {
                "segment_id": "segment_0003",
                "text": body[2 * len(body) // 3 :],
                "scene_ids": ["scene_0003"],
                "story_event_ids": ["event_0003"],
                "purpose": "resolution",
                "start_seconds": 80.0,
                "end_seconds": 118.0,
            },
        ],
        "ending": "And that decision sets up the next part of their journey.",
        "ending_scene_ids": ["scene_0003"],
        "word_count": 292,
        "estimated_duration_seconds": 121.0,
    }


def test_generates_hinglish_script() -> None:
    client = _FakeClient(_payload("hinglish"))
    generator = GeminiNarrationScriptGenerator(client=client)

    manifest = generator.generate(
        _story(),
        transcript=_transcript(),
        language="hinglish",
        script="roman",
    )

    assert manifest.language == "hinglish"
    assert manifest.script == "roman"
    assert manifest.checkpoint == "script"
    assert manifest.word_count == GeminiNarrationScriptGenerator._word_count(
        " ".join([manifest.hook, *(segment.text for segment in manifest.segments), manifest.ending])
    )
    assert manifest.model == "gemini-3.8-flash"
    assert client.models.calls[0]["model"] == "gemini-3.8-flash"
    assert client.models.calls[0]["config"].response_mime_type == "application/json"


def test_generates_english_script_from_same_story() -> None:
    client = _FakeClient(_payload("english"))
    manifest = GeminiNarrationScriptGenerator(client=client).generate(
        _story(),
        transcript=_transcript(),
        language="english",
        script="latin",
    )

    assert manifest.language == "english"
    assert manifest.script == "latin"


def test_rejects_unknown_scene() -> None:
    payload = _payload("hinglish")
    payload["segments"][1]["scene_ids"] = ["scene_9999"]

    with pytest.raises(NarrationScriptError, match="unknown scene"):
        GeminiNarrationScriptGenerator(client=_FakeClient(payload)).generate(
            _story(), transcript=_transcript(), language="hinglish", script="roman"
        )


def test_rejects_exact_subtitle_copy() -> None:
    payload = _payload("hinglish")
    payload["segments"][0]["text"] = (
        "Hey, we need to move now before the storm reaches us. "
        + _words(250)
    )

    with pytest.raises(NarrationScriptError, match="exact 9-word subtitle overlap"):
        GeminiNarrationScriptGenerator(client=_FakeClient(payload)).generate(
            _story(), transcript=_transcript(), language="hinglish", script="roman"
        )


def test_requires_matching_language_script_pair() -> None:
    with pytest.raises(NarrationScriptError, match="English narration"):
        GeminiNarrationScriptGenerator(client=_FakeClient(_payload("english"))).generate(
            _story(), transcript=_transcript(), language="english", script="roman"
        )
