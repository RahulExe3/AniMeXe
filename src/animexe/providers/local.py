from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import EpisodeAvailability, EpisodeRef, MediaSource, utc_now
from .base import Provider, ProviderHealth


class LocalProvider(Provider):
    """Development adapter for a file supplied to the pipeline."""

    name = "local"

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path.cwd()).resolve()

    def search(self, query: str) -> list[dict[str, Any]]:
        return []

    def get_anime(self, anime_id: str) -> dict[str, Any]:
        raise NotImplementedError("local provider does not supply metadata")

    def get_episodes(self, anime_id: str, season: int = 1) -> list[EpisodeRef]:
        raise NotImplementedError("local provider does not supply catalogs")

    def resolve_episode(
        self,
        anime_id: str,
        episode_number: int,
        season: int = 1,
        language: str = "sub",
    ) -> EpisodeAvailability:
        EpisodeRef(
            anime_id=anime_id,
            season=season,
            episode=episode_number,
            language=language,
        ).validate()
        return EpisodeAvailability(
            metadata_exists=True,
            catalog_exists=True,
            provider_status="AVAILABLE",
            checked_at=utc_now(),
        )

    def get_source(self, episode: EpisodeRef) -> MediaSource:
        if not episode.external_id:
            raise ValueError("EpisodeRef.external_id must contain a file path")

        path = Path(episode.external_id).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()

        if not path.is_file():
            raise FileNotFoundError(f"file not found: {path}")

        source = MediaSource(
            provider=self.name,
            protocol="file",
            reference=str(path),
            language=episode.language,
            capabilities=("random_access", "seekable"),
        )
        source.validate()
        return source

    def check_health(self) -> ProviderHealth:
        return ProviderHealth(
            status="AVAILABLE",
            provider=self.name,
            checked_at=utc_now(),
            detail=str(self.root),
        )
