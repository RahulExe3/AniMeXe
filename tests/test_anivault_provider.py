from animexe.providers.anivault import AnivaultProvider


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses

    def request_json(self, url, *, method="GET", payload=None, headers=None):
        del method, payload, headers
        return self.responses[url]


def test_anivault_merges_episode_catalog_sources() -> None:
    base = "https://anivault.example"
    transport = FakeTransport({
        f"{base}/api/episodes?anilistId=20&source=anikoto": {
            "episodes": [{"id": "a-1", "number": 1, "type": "sub"}, {"id": "a-1d", "number": 1, "type": "dub"}]
        },
        f"{base}/api/episodes?anilistId=20&source=animeheaven": {
            "episodes": [{"id": "h-1", "number": 1, "type": "sub"}, {"id": "h-2", "number": 2, "type": "sub"}]
        },
    })
    episodes = AnivaultProvider(base, transport=transport).get_episodes("anilist:20")
    assert [(item.episode, item.language) for item in episodes] == [
        (1, "dub"), (1, "sub"), (1, "sub"), (2, "sub")
    ]


def test_anivault_health_normalizes_ok_status() -> None:
    base = "https://anivault.example"
    transport = FakeTransport({f"{base}/api/health": {"status": "ok", "meta": {"version": "x"}}})
    health = AnivaultProvider(base, transport=transport).check_health()
    assert health.status == "AVAILABLE"
