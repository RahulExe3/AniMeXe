from __future__ import annotations

from dataclasses import dataclass

from .anilist import AniListClient
from .jikan import JikanClient
from .models import AnimeMetadata, MetadataResult


@dataclass
class MetadataService:
    """Resolve metadata through AniList first, then Jikan."""

    anilist: AniListClient
    jikan: JikanClient

    @classmethod
    def create(
        cls,
        *,
        anilist_endpoint: str | None = None,
        jikan_base_url: str | None = None,
    ) -> "MetadataService":
        return cls(
            AniListClient(endpoint=anilist_endpoint),
            JikanClient(endpoint=jikan_base_url),
        )

    def search(self, query: str, limit: int = 10) -> list[MetadataResult]:
        results: list[MetadataResult] = []

        try:
            primary = self.anilist.search(query)
            for item in primary[:limit]:
                results.append(MetadataResult(item, "anilist"))
        except Exception as exc:
            results.append(MetadataResult(None, "anilist", str(exc)))

        if results and any(item.metadata for item in results):
            return results

        try:
            fallback = self.jikan.search(query, limit=limit)
            results.extend(MetadataResult(item, "jikan") for item in fallback[:limit])
        except Exception as exc:
            results.append(MetadataResult(None, "jikan", str(exc)))

        return results

    def get_anime(self, provider: str, external_id: int | str) -> AnimeMetadata:
        normalized = provider.strip().lower()
        if normalized == "anilist":
            return self.anilist.get_anime(external_id)
        if normalized == "jikan":
            return self.jikan.get_anime(external_id)
        raise KeyError(f"unsupported metadata provider: {provider}")
