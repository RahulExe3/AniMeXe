"""Media input boundary for provider/local/authorized sources.

The package currently exposes only the stable media-input boundary. Provider-specific
source extraction must return a normalized MediaSource; AniMeXe does not implement
DRM bypass, paywall bypass, CAPTCHA evasion, or proxy/decryption workarounds.
"""

from ..models import MediaSource


class MediaInputError(RuntimeError):
    """Raised when an authorized media input cannot be accepted."""


__all__ = ["MediaInputError", "MediaSource"]
