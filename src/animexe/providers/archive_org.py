from __future__ import annotations

from urllib.parse import quote

import requests

from ..metadata.models import AnimeMetadata
from ..models import EpisodeAvailability, EpisodeRef, MediaSource, utc_now
from .base import Provider, ProviderHealth


PUBLIC_DOMAIN_ALLOWLIST: dict[int, dict[str, str]] = {
    6654: {
        "identifier": "namakura-gatana-1917",
        "title": "Namakura Gatana (The Dull Sword)",
    },
    5875: {
        "identifier": "malkav-animes-kobutori",
        "title": "Kobutori",
    },
    3929: {
        "identifier": "ugokie-kori-no-tatehiki-1933",
        "title": "Ugokie Kori no Tatehiki",
    },
}


class ArchiveOrgProvider(Provider):
    """Allowlisted public-domain/openly licensed anime from Internet Archive."""

    name = "archive_org"

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def search(self, query: str) -> list[AnimeMetadata]:
        needle = query.strip().lower()
        results: list[AnimeMetadata] = []
        for anilist_id, item in PUBLIC_DOMAIN_ALLOWLIST.items():
            if needle and needle not in item["title"].lower():
                continue
            results.append(
                AnimeMetadata(
                    id=f"anilist:{anilist_id}",
                    title=item["title"],
                    titles=(item["title"],),
                    anilist_id=anilist_id,
                    source_provider=self.name,
                )
            )
        return results

    def get_anime(self, anime_id: str) -> AnimeMetadata:
        anilist_id = self._anilist_id(anime_id)
        item = PUBLIC_DOMAIN_ALLOWLIST.get(anilist_id)
        if item is None:
            raise LookupError(
                f"ArchiveOrg allowlist does not contain public-domain anime {anime_id}"
            )
        return AnimeMetadata(
            id=f"anilist:{anilist_id}",
            title=item["title"],
            titles=(item["title"],),
            anilist_id=anilist_id,
            source_provider=self.name,
        )

    def get_episodes(self, anime_id: str, season: int = 1) -> list[EpisodeRef]:
        del season
        anilist_id = self._anilist_id(anime_id)
        if anilist_id not in PUBLIC_DOMAIN_ALLOWLIST:
            return []
        return [
            EpisodeRef(
                anime_id=f"anilist:{anilist_id}",
                season=1,
                episode=1,
                language="sub",
                external_id=PUBLIC_DOMAIN_ALLOWLIST[anilist_id]["identifier"],
            )
        ]

    def resolve_episode(
        self,
        anime_id: str,
        episode_number: int,
        season: int = 1,
        language: str = "sub",
    ) -> EpisodeAvailability:
        available = bool(
            language == "sub"
            and season == 1
            and episode_number == 1
            and self._anilist_id(anime_id) in PUBLIC_DOMAIN_ALLOWLIST
        )
        return EpisodeAvailability(
            metadata_exists=available,
            catalog_exists=available,
            source_resolved=available,
            media_usable=available,
            processable=available,
            provider_status="AVAILABLE" if available else "EPISODE_UNAVAILABLE",
            checked_at=utc_now(),
        )

    def get_source(self, episode: EpisodeRef) -> MediaSource:
        anilist_id = self._anilist_id(episode.anime_id)
        item = PUBLIC_DOMAIN_ALLOWLIST.get(anilist_id)
        if item is None or episode.episode != 1 or episode.language != "sub":
            raise LookupError("requested episode is not in the public-domain allowlist")

        response = requests.get(
            f"https://archive.org/metadata/{quote(item['identifier'], safe='')}",
            timeout=self.timeout_seconds,
            headers={"User-Agent": "AniMeXe/0.1"},
        )
        response.raise_for_status()
        payload = response.json()
        files = payload.get("files", [])
        candidates = [
            entry
            for entry in files
            if isinstance(entry, dict)
            and str(entry.get("name", "")).lower().endswith(
                (".mp4", ".mkv", ".webm", ".mov")
            )
            and "__ia_thumb" not in str(entry.get("name", "")).lower()
        ]
        if not candidates:
            raise LookupError(f"Archive.org item {item['identifier']} has no video file")

        candidates.sort(
            key=lambda entry: (
                0 if str(entry["name"]).lower().endswith(".mp4") else 1,
                -int(entry.get("size") or 0),
            )
        )
        selected = candidates[0]
        filename = quote(str(selected["name"]), safe="/-_.~")
        return MediaSource(
            provider=self.name,
            protocol="other",
            reference=(
                f"https://archive.org/download/"
                f"{quote(item['identifier'], safe='')}/{filename}"
            ),
            quality=str(selected.get("format") or ""),
            language="sub",
            capabilities=("random_access", "seekable", "public_domain"),
            headers=(("User-Agent", "AniMeXe/0.1"),),
        )

    def check_health(self) -> ProviderHealth:
        try:
            response = requests.get(
                "https://archive.org/metadata/namakura-gatana-1917",
                timeout=self.timeout_seconds,
                headers={"User-Agent": "AniMeXe/0.1"},
            )
            response.raise_for_status()
            return ProviderHealth(
                status="AVAILABLE",
                provider=self.name,
                checked_at=utc_now(),
                detail="allowlisted Archive.org item metadata is reachable",
            )
        except Exception as exc:
            return ProviderHealth(
                status="TEMPORARILY_UNAVAILABLE",
                provider=self.name,
                checked_at=utc_now(),
                detail=str(exc),
            )

    @staticmethod
    def _anilist_id(anime_id: str) -> int:
        value = anime_id.strip().lower()
        if value.startswith("anilist:"):
            value = value.split(":", 1)[1]
        if not value.isdigit():
            raise ValueError("ArchiveOrgProvider requires an AniList ID")
        return int(value)


__all__ = ["ArchiveOrgProvider", "PUBLIC_DOMAIN_ALLOWLIST"]
