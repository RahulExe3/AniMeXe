from pathlib import Path

from animexe.metadata import MetadataLibrary
from animexe.metadata.models import AnimeMetadata
from animexe.state import StateStore


def test_metadata_library_upserts_by_mal_identity(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "data")
    store.ensure()
    library = MetadataLibrary(store)

    first = library.upsert(
        AnimeMetadata(
            id="mal:100",
            title="Demo",
            mal_id=100,
            anilist_id=200,
            episodes=12,
            season="FALL",
            season_year=2026,
            release_state="RELEASING",
            source_provider="anilist",
        )
    )

    second = library.upsert(
        AnimeMetadata(
            id="mal:100",
            title="Demo Updated",
            mal_id=100,
            anilist_id=200,
            episodes=13,
            release_state="RELEASING",
            source_provider="jikan",
        )
    )

    records = store.list_anime()

    assert len(records) == 1
    assert first.id == second.id == "mal:100"
    assert records[0].title == "Demo Updated"
    assert records[0].episode_count == 13
    assert records[0].latest_known_episode == 13
