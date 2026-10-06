from pathlib import Path

from animexe.config import AppConfig
from animexe.pipeline import EpisodePipeline, PipelineResult
from animexe.paths import ProjectPaths


def test_pipeline_result_is_serializable(tmp_path: Path) -> None:
    result = PipelineResult(
        input_path="/tmp/episode.mkv",
        output_path="/tmp/output.mp4",
        checkpoints={"story": "/tmp/story.json", "render": "/tmp/output.mp4"},
        resumed=("story",),
    )
    assert result.to_dict()["resumed"] == ["story"]
    assert result.to_dict()["checkpoints"]["render"] == "/tmp/output.mp4"


def test_pipeline_rejects_missing_input(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    paths.ensure()
    try:
        EpisodePipeline(paths, AppConfig()).run(tmp_path / "missing.mkv")
    except Exception as exc:
        assert "input episode not found" in str(exc)
    else:
        raise AssertionError("missing input should fail")
