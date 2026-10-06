from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from ...metadata.models import AnimeMetadata
from ...metadata.transport import HttpTransport
from ...models import EpisodeAvailability, EpisodeRef, MediaSource, utc_now
from ..base import Provider, ProviderHealth


class AnivaultProvider(Provider):
    """Catalog/availability adapter for the AniVault REST API."""

    name = "anivault"

    def __init__(self, api_base_url: str, transport: HttpTransport | None = None) -> None:
        if not api_base_url.strip():
            raise ValueError("AniVault api_base_url cannot be empty")
        self.base_url = api_base_url.rstrip("/")
        self.transport = transport or HttpTransport()

    @staticmethod
    def _anilist_id(anime_id: str) -> int:
        value = anime_id.strip().lower()
        if value.startswith("anilist:"):
            value = value.split(":", 1)[1]
        if not value.isdigit():
            raise ValueError("AniVault requires an AniList ID (for example anilist:20)")
        return int(value)

    @staticmethod
    def _title_values(item: dict[str, Any]) -> tuple[str, ...]:
        values: list[str] = []
        title = item.get("title")
        if isinstance(title, str):
            values.append(title)
        elif isinstance(title, dict):
            values.extend(str(title[k]) for k in ("english", "romaji", "native") if title.get(k))
        values.extend(str(entry.get("title")) for entry in item.get("titles", []) if isinstance(entry, dict) and entry.get("title"))
        return tuple(dict.fromkeys(values))

    @classmethod
    def _normalize_anime(cls, item: dict[str, Any]) -> AnimeMetadata:
        titles = cls._title_values(item)
        title = titles[0] if titles else str(item.get("name") or "Unknown")
        anilist_id = item.get("anilistId") or item.get("anilist_id")
        mal_id = item.get("malId") or item.get("mal_id")
        identifier = f"mal:{mal_id}" if mal_id else f"anilist:{anilist_id}" if anilist_id else "anivault:unknown"
        metadata = AnimeMetadata(
            id=identifier,
            title=title,
            titles=titles,
            anilist_id=int(anilist_id) if str(anilist_id).isdigit() else None,
            mal_id=int(mal_id) if str(mal_id).isdigit() else None,
            format=item.get("type") or item.get("format"),
            status=item.get("status"),
            release_state="RELEASING" if str(item.get("status", "")).lower() in {"airing", "currently airing", "releasing"} else "UNKNOWN",
            season=item.get("season"),
            season_year=item.get("year") or item.get("seasonYear"),
            episodes=item.get("episodes") or item.get("episodeCount"),
            duration_minutes=item.get("duration"),
            start_date=item.get("aired_from") or item.get("startDate"),
            end_date=item.get("aired_to") or item.get("endDate"),
            description=item.get("synopsis") or item.get("description"),
            cover_image=(item.get("images") or {}).get("jpg", {}).get("large_image_url") if isinstance(item.get("images"), dict) else item.get("coverImage"),
            source_provider=cls.name,
            raw=item,
        )
        metadata.validate()
        return metadata

    def search(self, query: str) -> list[AnimeMetadata]:
        response = self.transport.request_json(f"{self.base_url}/api/search?q={quote_plus(query)}")
        raw = response.get("results", response.get("data", []))
        return [self._normalize_anime(item) for item in raw if isinstance(item, dict)]

    def get_anime(self, anime_id: str) -> AnimeMetadata:
        anilist_id = self._anilist_id(anime_id)
        response = self.transport.request_json(f"{self.base_url}/api/info?anilistId={anilist_id}")
        item = response.get("data", response)
        if not isinstance(item, dict) or not item:
            raise LookupError(f"AniVault anime not found: {anime_id}")
        item.setdefault("anilistId", anilist_id)
        return self._normalize_anime(item)

    def get_episodes(self, anime_id: str, season: int = 1) -> list[EpisodeRef]:
        del season
        anilist_id = self._anilist_id(anime_id)
        found: list[EpisodeRef] = []
        seen: set[tuple[int, str, str | None]] = set()
        for source in ("anikoto", "animeheaven"):
            try:
                response = self.transport.request_json(
                    f"{self.base_url}/api/episodes?anilistId={anilist_id}&source={source}"
                )
            except Exception:
                continue
            items = response.get("episodes", response.get("data", []))
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                number = item.get("number") or item.get("episode") or item.get("ep")
                if not isinstance(number, int) or number < 1:
                    continue
                language = str(item.get("type") or item.get("language") or "sub").lower()
                language = "dub" if language == "dub" else "sub"
                external_id = item.get("id") or item.get("episodeId") or item.get("episode_id")
                key = (number, language, str(external_id) if external_id is not None else None)
                if key in seen:
                    continue
                seen.add(key)
                found.append(EpisodeRef(
                    anime_id=f"anilist:{anilist_id}",
                    season=1,
                    episode=number,
                    language=language,
                    external_id=(f"{source}:{external_id}" if external_id is not None else source),
                ))
        return sorted(found, key=lambda item: (item.episode, item.language, item.external_id or ""))

    def resolve_episode(
        self,
        anime_id: str,
        episode_number: int,
        season: int = 1,
        language: str = "sub",
    ) -> EpisodeAvailability:
        try:
            candidates = [
                item for item in self.get_episodes(anime_id, season)
                if item.episode == episode_number and item.language == language
            ]
        except Exception as exc:
            return EpisodeAvailability(provider_status="TEMPORARILY_UNAVAILABLE", checked_at=utc_now(), error=str(exc))
        return EpisodeAvailability(
            metadata_exists=True,
            catalog_exists=bool(candidates),
            source_resolved=False,
            media_usable=False,
            processable=False,
            provider_status="AVAILABLE" if candidates else "EPISODE_UNAVAILABLE",
            checked_at=utc_now(),
            error=None if candidates else f"episode {episode_number} ({language}) is absent from AniVault catalog",
        )

    def get_source(self, episode: EpisodeRef) -> MediaSource:
        del episode
        raise NotImplementedError("AniVault source extraction is outside the current authorized-media boundary")

    def check_health(self) -> ProviderHealth:
        try:
            response = self.transport.request_json(f"{self.base_url}/api/health")
            status = str(response.get("status", "ok")).lower()
            healthy = status in {"ok", "healthy", "available"}
            return ProviderHealth(
                status="AVAILABLE" if healthy else "TEMPORARILY_UNAVAILABLE",
                provider=self.name,
                checked_at=utc_now(),
                detail=str(response.get("meta") or response.get("status") or status),
            )
        except Exception as exc:
            return ProviderHealth(status="TEMPORARILY_UNAVAILABLE", provider=self.name, checked_at=utc_now(), detail=str(exc))
