"""Kuhi provider adapter.

The adapter currently integrates Kuhi's normalized anime/catalog/health APIs.
Actual stream extraction remains an explicit authorized-media boundary.
"""

from .client import KuhiProvider

__all__ = ["KuhiProvider"]
