import httpx

from antenna.config import AppConfig, Settings
from antenna.services.thumbnail_service import ThumbnailService


def make_service(tmp_path):
    settings = Settings(
        app=AppConfig(
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            thumbnail_dir=str(tmp_path / "thumbnails"),
        ),
    )
    return ThumbnailService(settings)


def test_download_writes_thumbnail_and_returns_static_path(tmp_path, monkeypatch):
    def fake_get(url, timeout):
        assert url == "https://example.com/thumb.jpg"
        assert timeout == 20
        return httpx.Response(200, content=b"image-bytes", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    service = make_service(tmp_path)

    path = service.download("video123", "https://example.com/thumb.jpg")

    assert path == "static/thumbnails/video123.jpg"
    assert (tmp_path / "thumbnails" / "video123.jpg").read_bytes() == b"image-bytes"


def test_download_returns_none_when_http_request_fails(tmp_path, monkeypatch):
    def fake_get(url, timeout):
        raise httpx.ConnectError("failed")

    monkeypatch.setattr(httpx, "get", fake_get)
    service = make_service(tmp_path)

    path = service.download("video123", "https://example.com/thumb.jpg")

    assert path is None
    assert not (tmp_path / "thumbnails" / "video123.jpg").exists()
