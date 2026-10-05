from animexe.models import AnimeRecord, EpisodeRecord, SchedulerState
from animexe.scheduler import Scheduler


def test_scheduler_selects_next_eligible_episode() -> None:
    state = SchedulerState(max_active_anime=4, daily_output_limit=2)
    anime = [
        AnimeRecord(
            id="a",
            title="Anime A",
            status="ACTIVE",
            release_state="RELEASING",
            active=True,
            next_episode=3,
        ),
        AnimeRecord(
            id="b",
            title="Anime B",
            status="ACTIVE",
            release_state="RELEASING",
            active=True,
            next_episode=2,
        ),
    ]
    episodes = [
        EpisodeRecord(id="a-e3", anime_id="a", episode_number=3, status="PENDING"),
    ]

    plans = Scheduler(state).plan(anime, episodes)

    assert [(item.anime_id, item.episode_number) for item in plans] == [
        ("b", 2)
    ]


def test_scheduler_respects_daily_limit() -> None:
    state = SchedulerState(
        max_active_anime=4,
        daily_output_limit=2,
        successful_outputs_today=2,
    )
    anime = [
        AnimeRecord(
            id="a",
            title="Anime A",
            status="ACTIVE",
            release_state="RELEASING",
            active=True,
        )
    ]

    assert Scheduler(state).plan(anime, []) == []
