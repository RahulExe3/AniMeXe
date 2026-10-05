from pathlib import Path

from animexe.models import AnimeRecord, EpisodeRecord
from animexe.state import StateStore


def test_state_store_initializes_and_round_trips(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "data")
    store.ensure()

    anime = AnimeRecord(id="demo-s1", title="Demo Anime", status="ACTIVE", release_state="RELEASING")
    store.save_anime(anime)

    episode = EpisodeRecord(id="demo-s1-e1", anime_id="demo-s1", episode_number=1)
    store.save_episode(episode)

    loaded_anime = store.list_anime()
    loaded_episodes = store.list_episodes()

    assert loaded_anime[0].title == "Demo Anime"
    assert loaded_episodes[0].episode_number == 1
    assert (tmp_path / "data" / "anime.json").exists()


def test_state_store_writes_valid_json(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "data")
    store.ensure()
    payload = (tmp_path / "data" / "scheduler.json").read_text(encoding="utf-8")
    assert '"schema_version": 1' in payload


def test_state_store_loads_legacy_episode_without_analysis_manifest(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "data")
    store.ensure()
    path = tmp_path / "data" / "episodes.json"
    path.write_text(
        '{"schema_version": 1, "items": [{"id": "legacy-e1", "anime_id": "legacy", '
        '"episode_number": 1, "status": "PENDING", "attempts": 0, '
        '"current_checkpoint": "input", "failure_reason": null, '
        '"provider": null, "source_reference": null, "render_output": null, '
        '"created_at": "2026-10-06T00:00:00+00:00", '
        '"updated_at": "2026-10-06T00:00:00+00:00"}]}',
        encoding="utf-8",
    )

    episodes = store.list_episodes()

    assert episodes[0].id == "legacy-e1"
    assert episodes[0].analysis_manifest is None
