from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

EPISODE_STATES = (
    "PENDING",
    "QUEUED",
    "PROCESSING",
    "RENDERED",
    "READY",
    "PUBLISHED",
    "FAILED",
)

ANIME_STATES = (
    "DISCOVERED",
    "ACTIVE",
    "PAUSED",
    "COMPLETED",
    "WAITING_FOR_NEXT_EPISODE",
    "FAILED",
    "UNAVAILABLE",
    "ARCHIVED",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class AnimeRecord:
    id: str
    title: str
    season: int = 1
    status: str = "DISCOVERED"
    release_state: str = "NOT_YET_RELEASED"
    latest_known_episode: int = 0
    next_episode: int = 1
    priority: int = 0
    discovery_source: str = "manual"
    active: bool = False
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("anime id cannot be empty")
        if not self.title.strip():
            raise ValueError("anime title cannot be empty")
        if self.season < 1:
            raise ValueError("anime season must be >= 1")
        if self.next_episode < 1:
            raise ValueError("anime next_episode must be >= 1")
        if self.status not in ANIME_STATES:
            raise ValueError(f"unsupported anime state: {self.status}")


@dataclass
class EpisodeRecord:
    id: str
    anime_id: str
    episode_number: int
    status: str = "PENDING"
    attempts: int = 0
    current_checkpoint: str = "input"
    failure_reason: str | None = None
    provider: str | None = None
    source_reference: str | None = None
    render_output: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("episode id cannot be empty")
        if not self.anime_id.strip():
            raise ValueError("episode anime_id cannot be empty")
        if self.episode_number < 1:
            raise ValueError("episode number must be >= 1")
        if self.status not in EPISODE_STATES:
            raise ValueError(f"unsupported episode state: {self.status}")


@dataclass
class SchedulerState:
    max_active_anime: int = 4
    daily_output_limit: int = 2
    strategy: str = "balanced"
    successful_outputs_today: int = 0
    last_reset_date: str | None = None
    last_plan_at: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        if self.max_active_anime < 1:
            raise ValueError("max_active_anime must be >= 1")
        if self.daily_output_limit < 1:
            raise ValueError("daily_output_limit must be >= 1")
        if self.strategy not in {"balanced", "priority", "flexible"}:
            raise ValueError(f"unsupported scheduler strategy: {self.strategy}")


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
