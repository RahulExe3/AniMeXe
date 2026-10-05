from __future__ import annotations

from animexe.models import AnimeRecord, utc_now
from animexe.state import StateStore

from .models import AnimeMetadata


class MetadataLibrary:
    """Upsert normalized metadata into the persistent anime library."""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def upsert(self, metadata: AnimeMetadata) -> AnimeRecord:
        metadata.validate()
        records = self.store.list_anime()

        existing = next(
            (
                item
                for item in records
                if item.id == metadata.id
                or (
                    metadata.mal_id is not None
                    and item.mal_id == metadata.mal_id
                )
                or (
                    metadata.anilist_id is not None
                    and item.anilist_id == metadata.anilist_id
                )
            ),
            None,
        )

        if existing is None:
            record = AnimeRecord(
                id=metadata.id,
                title=metadata.title,
                season=1,
                status="DISCOVERED",
                release_state=metadata.release_state,
                latest_known_episode=metadata.episodes or 0,
                next_episode=1,
                discovery_source=metadata.source_provider,
                anilist_id=metadata.anilist_id,
                mal_id=metadata.mal_id,
                format=metadata.format,
                season_name=metadata.season,
                season_year=metadata.season_year,
                episode_count=metadata.episodes,
                last_metadata_sync_at=utc_now(),
            )
        else:
            existing.title = metadata.title
            existing.release_state = metadata.release_state
            existing.discovery_source = metadata.source_provider or existing.discovery_source
            existing.anilist_id = metadata.anilist_id or existing.anilist_id
            existing.mal_id = metadata.mal_id or existing.mal_id
            existing.format = metadata.format or existing.format
            existing.season_name = metadata.season or existing.season_name
            existing.season_year = metadata.season_year or existing.season_year
            if metadata.episodes is not None:
                existing.episode_count = metadata.episodes
                existing.latest_known_episode = max(
                    existing.latest_known_episode,
                    metadata.episodes,
                )
            existing.last_metadata_sync_at = utc_now()
            record = existing

        self.store.save_anime(record)
        return record
