from antenna.services.youtube_service import YoutubeService


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
