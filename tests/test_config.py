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


def test_config_includes_provider_fallbacks(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
provider:
  name: kuhi
  api_base_url: https://kuhi.example
provider_fallbacks:
  - name: anivexa
    api_base_url: https://anivexa.example
  - name: anivault
    api_base_url: https://anivault.example
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert [item.name for item in config.provider_fallbacks] == ["anivexa", "anivault"]
    assert config.provider_fallbacks[0].api_base_url == "https://anivexa.example"



def test_config_includes_gemini_thinking_level(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
llm:
  thinking_level: low
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.llm.thinking_level == "low"


def test_config_accepts_gemini_tts(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
tts:
  provider: gemini
  model: gemini-3.8-flash-tts
  api_key_env: TEST_GEMINI_KEY
  voice: Kore
  style: natural narrator
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.tts.provider == "gemini"
    assert config.tts.model == "gemini-3.8-flash-tts"
    assert config.tts.api_key_env == "TEST_GEMINI_KEY"
    assert config.tts.voice == "Kore"



def test_config_includes_audio_bgm_controls(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text(
        """
project:
  name: AniMeXe
audio:
  bgm: true
  music_dir: custom/music
  bgm_volume: 0.15
  bgm_ducking_ratio: 6
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.audio.bgm is True
    assert config.audio.music_dir == "custom/music"
    assert config.audio.bgm_volume == 0.15
    assert config.audio.bgm_ducking_ratio == 6
