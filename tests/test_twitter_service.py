import asyncio
from types import SimpleNamespace

from antenna.config import TwitterConfig
from antenna.services.twitter_service import TwitterService


class FakeTwitterService(TwitterService):
    def __init__(self, total):
        super().__init__(TwitterConfig())
        self.total = total
        self.closed = False

    def _create_app(self):
        total = self.total
        service = self

        class FakeApp:
            def iter_tweets(self, username, pages=50, wait_time=0):
                page_size = 20

                class FakeGenerator:
                    def __init__(self):
                        self.next_start = total

                    def __aiter__(self):
                        return self

                    async def __anext__(self):
                        if self.next_start <= 0:
                            raise StopAsyncIteration
                        start = self.next_start
                        self.next_start -= page_size
                        page = [
                            SimpleNamespace(
                                id=str(index),
                                created_at="2026-06-14T00:00:00+00:00",
                                urls=[],
                            )
                            for index in range(start, max(start - page_size, 0), -1)
                        ]
                        return object(), page

                    async def aclose(self):
                        service.closed = True

                return FakeGenerator()

        return FakeApp()


def test_fetch_tweets_stops_at_max_tweets_for_new_account():
    service = FakeTwitterService(total=150)

    tweets = service.fetch_tweets("new_account", max_tweets=100)

    assert len(tweets) == 100
    assert tweets[0].status_id == "150"
    assert tweets[-1].status_id == "51"
    assert service.closed is True


def test_fetch_tweets_without_max_tweets_keeps_all_newer_than_cutoff():
    service = FakeTwitterService(total=150)

    tweets = service.fetch_tweets("known_account", since_status_id="140")

    assert [tweet.status_id for tweet in tweets] == [str(index) for index in range(150, 140, -1)]


def test_tweety_home_html_patch_uses_responsive_web_home(monkeypatch):
    from tweety.http import Request

    original_get_home_html = Request.get_home_html

    async def fallback_get_home_html(self):
        raise AssertionError("fallback should not be used for responsive-web home")

    class FakeSession:
        def __init__(self):
            self.calls = []

        async def request(self, **kwargs):
            self.calls.append(kwargs)
            html = """
            <html>
              <head><meta name="twitter-site-verification" content="abc"></head>
              <body>
                <svg id="loading-x-anim-0"></svg>
                <script>0:"ondemand.s",0:"abc"</script>
              </body>
            </html>
            """
            return SimpleNamespace(status_code=200, content=html.encode())

    class FakeRequest:
        def __init__(self):
            self._session = FakeSession()

        def _get_request_headers(self):
            return {"authorization": "Bearer token", "x-test": "1"}

    TwitterService._tweety_patch_applied = False
    monkeypatch.setattr(Request, "get_home_html", fallback_get_home_html)
    try:
        TwitterService(TwitterConfig())._patch_tweety_home_html()
        request = FakeRequest()

        home_page = asyncio.run(Request.get_home_html(request))

        assert home_page.select_one("[name='twitter-site-verification']")
        assert request._session.calls == [
            {"method": "GET", "url": "https://x.com/home", "headers": {"x-test": "1"}}
        ]
    finally:
        monkeypatch.setattr(Request, "get_home_html", original_get_home_html)
        TwitterService._tweety_patch_applied = False
