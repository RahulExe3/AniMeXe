"""Text-to-speech primitives and checkpoint manifests."""

from .engine import (
    CommandTTSSynthesizer,
    SyntheticTTSSynthesizer,
    TTSError,
    TTSManifest,
    TTSSegment,
)

__all__ = [
    "CommandTTSSynthesizer",
    "SyntheticTTSSynthesizer",
    "TTSError",
    "TTSManifest",
    "TTSSegment",
]
