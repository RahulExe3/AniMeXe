from pathlib import Path
from types import SimpleNamespace

import pytest

from animexe.media.source_download import SourceDownloadError, _check_unencrypted_hls, download_media_source


class FakeResponse:
    def __init__(self, url, content=b"", headers=None, chunks=None, status_code=200):
        self.url = url
        self.content = content
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.status_code = status_code
        self._chunks = chunks if chunks is not None else ([content] if content else [])

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=1024):
        del chunk_size
        yield from self._chunks

    def close(self):
        pass


def test_embed_player_urls_are_not_downloaded(monkeypatch):
    def unexpected_request(*args, **kwargs):
        raise AssertionError("embed URL should be rejected before network access")

    monkeypatch.setattr("animexe.media.source_download.requests.get", unexpected_request)
    with pytest.raises(SourceDownloadError, match="embedded player/catalog page"):
        download_media_source(
            "https://anixo.buzz/embed/ani/21/1?track=dub",
            "/tmp/episode.mkv",
            source_provider="anixo",
        )


def test_dash_is_explicitly_unsupported():
    with pytest.raises(SourceDownloadError, match="DASH sources are not supported"):
        download_media_source("https://cdn.example/video.mpd", "/tmp/episode.mkv")


def test_private_ip_urls_are_rejected():
    with pytest.raises(SourceDownloadError, match="Private or non-public IP"):
        download_media_source("http://127.0.0.1/episode.mp4", "/tmp/episode.mkv")


def test_encrypted_hls_is_rejected(monkeypatch):
    playlist = b"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-KEY:METHOD=AES-128,URI="key.bin"
#EXTINF:4.0,
segment.ts
#EXT-X-ENDLIST
"""
    monkeypatch.setattr(
        "animexe.media.source_download.requests.get",
        lambda url, **kwargs: FakeResponse(url=url, content=playlist),
    )
    with pytest.raises(SourceDownloadError, match="Encrypted or ambiguous HLS key"):
        download_media_source(
            "https://cdn.example/episode.m3u8",
            "/tmp/episode.mkv",
        )


def test_hls_download_preflights_and_remuxes(monkeypatch, tmp_path: Path):
    playlist = b"""#EXTM3U
#EXT-X-VERSION:3
#EXTINF:4.0,
segment.ts
#EXT-X-ENDLIST
"""
    monkeypatch.setattr(
        "animexe.media.source_download.requests.get",
        lambda url, **kwargs: FakeResponse(
            url,
            content=playlist,
            headers={"Content-Type": "application/vnd.apple.mpegurl"},
        ),
    )
    monkeypatch.setattr("animexe.media.source_download.shutil.which", lambda _: "/usr/bin/ffmpeg")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        Path(command[-1]).write_bytes(b"fake-matroska")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("animexe.media.source_download.subprocess.run", fake_run)
    output = tmp_path / "episode.mkv"
    result = download_media_source(
        "https://stream.animeparadise.moe/m3u8?url=opaque-token",
        output,
        source_provider="animeparadise",
        headers={"Referer": "https://animeparadise.moe/"},
    )
    assert output.read_bytes() == b"fake-matroska"
    assert captured["command"][captured["command"].index("-fs") + 1] == str(8 * 1024**3)
    assert result["source_kind"] == "hls"
    assert result["source_audio_preserved_for_analysis"] is True


def test_direct_file_is_saved_atomically(monkeypatch, tmp_path: Path):
    payload = b"fake-mp4-container"
    monkeypatch.setattr(
        "animexe.media.source_download.requests.get",
        lambda url, **kwargs: FakeResponse(
            url,
            content=payload,
            chunks=[payload[:5], payload[5:]],
            headers={"Content-Type": "video/mp4", "Content-Length": str(len(payload))},
        ),
    )
    output = tmp_path / "episode.mp4"
    result = download_media_source(
        "https://cdn.example/episode.mp4",
        output,
        source_provider="anixo",
        max_bytes=100,
    )
    assert output.read_bytes() == payload
    assert result["source_kind"] == "file"
    assert result["size_bytes"] == len(payload)


def test_direct_file_size_limit_is_enforced(monkeypatch, tmp_path: Path):
    payload = b"x" * 20
    monkeypatch.setattr(
        "animexe.media.source_download.requests.get",
        lambda url, **kwargs: FakeResponse(
            url,
            content=payload,
            chunks=[payload],
            headers={"Content-Type": "video/mp4"},
        ),
    )
    with pytest.raises(SourceDownloadError, match="exceeds the 10 byte limit"):
        download_media_source(
            "https://cdn.example/episode.mp4",
            tmp_path / "episode.mp4",
            max_bytes=10,
        )


def test_hls_preflight_ignores_unavailable_iframe_only_playlist(monkeypatch):
    master = b"""#EXTM3U
#EXT-X-VERSION:4
#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=640x360
/index-f3-v1-a1.m3u8
#EXT-X-I-FRAME-STREAM-INF:BANDWIDTH=50000,URI="/iframes-f3-v1-a1.m3u8"
"""
    media = b"""#EXTM3U
#EXT-X-VERSION:3
#EXTINF:6.0,
segment.ts
#EXT-X-ENDLIST
"""
    root = "https://stream.animeparadise.moe/m3u8?url=opaque-token"
    variant = "https://stream.animeparadise.moe/index-f3-v1-a1.m3u8"
    requested = []

    def fake_get(url, **kwargs):
        requested.append(url)
        if url == root:
            return FakeResponse(url=url, content=master)
        if url == variant:
            return FakeResponse(url=url, content=media)
        if "/iframes-f3-v1-a1.m3u8" in url:
            return FakeResponse(
                url=url,
                content=b'{"message":"Route GET:/iframes-f3-v1-a1.m3u8 not found"}',
                status_code=404,
            )
        raise AssertionError(f"Unexpected playlist request: {url}")

    monkeypatch.setattr("animexe.media.source_download.requests.get", fake_get)

    _check_unencrypted_hls(root, {"Referer": "https://animeparadise.moe/"}, 10)

    assert root in requested
    assert variant in requested
    assert not any("/iframes-f3-v1-a1.m3u8" in url for url in requested)
