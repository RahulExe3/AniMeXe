from __future__ import annotations

from pathlib import Path

from ..config import AppConfig
from .kuhi import KuhiProvider
from .local import LocalProvider
from .registry import ProviderRegistry


def build_registry(config: AppConfig, project_root: Path) -> ProviderRegistry:
    """Build the configured provider set without leaking implementations."""
    registry = ProviderRegistry()
    registry.register(LocalProvider(project_root))

    api_base_url = config.provider.api_base_url
    if api_base_url:
        registry.register(KuhiProvider(api_base_url))

    return registry
