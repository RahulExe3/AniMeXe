# AniMeXe Providers

## Provider architecture
Providers are adapters. They translate external APIs into normalized AniMeXe objects. The scheduler, story engine, scene matcher, and renderer must not depend on provider-specific response formats.

## Provider categories
- Metadata: AniList, Jikan, and optional TMDB.
- Episode/media: Kitsune-compatible API, official/free sources where available, and local/manual input.
- Local: mandatory for development and deterministic testing.

## Kitsune adapter
Kitsune is the first external episode-provider integration.

The adapter lives under src/providers/kitsune and should integrate with the API contract rather than the Kitsune web UI.

Internal operations:
- search(query)
- get_anime(anime_id)
- get_episodes(anime_id, season)
- resolve_episode(anime_id, episode_number, language)
- get_source(episode_reference)

The configured API base URL is provided through KITSUNE_API_BASE_URL or project configuration. Do not hard-code one deployment.

## Kitsune data normalization
The adapter should normalize the concepts demonstrated by the Kitsune frontend: anime suggestions, anime details, episode lists, sub/dub availability, provider/server identifiers, stream sources, subtitle files, and intro/outro timestamps.

Exact upstream endpoint paths are implementation details and must be verified against the configured API before an integration is called workflow-tested.

## Normalized episode contract
Every provider should produce an object containing anime ID, title, season, episode number, episode title, optional duration, source provider, source reference, subtitles, and optional intro/outro intervals.

The renderer consumes this normalized object only.

## Provider health
Adapters must distinguish available, temporarily unavailable, episode unavailable, invalid response, rate limited, and configuration/authentication failure.

Provider failure must not corrupt anime or episode state.

## Fallback
Primary provider -> metadata fallback -> another configured compatible source -> local/manual input or pending state.

Finding metadata does not mean that usable media exists.

## Provider tests
Minimum tests: search normalization, detail normalization, episode normalization, sub/dub mapping, source normalization, subtitle normalization, intro/outro normalization, malformed responses, timeout/error handling, and one manually verified real integration run.