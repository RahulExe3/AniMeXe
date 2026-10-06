from pathlib import Path

import pytest

from animexe.analysis.scenes import SceneAnalysisManifest, SceneRecord
from animexe.analysis.story import EpisodeStoryManifest, StoryEvent, StoryEvidence
from animexe.editing import EditPlanner


def _fixtures():
    scenes = tuple(
        SceneRecord(
            scene_id=f"scene_{index:03d}",
            index=index,
            start_seconds=(index - 1) * 5,
            end_seconds=index * 5,
            duration_seconds=5,
            representative_time_seconds=(index - 0.5) * 5,
        )
        for index in range(1, 7)
    )
    events = tuple(
        StoryEvent(
            event_id=f"event_{index:03d}",
            scene_ids=(f"scene_{index:03d}",),
            start_seconds=(index - 1) * 5,
            end_seconds=index * 5,
            text=f"event {index}",
            importance=0.95 if index in {2, 5} else 0.35,
            kind="reveal" if index == 5 else "dialogue",
        )
        for index in range(1, 7)
    )
    story = EpisodeStoryManifest(
        schema_version=2,
        episode_id="test-episode",
        input_path="/tmp/episode.mkv",
        input_sha256="abc123",
        source_transcript="transcript.json",
        source_scenes="scenes.json",
        method="gemini",
        evidence=StoryEvidence(),
        events=events,
        ending_event_id="event_006",
        summary="A test story.",
    )
    scenes_manifest = SceneAnalysisManifest(
        schema_version=1,
        episode_id="test-episode",
        input_path="/tmp/episode.mkv",
        input_sha256="abc123",
        detection_method="test",
        threshold=27.0,
        min_scene_duration_seconds=0.5,
        detected_scenes=6,
        frames_extracted=0,
        scenes=scenes,
    )
    return story, scenes_manifest


def test_edit_planner_selects_important_scenes_in_story_order():
    story, scenes = _fixtures()
    plan = EditPlanner(
        target_duration_seconds=15,
        min_duration_seconds=10,
        max_duration_seconds=18,
        max_clip_duration_seconds=5,
    ).plan(story, scenes)

    assert plan.clips
    assert plan.total_duration_seconds <= 18
    assert plan.clips[0].source_start_seconds < plan.clips[-1].source_start_seconds
    selected = {clip.scene_id for clip in plan.clips}
    assert "scene_005" in selected
    assert "scene_006" in selected
    assert tuple(plan.scene_ids) == tuple(clip.scene_id for clip in plan.clips)


def test_edit_planner_rejects_mismatched_input():
    story, scenes = _fixtures()
    object.__setattr__(scenes, "input_sha256", "different")
    with pytest.raises(Exception, match="fingerprints"):
        EditPlanner(target_duration_seconds=10, min_duration_seconds=5, max_duration_seconds=12).plan(
            story, scenes
        )
