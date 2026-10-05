# AniMeXe Scheduler

> Build the engine once. Let the scheduler decide what runs next.

## Defaults
- max_active_anime: 4
- daily_output_limit: 2
- count_mode: successful_outputs
- strategy: balanced

## Anime state
Each anime/season stores stable identity, current episode, completed episodes, failed episodes, status, priority, last selected time, and last successful time.

## Episode continuity
If the current episode is 8, episode 9 cannot be selected. Episode 8 remains current until it reaches the success checkpoint. Retry is allowed.

## Daily slots
The daily limit counts successful production outputs. Failed attempts do not consume a slot by default.

Example: limit 2, job A fails, B succeeds, C succeeds. Successful outputs equal 2 and scheduling stops.

## Strategies
Balanced distributes recent successful slots fairly. Priority gives higher-priority anime stronger weight without permanently starving others. Flexible adds controlled variation while preserving continuity, limits, and failure recovery.

## Job claiming
Claim atomically from PENDING to QUEUED, then process. Before claiming, check current episode, anime status, remaining budget, and whether another worker already owns the job.

## Failure
PROCESSING -> FAILED. Record stage, error, timestamp, attempt, provider, and configuration fingerprint. The same episode can be retried later.

## Success
PROCESSING -> RENDERED -> READY. Only then increment successful output count, record completion, advance the next episode, and persist state.

## Determinism
Given the same state, date, configuration, availability, and strategy, scheduler decisions should be reproducible. Controlled randomness must record its seed/context.

## Required tests
Test four active anime, fewer than four, daily limit reached, failed jobs, unavailable providers, paused/completed anime, episode gaps, priority strategy, fairness strategy, concurrent claim prevention, and restart recovery.