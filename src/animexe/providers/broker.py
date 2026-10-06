from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import monotonic

from ..models import EpisodeAvailability
from .base import Provider
from .registry import ProviderRegistry


@dataclass(frozen=True)
class ProviderProbe:
    provider: str
    elapsed_ms: float
    availability: EpisodeAvailability | None = None
    error: str | None = None

    @property
    def catalog_available(self) -> bool:
        return bool(self.availability and self.availability.catalog_exists)

    @property
    def score(self) -> float:
        if not self.availability:
            return -1000.0
        status_bonus = {"AVAILABLE": 10.0, "EPISODE_UNAVAILABLE": 0.0}.get(self.availability.provider_status, -20.0)
        return (
            (100.0 if self.availability.processable else 0.0)
            + (40.0 if self.availability.media_usable else 0.0)
            + (20.0 if self.availability.source_resolved else 0.0)
            + (10.0 if self.availability.catalog_exists else 0.0)
            + status_bonus
            - min(self.elapsed_ms / 1000.0, 20.0)
        )


class ProviderBroker:
    """Fan-out provider checks and choose the strongest currently healthy result."""

    def __init__(self, registry: ProviderRegistry, max_workers: int = 4) -> None:
        self.registry = registry
        self.max_workers = max(1, max_workers)

    def probe_episode(self, anime_id: str, episode_number: int, language: str = "sub") -> list[ProviderProbe]:
        names = [name for name in self.registry.names() if name != "local"]
        probes: list[ProviderProbe] = []

        def run(name: str) -> ProviderProbe:
            provider: Provider = self.registry.get(name)
            started = monotonic()
            try:
                availability = provider.resolve_episode(anime_id, episode_number, language=language)
                return ProviderProbe(
                    provider=name,
                    elapsed_ms=(monotonic() - started) * 1000.0,
                    availability=availability,
                )
            except Exception as exc:
                return ProviderProbe(
                    provider=name,
                    elapsed_ms=(monotonic() - started) * 1000.0,
                    error=str(exc),
                )

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(names)))) as pool:
            futures = {pool.submit(run, name): name for name in names}
            for future in as_completed(futures):
                probes.append(future.result())

        return sorted(probes, key=lambda item: (-item.score, item.provider))

    @staticmethod
    def best_catalog_provider(probes: list[ProviderProbe]) -> ProviderProbe | None:
        candidates = [item for item in probes if item.catalog_available]
        return max(candidates, key=lambda item: item.score, default=None)
