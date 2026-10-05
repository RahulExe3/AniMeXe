from __future__ import annotations

from .base import Provider


class ProviderRegistry:
    """Explicit provider registry used by the controller layer."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        name = provider.name.strip().lower()
        if not name:
            raise ValueError("provider name cannot be empty")
        if name in self._providers:
            raise ValueError(f"provider already registered: {name}")
        self._providers[name] = provider

    def get(self, name: str) -> Provider:
        key = name.strip().lower()
        if key not in self._providers:
            available = ", ".join(sorted(self._providers))
            raise KeyError(
                f"unknown provider '{name}'. Available: {available or 'none'}"
            )
        return self._providers[key]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
