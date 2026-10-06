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


def test_config_includes_gemini_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
llm:
  provider: gemini
  model: gemini-test
  api_key_env: TEST_GEMINI_KEY
  temperature: 0.35
  max_output_tokens: 4000
  max_frames: 12
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.llm.provider == "gemini"
    assert config.llm.model == "gemini-test"
    assert config.llm.api_key_env == "TEST_GEMINI_KEY"
    assert config.llm.temperature == 0.35
    assert config.llm.max_output_tokens == 4000
    assert config.llm.max_frames == 12

    
def test_config_includes_narration_language_and_duration_targets(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
narration:
  language: english
  script: latin
  target_duration_seconds: 120
  min_duration_seconds: 105
  max_duration_seconds: 135
  words_per_minute: 150
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.narration.language == "english"
    assert config.narration.script == "latin"
    assert config.narration.target_duration_seconds == 120
    assert config.narration.min_duration_seconds == 105
    assert config.narration.max_duration_seconds == 135
    assert config.narration.words_per_minute == 150


def test_config_includes_tts_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
tts:
  provider: command
  voice: narrator
  command:
    - python
    - tools/tts_runner.py
    - "{text_file}"
    - "{output_file}"
  timeout_seconds: 90
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.tts.provider == "command"
    assert config.tts.voice == "narrator"
    assert config.tts.command == (
        "python",
        "tools/tts_runner.py",
        "{text_file}",
        "{output_file}",
    )
    assert config.tts.timeout_seconds == 90
