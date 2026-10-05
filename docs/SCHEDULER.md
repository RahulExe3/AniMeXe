# AniMeXe Scheduler

> Build the engine once. Let the scheduler decide what runs next.

## Defaults
- max_active_anime: 4
- daily_output_limit: 2
- count_mode: successful_outputs
- strategy: balanced

## Anime library vs active slots

The four-anime limit is an active-slot limit, not a requirement for the user to manually choose exactly four anime.

AniMeXe maintains an anime library containing everything it knows about. The scheduler automatically promotes eligible anime into active slots and replaces them when a slot becomes unproductive or available for another candidate.

Anime Library -> Release/Episode Monitor -> Candidate Pool -> Active Slots (max 4) -> Episode Queue -> Production

Manual selection may be supported as an optional override, but automatic selection is the default behavior.

## Anime discovery

AniMeXe should support both:
- Automatic discovery through configured metadata providers.
- Manual addition of an anime.

Discovery creates or updates an anime-library record. Discovery does not automatically mean the anime should consume an active slot.

Metadata providers should expose enough information to determine identity, season, release status, episode count when known, and airing information when available.

## Release-state eligibility

AniMeXe must distinguish anime that have not started, anime that are currently airing, anime that have finished, and anime for which release information is temporarily unavailable.

Lifecycle:

DISCOVERED -> NOT_YET_RELEASED -> RELEASING -> FINISHED

Operational states such as PAUSED, UNAVAILABLE, or ARCHIVED may coexist with these release states.

A NOT_YET_RELEASED anime must not consume an active production slot. When its premiere becomes available, the anime becomes eligible according to configured policy.

## Episode monitoring

Episode availability is monitored independently from active-slot selection.

For an airing anime, AniMeXe periodically refreshes provider metadata and compares the known episode set against persisted state.

Example:

Demon Slayer
Processed: 1-8
Latest known: 8
Next expected: 9
Status: RELEASING
    -> no episode 9 yet
WAITING_FOR_NEXT_EPISODE
    -> provider reports episode 9
Episode 9 -> PENDING

AniMeXe must not require the user to manually add every newly released episode.

Persist at minimum:
- latest known episode
- next expected episode
- release status
- next airing timestamp when available
- last metadata refresh
- provider/source used for the observation
- newly detected episode numbers
- availability errors or stale-provider conditions

A temporary provider failure must not be interpreted as an anime having no new episode.

## Candidate pool

An anime can remain in the library without being active.

An anime is an eligible candidate when, subject to configuration:
- it has started airing or is finished;
- the next required episode exists and is available;
- it is not paused, archived, or permanently unavailable;
- the episode is not already completed;
- it has not violated a scheduling constraint;
- processing capacity and daily limits permit consideration.

An airing anime that has caught up to its latest available episode remains in the library but becomes WAITING_FOR_NEXT_EPISODE rather than blocking an active slot.

## Dynamic active-slot management

The scheduler maintains up to max_active_anime active anime.

If an active anime catches up and has no next episode:

Jujutsu Kaisen -> WAITING_FOR_NEXT_EPISODE
Active productive slots: 3/4
    -> select best eligible candidate
Attack on Titan -> ACTIVE
Active slots: 4/4

A slot may also be freed when an anime is completed, paused, archived, or becomes unavailable under configured policy.

If the waiting anime later receives a new episode, it returns to the candidate pool. The scheduler decides whether to reactivate it using the configured strategy.

The system must not assume that the same four anime remain active forever.

## Episode continuity

If the current episode is 8, episode 9 cannot be selected before episode 8 succeeds.

Episode 8 remains current until the success checkpoint. Retry is allowed.

For airing anime, catching up means current episode equals latest available, then the anime waits for the next episode. When a new episode is detected, it becomes PENDING.

## Daily slots

The daily limit counts successful production outputs. Failed attempts do not consume a slot by default.

The active-anime limit and daily-output limit are separate:
- max_active_anime controls active scheduling attention.
- daily_output_limit controls successful episode outputs per day.

## Strategies

Balanced distributes recent successful slots fairly. Priority gives higher-priority anime stronger weight without permanently starving others. Flexible adds controlled variation while preserving continuity, limits, availability, and failure recovery.

Strategies operate over the candidate pool, not a manually fixed list of four anime.

## Job claiming

Claim atomically from PENDING to QUEUED, then process. Before claiming, check current episode, anime status, remaining budget, and whether another worker already owns the job.

## Failure

PROCESSING -> FAILED. Record stage, error, timestamp, attempt, provider, and configuration fingerprint. The same episode can be retried later.

A failed current episode remains the required next episode; the scheduler must not skip it merely to process a later episode from the same anime.

## Success

PROCESSING -> RENDERED -> READY. Only then increment successful output count, record completion, advance the next episode, and persist state.

After advancement, refresh eligibility. If no next episode is available, the anime may enter WAITING_FOR_NEXT_EPISODE and another candidate may fill the active slot.

## Determinism

Given the same state, date, configuration, availability, and strategy, scheduler decisions should be reproducible. Controlled randomness must record its seed/context.

## Required tests

Test:
- automatic discovery into the library;
- not-yet-released anime excluded from active slots;
- premiere transition into eligibility;
- airing anime waiting for the next episode;
- detection of a newly released episode;
- temporary provider failure not clearing known state;
- four active anime;
- fewer than four eligible candidates;
- dynamic replacement of waiting/completed/unavailable slots;
- re-entry after a new episode;
- daily limit reached;
- failed jobs;
- unavailable providers;
- paused/completed anime;
- episode gaps;
- priority strategy;
- fairness strategy;
- concurrent claim prevention;
- restart recovery.
