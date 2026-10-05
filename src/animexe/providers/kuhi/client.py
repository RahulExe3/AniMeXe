from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from ...metadata.models import AnimeMetadata
from ...metadata.transport import HttpTransport
from ...models import EpisodeAvailability, EpisodeRef, MediaSource, utc_now
from ..base import Provider, ProviderHealth


class KuhiProvider(Provider):
    """Normalized client for the Kuhi REST catalog boundary.

    Kuhi's current public project exposes anime search, info, episode catalogs,
    provider health, and stream extraction. AniMeXe intentionally integrates
    only the catalog/health boundary here. Stream extraction is kept separate
    until an authorized media source is selected for processing.
    """

    name = "kuhi"

    def __init__(
        self,
        api_base_url: str,
        transport: HttpTransport | None = None,
    ) -> None:
        if not api_base_url.strip():
            raise ValueError("Kuhi api_base_url cannot be empty")
        self.base_url = api_base_url.rstrip("/")
        self.transport = transport or HttpTransport()

    @staticmethod
    def _release_state(status: str | None) -> str:
        return {
            "NOT_YET_RELEASED": "NOT_YET_RELEASED",
            "RELEASING": "RELEASING",
            "FINISHED": "FINISHED",
            "CANCELLED": "UNAVAILABLE",
            "HIATUS": "PAUSED",
        }.get(status or "", "UNKNOWN")

    @staticmethod
    def _titles(item: dict[str, Any]) -> tuple[str, ...]:
        values = []
        title = item.get("title") or {}
        if isinstance(title, dict):
            values.extend(
                title.get(key)
                for key in ("userPreferred", "english", "romaji", "native")
            )
        seen: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.append(value)
        return tuple(seen)

    @classmethod
    def _normalize_anime(cls, item: dict[str, Any]) -> AnimeMetadata:
        titles = cls._titles(item)
        title = (item.get("title") or {}).get("userPreferred") if isinstance(item.get("title"), dict) else None
        title = title or (titles[0] if titles else "Unknown")

        metadata = AnimeMetadata(
            id=(
                f"mal:{item['idMal']}"
                if item.get("idMal")
                else f"anilist:{item['id']}"
            ),
            title=title,
            titles=titles,
            anilist_id=item.get("id"),
            mal_id=item.get("idMal"),
            format=item.get("format"),
            status=item.get("status"),
            release_state=cls._release_state(item.get("status")),
            season=item.get("season"),
            season_year=item.get("seasonYear"),
            episodes=item.get("episodes"),
            duration_minutes=item.get("duration"),
            start_date=cls._date(item.get("startDate")),
            end_date=cls._date(item.get("endDate")),
            description=item.get("description"),
            cover_image=(item.get("coverImage") or {}).get("large"),
            source_provider=cls.name,
            raw=item,
        )
        metadata.validate()
        return metadata

    @staticmethod
    def _date(value: dict[str, Any] | None) -> str | None:
        if not value:
            return None
        year = value.get("year")
        if not year:
            return None
        month = value.get("month")
        day = value.get("day")
        parts = [str(year)]
        if month:
            parts.append(f"{int(month):02d}")
        if day:
            parts.append(f"{int(day):02d}")
        return "-".join(parts)

    @staticmethod
    def _anilist_id(anime_id: str) -> int:
        value = anime_id.strip().lower()
        if value.startswith("anilist:"):
            value = value.split(":", 1)[1]
        if not value.isdigit():
            raise ValueError(
                "Kuhi catalog endpoints require an AniList ID "
                "(for example anilist:21 or 21)"
            )
        return int(value)

    def search(self, query: str) -> list[AnimeMetadata]:
        response = self.transport.request_json(
            f"{self.base_url}/anime/search?query={quote_plus(query)}&page=1&per_page=20"
        )
        return [
            self._normalize_anime(item)
            for item in response.get("results", [])
            if isinstance(item, dict)
        ]

    def get_anime(self, anime_id: str) -> AnimeMetadata:
        anilist_id = self._anilist_id(anime_id)
        response = self.transport.request_json(
            f"{self.base_url}/anime/info/{anilist_id}"
        )
        if not response:
            raise LookupError(f"Kuhi anime not found: {anime_id}")
        return self._normalize_anime(response)

    def get_episodes(self, anime_id: str, season: int = 1) -> list[EpisodeRef]:
        del season
        anilist_id = self._anilist_id(anime_id)
        response = self.transport.request_json(
            f"{self.base_url}/anime/episodes/{anilist_id}"
        )

        episodes: list[EpisodeRef] = []
        seen: set[tuple[int, str]] = set()
        providers = response.get("providers", {}) if isinstance(response, dict) else {}
        for provider_name, provider_data in providers.items():
            if not isinstance(provider_data, dict):
                continue
            grouped = provider_data.get("episodes", {})
            if not isinstance(grouped, dict):
                continue
            for language in ("sub", "dub"):
                for item in grouped.get(language, []) or []:
                    if not isinstance(item, dict):
                        continue
                    number = item.get("number")
                    if not isinstance(number, int) or number < 1:
                        continue
                    key = (number, language)
                    if key in seen:
                        continue
                    seen.add(key)
                    episodes.append(
                        EpisodeRef(
                            anime_id=f"anilist:{anilist_id}",
                            season=1,
                            episode=number,
                            language=language,
                            external_id=item.get("id"),
                        )
                    )

        episodes.sort(key=lambda item: (item.episode, item.language))
        return episodes

    def resolve_episode(
        self,
        anime_id: str,
        episode_number: int,
        season: int = 1,
        language: str = "sub",
    ) -> EpisodeAvailability:
        candidates = [
            item
            for item in self.get_episodes(anime_id, season)
            if item.episode == episode_number
            and item.language == language
        ]

        return EpisodeAvailability(
            metadata_exists=True,
            catalog_exists=bool(candidates),
            source_resolved=False,
            media_usable=False,
            processable=False,
            provider_status="AVAILABLE" if candidates else "EPISODE_UNAVAILABLE",
            checked_at=utc_now(),
            error=(
                None
                if candidates
                else f"episode {episode_number} ({language}) is absent from Kuhi catalog"
            ),
        )

    def get_source(self, episode: EpisodeRef) -> MediaSource:
        raise NotImplementedError(
            "Kuhi stream extraction is intentionally outside the current "
            "authorized-media boundary"
        )

    def check_health(self) -> ProviderHealth:
        try:
            response = self.transport.request_json(
                f"{self.base_url}/anime/providers/status"
            )
            available = response.get("available", [])
            detail = (
                f"available={', '.join(map(str, available))}"
                if isinstance(available, list)
                else "health endpoint returned"
            )
            return ProviderHealth(
                status="AVAILABLE",
                provider=self.name,
                checked_at=utc_now(),
                detail=detail,
            )
        except Exception as exc:
            return ProviderHealth(
                status="TEMPORARILY_UNAVAILABLE",
                provider=self.name,
                checked_at=utc_now(),
                detail=str(exc),
            )
