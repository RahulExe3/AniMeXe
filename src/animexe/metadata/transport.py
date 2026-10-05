from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


class MetadataTransportError(RuntimeError):
    """Raised when a metadata HTTP request cannot be completed."""


@dataclass(frozen=True)
class HttpTransport:
    timeout: float = 20.0
    user_agent: str = "AniMeXe/0.1"

    def request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if headers:
            request_headers.update(headers)

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        request = Request(
            url,
            data=body,
            headers=request_headers,
            method=method,
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise MetadataTransportError(f"metadata request failed: {exc}") from exc

        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MetadataTransportError("metadata provider returned invalid JSON") from exc

        if not isinstance(value, dict):
            raise MetadataTransportError("metadata provider returned a non-object JSON value")
        return value
