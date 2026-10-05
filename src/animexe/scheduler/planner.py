from __future__ import annotations

from dataclasses import dataclass

from ..models import AnimeRecord, EpisodeRecord, SchedulerState, utc_now


@dataclass(frozen=True)
class JobPlan:
    anime_id: str
    episode_number: int
    reason: str


class Scheduler:
    """First deterministic scheduler slice.

    It does not perform production work. It only selects eligible episode jobs
    from persisted anime/episode state.
    """

    def __init__(self, state: SchedulerState) -> None:
        self.state = state

    def plan(
        self,
        anime: list[AnimeRecord],
        episodes: list[EpisodeRecord],
    ) -> list[JobPlan]:
        if self.state.successful_outputs_today >= self.state.daily_output_limit:
            return []

        active = [
            item for item in anime
            if item.active and item.status == "ACTIVE"
        ]
        candidates = active or [
            item for item in anime
            if item.status in {"DISCOVERED", "ACTIVE"}
            and item.release_state != "NOT_YET_RELEASED"
        ]

        if self.state.strategy == "priority":
            candidates.sort(key=lambda item: (-item.priority, item.title.lower()))
        else:
            candidates.sort(key=lambda item: (item.next_episode, item.title.lower()))

        plans: list[JobPlan] = []
        for record in candidates:
            if len(plans) >= self.state.daily_output_limit:
                break

            current = next(
                (
                    ep for ep in episodes
                    if ep.anime_id == record.id
                    and ep.episode_number == record.next_episode
                ),
                None,
            )

            if current is not None and current.status not in {"PENDING", "FAILED"}:
                continue

            plans.append(
                JobPlan(
                    anime_id=record.id,
                    episode_number=record.next_episode,
                    reason="next eligible episode",
                )
            )

        self.state.last_plan_at = utc_now()
        return plans
