from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AnimeMetadata:
    """Provider-independent anime identity and release metadata."""

    id: str
    title: str
    titles: tuple[str, ...] = ()
    anilist_id: int | None = None
    mal_id: int | None = None
    format: str | None = None
    status: str | None = None
    release_state: str = "UNKNOWN"
    season: str | None = None
    season_year: int | None = None
    episodes: int | None = None
    duration_minutes: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    cover_image: str | None = None
    source_provider: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("metadata id cannot be empty")
        if not self.title.strip():
            raise ValueError("metadata title cannot be empty")
        if self.episodes is not None and self.episodes < 0:
            raise ValueError("metadata episode count cannot be negative")


@dataclass(frozen=True)
class MetadataResult:
    metadata: AnimeMetadata | None
    provider: str
    error: str | None = None
