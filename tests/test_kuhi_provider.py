from animexe.providers.kuhi import KuhiProvider


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses

    def request_json(self, url, *, method="GET", payload=None, headers=None):
        del method, payload, headers
        return self.responses[url]


def test_kuhi_search_normalizes_anime() -> None:
    base = "https://kuhi.example"
    transport = FakeTransport({
        f"{base}/anime/search?query=Demo&page=1&per_page=20": {
            "results": [{
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
                "coverImage": {"large": "https://img"},
            }]
        }
    })

    item = KuhiProvider(base, transport=transport).search("Demo")[0]

    assert item.id == "mal:456"
    assert item.anilist_id == 123
    assert item.release_state == "RELEASING"


def test_kuhi_episode_catalog_is_normalized() -> None:
    base = "https://kuhi.example"
    transport = FakeTransport({
        f"{base}/anime/episodes/123": {
            "anilistId": 123,
            "source": "native",
            "providers": {
                "anineko": {
                    "episodes": {
                        "sub": [
                            {"id": "sub-1", "number": 1, "title": "Episode 1"},
                            {"id": "sub-2", "number": 2, "title": "Episode 2"},
                        ],
                        "dub": [
                            {"id": "dub-1", "number": 1, "title": "Episode 1"},
                        ],
                    }
                }
            },
        }
    })

    provider = KuhiProvider(base, transport=transport)
    episodes = provider.get_episodes("anilist:123")

    assert [(item.episode, item.language, item.external_id) for item in episodes] == [
        (1, "dub", "dub-1"),
        (1, "sub", "sub-1"),
        (2, "sub", "sub-2"),
    ]


def test_kuhi_resolution_stops_at_catalog_boundary() -> None:
    base = "https://kuhi.example"
    transport = FakeTransport({
        f"{base}/anime/episodes/123": {
            "providers": {
                "anineko": {
                    "episodes": {
                        "sub": [{"id": "sub-1", "number": 1}],
                        "dub": [],
                    }
                }
            }
        }
    })

    provider = KuhiProvider(base, transport=transport)
    availability = provider.resolve_episode("anilist:123", 1)

    assert availability.catalog_exists is True
    assert availability.source_resolved is False
    assert availability.processable is False
