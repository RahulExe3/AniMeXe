"""Anime metadata providers and normalization."""

from .anilist import AniListClient
from .jikan import JikanClient
from .library import MetadataLibrary
from .models import AnimeMetadata, MetadataResult
from .service import MetadataService

__all__ = [
    "AnimeMetadata",
    "AniListClient",
    "JikanClient",
    "MetadataLibrary",
    "MetadataResult",
    "MetadataService",
]
