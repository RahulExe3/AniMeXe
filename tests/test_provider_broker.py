from animexe.models import EpisodeAvailability
from animexe.providers import ProviderBroker, ProviderRegistry
from animexe.providers.base import Provider, ProviderHealth


class StubProvider(Provider):
    def __init__(self, name, availability):
        self.name = name
        self.availability = availability

    def search(self, query):
        return []

    def get_anime(self, anime_id):
        raise NotImplementedError

    def get_episodes(self, anime_id, season=1):
        return []

    def resolve_episode(self, anime_id, episode_number, season=1, language="sub"):
        return self.availability

    def get_source(self, episode):
        raise NotImplementedError

    def check_health(self):
        return ProviderHealth("AVAILABLE", self.name, "now")


def test_broker_prefers_catalog_available_provider() -> None:
    registry = ProviderRegistry()
    registry.register(StubProvider("slow", EpisodeAvailability(catalog_exists=True)))
    registry.register(StubProvider("empty", EpisodeAvailability(catalog_exists=False)))
    probes = ProviderBroker(registry).probe_episode("anilist:21", 1)
    assert probes[0].provider == "slow"
    assert ProviderBroker.best_catalog_provider(probes).provider == "slow"
