from pathlib import Path

from animexe.config import load_config


def test_config_includes_metadata_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
metadata:
  anilist_endpoint: https://example.test/graphql
  jikan_base_url: https://example.test/v4
  search_limit: 7
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.metadata.anilist_endpoint == "https://example.test/graphql"
    assert config.metadata.jikan_base_url == "https://example.test/v4"
    assert config.metadata.search_limit == 7


def test_unresolved_optional_provider_url_becomes_none(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
provider:
  api_base_url: ${KUHI_API_BASE_URL}
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.provider.api_base_url is None


def test_config_includes_scene_analysis_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
episode:
  scene_threshold: 31.5
  scene_min_duration: 0.75
  scene_frame_width: 480
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.episode.scene_threshold == 31.5
    assert config.episode.scene_min_duration == 0.75
    assert config.episode.scene_frame_width == 480
