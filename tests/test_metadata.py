from animexe.metadata import AniListClient, JikanClient, MetadataService
from animexe.metadata.models import AnimeMetadata
from animexe.metadata.transport import MetadataTransportError


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request_json(self, url, *, method="GET", payload=None, headers=None):
        self.calls.append((url, method, payload))
        return self.responses[url]


def test_anilist_normalizes_identity_and_release_state() -> None:
    transport = FakeTransport({
        "https://graphql.anilist.co": {
            "data": {
                "Media": {
                    "id": 123,
                    "idMal": 456,
                    "title": {
                        "romaji": "Demo",
                        "english": "Demo English",
                        "native": "デモ",
                        "userPreferred": "Demo English",
                    },
                    "format": "TV",
                    "status": "RELEASING",
                    "season": "FALL",
                    "seasonYear": 2026,
                    "episodes": 12,
                    "duration": 24,
                    "startDate": {"year": 2026, "month": 10, "day": 1},
                    "endDate": None,
                    "description": "A demo.",
                    "coverImage": {"large": "https://img"},
                }
            }
        }
    })
    client = AniListClient(transport=transport)
    item = client.get_anime(123)

    assert item.id == "mal:456"
    assert item.mal_id == 456
    assert item.release_state == "RELEASING"
    assert item.season_year == 2026
    assert item.episodes == 12


def test_jikan_search_normalizes_status() -> None:
    url = "https://api.jikan.moe/v4/anime?q=Demo&limit=10"
    transport = FakeTransport({
        url: {
            "data": [{
                "mal_id": 456,
                "title": "Demo",
                "title_english": "Demo English",
                "title_japanese": "デモ",
                "titles": [],
                "type": "TV",
                "status": "Finished Airing",
                "season": "fall",
                "year": 2026,
                "episodes": 12,
                "duration": "24 min",
                "images": {"jpg": {"large_image_url": "https://img"}},
                "synopsis": "A demo.",
                "aired": {"from": "2026-01-01T00:00:00+00:00", "to": None},
            }]
        }
    })
    client = JikanClient(transport=transport)
    item = client.search("Demo")[0]

    assert item.id == "mal:456"
    assert item.release_state == "FINISHED"
    assert item.episodes == 12
    assert item.cover_image == "https://img"


def test_metadata_service_falls_back_to_jikan() -> None:
    class BrokenAniList:
        def search(self, query):
            raise MetadataTransportError("down")

    class WorkingJikan:
        def search(self, query, limit=10):
            return [AnimeMetadata(id="jikan:1", title="Fallback", mal_id=1)]

    service = MetadataService(BrokenAniList(), WorkingJikan())
    results = service.search("Fallback")

    assert results[-1].metadata.title == "Fallback"
    assert results[-1].provider == "jikan"
