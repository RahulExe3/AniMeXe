# AniMeXe Metadata Layer

The metadata layer answers questions about anime identity, seasons, episode counts, release state, and titles. It does not establish media availability.

## Provider order

**AniList** is the primary identity/metadata provider.

**Jikan** is the fallback metadata provider.

AniList uses its GraphQL endpoint and accepts POST requests containing a query and variables. Jikan exposes a read-only REST API with anime detail and episode endpoints. These integrations are intentionally isolated behind AniMeXe's normalized metadata model.

## Normalized model

```text
AnimeMetadata
├── provider-independent id
├── title + aliases
├── AniList ID
├── MAL ID
├── format
├── release status
├── release state
├── season + season year
├── episode count
├── duration
├── start/end dates
├── description
└── cover image
```

The important rule is:

```text
metadata exists
    ≠
episode catalog exists
    ≠
media source exists
    ≠
media is usable
```

That separation prevents a metadata fallback from falsely telling the scheduler that an episode can be processed.

## CLI

```bash
python -m animexe metadata search "Mushoku Tensei"
python -m animexe metadata search "One Piece" --limit 5
python -m animexe metadata get anilist 20958
python -m animexe metadata get jikan 21
```

The CLI loads `config/config.yml` when present and falls back to `config/config.example.yml`.

## Integration rules

Metadata adapters must:

- return only normalized AniMeXe objects;
- keep provider-specific JSON inside the adapter;
- preserve AniList/MAL identifiers for cross-provider mapping;
- map release state explicitly;
- tolerate missing optional fields;
- treat provider errors as provider errors, not as proof that an anime is unavailable;
- remain read-only.

## Next metadata work

The next layer will connect normalized metadata to the persistent anime library:

```text
AniList/Jikan
      ↓
AnimeMetadata
      ↓
library upsert
      ↓
release monitor
      ↓
candidate pool
```

The media-provider layer remains separate and starts with Kuhi.

Reference: AniList GraphQL and Media documentation; Jikan REST API documentation.