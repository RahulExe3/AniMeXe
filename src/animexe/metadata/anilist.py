from __future__ import annotations

from typing import Any

from .models import AnimeMetadata
from .transport import HttpTransport


class AniListClient:
    """Read-only AniList GraphQL metadata adapter."""

    ENDPOINT = "https://graphql.anilist.co"
    PROVIDER = "anilist"

    MEDIA_QUERY = """
    query ($id: Int, $search: String) {
      Media(id: $id, search: $search, type: ANIME) {
        id
        idMal
        title { romaji english native userPreferred }
        format
        status
        season
        seasonYear
        episodes
        duration
        startDate { year month day }
        endDate { year month day }
        description(asHtml: false)
        coverImage { large }
      }
    }
    """

    SEARCH_QUERY = """
    query ($search: String, $page: Int = 1, $perPage: Int = 10) {
      Page(page: $page, perPage: $perPage) {
        media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
          id
          idMal
          title { romaji english native userPreferred }
          format
          status
          season
          seasonYear
          episodes
          duration
          coverImage { large }
        }
      }
    }
    """

    def __init__(self, transport: HttpTransport | None = None, endpoint: str | None = None) -> None:
        self.transport = transport or HttpTransport()
        self.endpoint = endpoint or self.ENDPOINT

    @staticmethod
    def _date(value: dict[str, Any] | None) -> str | None:
        if not value:
            return None
        year = value.get("year")
        month = value.get("month")
        day = value.get("day")
        if not year:
            return None
        parts = [str(year)]
        if month:
            parts.append(f"{int(month):02d}")
        if day:
            parts.append(f"{int(day):02d}")
        return "-".join(parts)

    @staticmethod
    def _titles(value: dict[str, Any]) -> tuple[str, ...]:
        seen: list[str] = []
        for key in ("romaji", "english", "native", "userPreferred"):
            title = value.get(key)
            if title and title not in seen:
                seen.append(title)
        return tuple(seen)

    @staticmethod
    def _release_state(status: str | None) -> str:
        return {
            "NOT_YET_RELEASED": "NOT_YET_RELEASED",
            "RELEASING": "RELEASING",
            "FINISHED": "FINISHED",
            "CANCELLED": "UNAVAILABLE",
            "HIATUS": "PAUSED",
        }.get(status or "", "UNKNOWN")

    def _request(self, *, media_id: int | None = None, search: str | None = None) -> dict[str, Any]:
        variables = {"id": media_id, "search": search}
        if search is None:
            variables.pop("search")
        if media_id is None:
            variables.pop("id")
        response = self.transport.request_json(
            self.endpoint,
            method="POST",
            payload={"query": self.MEDIA_QUERY, "variables": variables}
            if media_id is not None
            else {"query": self.SEARCH_QUERY, "variables": {"search": search, "page": 1, "perPage": 10}},
        )
        if response.get("errors"):
            raise RuntimeError(str(response["errors"]))
        return response

    def _normalize(self, media: dict[str, Any]) -> AnimeMetadata:
        titles = self._titles(media.get("title") or {})
        title = (media.get("title") or {}).get("userPreferred") or titles[0]
        item = AnimeMetadata(
            id=(
                f"mal:{media['idMal']}"
                if media.get("idMal")
                else f"anilist:{media['id']}"
            ),
            title=title,
            titles=titles,
            anilist_id=media.get("id"),
            mal_id=media.get("idMal"),
            format=media.get("format"),
            status=media.get("status"),
            release_state=self._release_state(media.get("status")),
            season=media.get("season"),
            season_year=media.get("seasonYear"),
            episodes=media.get("episodes"),
            duration_minutes=media.get("duration"),
            start_date=self._date(media.get("startDate")),
            end_date=self._date(media.get("endDate")),
            description=media.get("description"),
            cover_image=(media.get("coverImage") or {}).get("large"),
            source_provider=self.PROVIDER,
            raw=media,
        )
        item.validate()
        return item

    def search(self, query: str) -> list[AnimeMetadata]:
        response = self._request(search=query)
        media = ((response.get("data") or {}).get("Page") or {}).get("media") or []
        return [self._normalize(item) for item in media]

    def get_anime(self, anime_id: int | str) -> AnimeMetadata:
        response = self._request(media_id=int(anime_id))
        media = (response.get("data") or {}).get("Media")
        if not media:
            raise LookupError(f"AniList anime not found: {anime_id}")
        return self._normalize(media)
