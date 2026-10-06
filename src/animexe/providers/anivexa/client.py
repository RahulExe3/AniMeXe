from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from ...metadata.models import AnimeMetadata
from ...metadata.transport import HttpTransport
from ...models import EpisodeAvailability, EpisodeRef, MediaSource, utc_now
from ..base import Provider, ProviderHealth


class AnivexaProvider(Provider):
    """Catalog/availability adapter for Anivexa.

    Source extraction is deliberately not implemented here. Anivexa exposes
    streaming/extractor routes; AniMeXe keeps those behind the authorized-media
    boundary rather than embedding bypass/proxy/decryption behavior.
    """

    name = "anivexa"

    def __init__(self, api_base_url: str, transport: HttpTransport | None = None) -> None:
        if not api_base_url.strip():
            raise ValueError("Anivexa api_base_url cannot be empty")
        self.base_url = api_base_url.rstrip("/")
        self.transport = transport or HttpTransport()

    @staticmethod
    def _anilist_id(anime_id: str) -> int:
        value = anime_id.strip().lower()
        if value.startswith("anilist:"):
            value = value.split(":", 1)[1]
        if not value.isdigit():
            raise ValueError("Anivexa requires an AniList ID (for example anilist:21)")
        return int(value)

    @staticmethod
    def _normalize_language(value: Any) -> str | None:
        if not value:
            return None
        normalized = str(value).lower().strip()
        if normalized in {"sub", "subtitle", "subbed"}:
            return "sub"
        if normalized in {"dub", "dubbed"}:
            return "dub"
        return normalized

    @classmethod
    def _episode_items(cls, response: dict[str, Any]) -> list[EpisodeRef]:
        """Normalize both current and provider-filtered /episodes responses."""
        anilist_id = cls._response_anilist_id(response)
        found: list[EpisodeRef] = []
        seen: set[tuple[int, str, str]] = set()

        provider_map = response.get("providers")
        if isinstance(provider_map, dict):
            sources = provider_map.items()
        else:
            sources = (
                (name, value)
                for name, value in response.items()
                if name not in {"page", "type", "mappings", "anilistId", "anilist_id", "id", "title"}
            )

        for provider_name, provider_data in sources:
            if not isinstance(provider_data, dict):
                continue
            grouped = provider_data.get("episodes")
            if isinstance(grouped, list):
                grouped = {"sub": grouped}
            if not isinstance(grouped, dict):
                continue

            for language in ("sub", "dub"):
                items = grouped.get(language, [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    number = item.get("number") or item.get("episode")
                    if not isinstance(number, int) or number < 1:
                        continue
                    external_id = item.get("id") or item.get("epSlug") or item.get("sourceNumber")
                    external_text = (
                        str(external_id) if external_id is not None else f"ep-{number}"
                    )
                    key = (number, language, f"{provider_name}:{external_text}")
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(
                        EpisodeRef(
                            anime_id=f"anilist:{anilist_id}" if anilist_id else "anilist:unknown",
                            season=1,
                            episode=number,
                            language=language,
                            external_id=f"{provider_name}:{external_text}",
                        )
                    )

        # Provider-filtered/current deployments can return a bare episode map.
        grouped = response.get("episodes")
        if isinstance(grouped, list):
            grouped = {"sub": grouped}
        if isinstance(grouped, dict):
            for language in ("sub", "dub"):
                for item in grouped.get(language, []) or []:
                    if not isinstance(item, dict):
                        continue
                    number = item.get("number") or item.get("episode")
                    if not isinstance(number, int) or number < 1:
                        continue
                    external_id = item.get("id") or item.get("epSlug") or item.get("sourceNumber")
                    external_text = str(external_id) if external_id is not None else f"ep-{number}"
                    key = (number, language, external_text)
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(
                        EpisodeRef(
                            anime_id=f"anilist:{anilist_id}" if anilist_id else "anilist:unknown",
                            season=1,
                            episode=number,
                            language=language,
                            external_id=external_text,
                        )
                    )

        found.sort(key=lambda item: (item.episode, item.language, item.external_id or ""))
        return found

    @staticmethod
    def _response_anilist_id(response: dict[str, Any]) -> int:
        value = response.get("anilistId") or response.get("anilist_id") or response.get("id")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return 0

    def search(self, query: str) -> list[AnimeMetadata]:
        del query
        raise NotImplementedError("Anivexa catalog adapter does not expose a search endpoint")

    def get_anime(self, anime_id: str) -> AnimeMetadata:
        del anime_id
        raise NotImplementedError("Use AniList metadata for Anivexa identity/details")

    def get_episodes(self, anime_id: str, season: int = 1) -> list[EpisodeRef]:
        del season
        anilist_id = self._anilist_id(anime_id)
        response = self.transport.request_json(f"{self.base_url}/episodes/{anilist_id}")
        response.setdefault("anilistId", anilist_id)
        return self._episode_items(response)

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
            return EpisodeAvailability(
                provider_status="TEMPORARILY_UNAVAILABLE",
                checked_at=utc_now(),
                error=str(exc),
            )
        return EpisodeAvailability(
            metadata_exists=True,
            catalog_exists=bool(candidates),
            source_resolved=False,
            media_usable=False,
            processable=False,
            provider_status="AVAILABLE" if candidates else "EPISODE_UNAVAILABLE",
            checked_at=utc_now(),
            error=None if candidates else f"episode {episode_number} ({language}) is absent from Anivexa catalog",
        )

    def get_source(self, episode: EpisodeRef) -> MediaSource:
        del episode
        raise NotImplementedError(
            "Anivexa stream/source extraction is outside the current authorized-media boundary"
        )

    def check_health(self) -> ProviderHealth:
        try:
            response = self.transport.request_json(self.base_url)
            return ProviderHealth(
                status="AVAILABLE",
                provider=self.name,
                checked_at=utc_now(),
                detail="root endpoint responded with JSON",
            )
        except Exception as exc:
            return ProviderHealth(
                status="TEMPORARILY_UNAVAILABLE",
                provider=self.name,
                checked_at=utc_now(),
                detail=str(exc),
            )
