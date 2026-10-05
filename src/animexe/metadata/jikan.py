from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from .models import AnimeMetadata
from .transport import HttpTransport


class JikanClient:
    """Read-only Jikan v4 metadata adapter."""

    ENDPOINT = "https://api.jikan.moe/v4"
    PROVIDER = "jikan"

    def __init__(self, transport: HttpTransport | None = None, endpoint: str | None = None) -> None:
        self.transport = transport or HttpTransport()
        self.endpoint = (endpoint or self.ENDPOINT).rstrip("/")

    @staticmethod
    def _titles(item: dict[str, Any]) -> tuple[str, ...]:
        values = [item.get("title"), item.get("title_english"), item.get("title_japanese")]
        values.extend(
            entry.get("title")
            for entry in item.get("titles", [])
            if isinstance(entry, dict)
        )
        seen: list[str] = []
        for title in values:
            if title and title not in seen:
                seen.append(title)
        return tuple(seen)

    @staticmethod
    def _release_state(status: str | None) -> str:
        normalized = (status or "").lower()
        if "currently airing" in normalized:
            return "RELEASING"
        if "finished" in normalized:
            return "FINISHED"
        if "not yet aired" in normalized:
            return "NOT_YET_RELEASED"
        if "on hiatus" in normalized:
            return "PAUSED"
        return "UNKNOWN"

    def _normalize(self, item: dict[str, Any]) -> AnimeMetadata:
        titles = self._titles(item)
        title = item.get("title") or (titles[0] if titles else "")
        image = ((item.get("images") or {}).get("jpg") or {}).get("large_image_url")             or ((item.get("images") or {}).get("jpg") or {}).get("image_url")

        metadata = AnimeMetadata(
            id=f"jikan:{item['mal_id']}",
            title=title,
            titles=titles,
            mal_id=item.get("mal_id"),
            format=item.get("type"),
            status=item.get("status"),
            release_state=self._release_state(item.get("status")),
            season=item.get("season"),
            season_year=item.get("year"),
            episodes=item.get("episodes"),
            duration_minutes=item.get("duration"),
            start_date=item.get("aired", {}).get("from"),
            end_date=item.get("aired", {}).get("to"),
            description=item.get("synopsis"),
            cover_image=image,
            source_provider=self.PROVIDER,
            raw=item,
        )
        metadata.validate()
        return metadata

    def search(self, query: str, limit: int = 10) -> list[AnimeMetadata]:
        url = f"{self.endpoint}/anime?q={quote_plus(query)}&limit={max(1, min(limit, 25))}"
        response = self.transport.request_json(url)
        return [self._normalize(item) for item in response.get("data", [])]

    def get_anime(self, mal_id: int | str) -> AnimeMetadata:
        response = self.transport.request_json(f"{self.endpoint}/anime/{int(mal_id)}")
        item = response.get("data")
        if not item:
            raise LookupError(f"Jikan anime not found: {mal_id}")
        return self._normalize(item)

    def get_episodes(self, mal_id: int | str, max_pages: int = 1) -> list[dict[str, Any]]:
        episodes: list[dict[str, Any]] = []
        for page in range(1, max(1, max_pages) + 1):
            response = self.transport.request_json(
                f"{self.endpoint}/anime/{int(mal_id)}/episodes?page={page}"
            )
            batch = response.get("data", [])
            episodes.extend(batch)
            pagination = response.get("pagination") or {}
            if not pagination.get("has_next_page"):
                break
        return episodes
