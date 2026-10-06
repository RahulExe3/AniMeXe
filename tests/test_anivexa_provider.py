from animexe.providers.anivexa import AnivexaProvider


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses

    def request_json(self, url, *, method="GET", payload=None, headers=None):
        del method, payload, headers
        return self.responses[url]


def test_anivexa_episode_catalog_is_normalized() -> None:
    base = "https://anivexa.example"
    transport = FakeTransport({
        f"{base}/episodes/21": {
            "anilistId": 21,
            "providers": {
                "anineko": {
                    "episodes": {
                        "sub": [{"id": "sub-1", "number": 1}],
                        "dub": [{"id": "dub-1", "number": 1}],
                    }
                },
            },
        }
    })
    episodes = AnivexaProvider(base, transport=transport).get_episodes("anilist:21")
    assert [(item.episode, item.language) for item in episodes] == [(1, "dub"), (1, "sub")]


def test_anivexa_availability_never_claims_source_resolution() -> None:
    base = "https://anivexa.example"
    transport = FakeTransport({
        f"{base}/episodes/21": {
            "anilistId": 21,
            "providers": {"anineko": {"episodes": {"sub": [{"id": "sub-1", "number": 1}], "dub": []}}},
        }
    })
    availability = AnivexaProvider(base, transport=transport).resolve_episode("anilist:21", 1)
    assert availability.catalog_exists is True
    assert availability.source_resolved is False
    assert availability.processable is False
