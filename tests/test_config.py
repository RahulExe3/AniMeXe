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
