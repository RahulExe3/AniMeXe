from pathlib import Path

from animexe.analysis.scenes import SceneAnalysisManifest, SceneRecord
from animexe.analysis.story import (
    EpisodeStoryManifest,
    ExtractiveStoryAnalyzer,
    StoryEvidence,
    StoryEvent,
)
from animexe.analysis.transcript import TranscriptAnalysisManifest, TranscriptSegment


def _inputs() -> tuple[TranscriptAnalysisManifest, SceneAnalysisManifest]:
    scenes = SceneAnalysisManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        detection_method="pyscenedetect:ContentDetector",
        threshold=27.0,
        min_scene_duration_seconds=0.5,
        detected_scenes=2,
        frames_extracted=0,
        scenes=(
            SceneRecord("scene_0001", 1, 0.0, 4.0, 4.0, 2.0),
            SceneRecord("scene_0002", 2, 4.0, 10.0, 6.0, 7.0),
        ),
    )
    transcript = TranscriptAnalysisManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source="embedded_subtitle",
        language="eng",
        subtitle_stream_index=2,
        transcript_status="READY",
        segments=(
            TranscriptSegment("segment_0001", 1.0, 2.5, "Gon is here!", ("scene_0001",)),
            TranscriptSegment("segment_0002", 3.5, 5.5, "We need to move now.", ("scene_0001", "scene_0002")),
        ),
    )
    return transcript, scenes


def test_extractive_story_analyzer_builds_events_and_keywords() -> None:
    transcript, scenes = _inputs()

    manifest = ExtractiveStoryAnalyzer().analyze(transcript, scenes)

    assert manifest.checkpoint == "story"
    assert manifest.method == "extractive"
    assert len(manifest.events) == 2
    assert manifest.ending_event_id == "event_0002"
    assert manifest.events[0].scene_ids == ("scene_0001",)
    assert "move" in manifest.evidence.keywords
    assert "Gon" in manifest.evidence.characters


def test_story_manifest_round_trips(tmp_path: Path) -> None:
    manifest = EpisodeStoryManifest(
        schema_version=1,
        episode_id="demo-s1-e1",
        input_path="/tmp/episode.mkv",
        input_sha256="a" * 64,
        source_transcript="transcript.json",
        source_scenes="scenes.json",
        method="extractive",
        evidence=StoryEvidence(characters=("Gon",), keywords=("move",)),
        events=(
            StoryEvent(
                "event_0001",
                ("scene_0001",),
                1.0,
                2.0,
                "Gon is here!",
                0.5,
            ),
        ),
        ending_event_id="event_0001",
        continuity_notes=("test",),
    )
    path = tmp_path / "story.json"
    manifest.write(path)

    assert EpisodeStoryManifest.read(path) == manifest
