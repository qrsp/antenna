import sys
import types

import pytest

from antenna.services.youtube_service import YoutubeMetadataUnavailable, YoutubeService


def test_canonicalize_supported_youtube_urls():
    service = YoutubeService()

    assert service.canonicalize("https://youtu.be/abc123") == (
        "https://www.youtube.com/watch?v=abc123",
        "abc123",
    )
    assert service.canonicalize("https://www.youtube.com/watch?v=abc123&t=30") == (
        "https://www.youtube.com/watch?v=abc123",
        "abc123",
    )
    assert service.canonicalize("https://youtube.com/live/abc123") == (
        "https://www.youtube.com/watch?v=abc123",
        "abc123",
    )


def test_filter_urls_applies_blacklist_and_deduplicates():
    service = YoutubeService()

    urls = service.filter_urls(
        [
            "https://youtu.be/abc123",
            "https://www.youtube.com/watch?v=abc123",
            "https://booth.pm/items/1",
        ],
        ["booth.pm"],
    )

    assert urls == ["https://www.youtube.com/watch?v=abc123"]


def test_fetch_metadata_converts_expected_ytdlp_errors(monkeypatch):
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def extract_info(self, url, download=False):
            raise RuntimeError("Private video. Sign in if you've been granted access to this video.")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    with pytest.raises(YoutubeMetadataUnavailable) as exc:
        YoutubeService().fetch_metadata("https://www.youtube.com/watch?v=abc123")

    assert exc.value.status == "private"
