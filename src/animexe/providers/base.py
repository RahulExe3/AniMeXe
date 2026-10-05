from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..models import EpisodeAvailability, EpisodeRef, MediaSource, utc_now


@dataclass(frozen=True)
class ProviderHealth:
    status: str
    provider: str
    checked_at: str
    detail: str | None = None


class Provider(ABC):
    """Stable boundary between AniMeXe and an episode provider."""

    name: str

    @abstractmethod
    def search(self, query: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_anime(self, anime_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_episodes(self, anime_id: str, season: int = 1) -> list[EpisodeRef]:
        raise NotImplementedError

    @abstractmethod
    def resolve_episode(
        self,
        anime_id: str,
        episode_number: int,
        season: int = 1,
        language: str = "sub",
    ) -> EpisodeAvailability:
        raise NotImplementedError

    @abstractmethod
    def get_source(self, episode: EpisodeRef) -> MediaSource:
        raise NotImplementedError

    @abstractmethod
    def check_health(self) -> ProviderHealth:
        raise NotImplementedError
