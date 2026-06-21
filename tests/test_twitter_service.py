from types import SimpleNamespace

from antenna.config import TwitterConfig
from antenna.services.twitter_service import TwitterService


class FakeTwitterService(TwitterService):
    def __init__(self, total):
        super().__init__(TwitterConfig())
        self.total = total

    def _iter_raw_tweets(self, username):
        for index in range(self.total, 0, -1):
            yield SimpleNamespace(
                id=str(index),
                created_at="2026-06-14T00:00:00+00:00",
                urls=[],
            )


def test_fetch_tweets_stops_at_max_tweets_for_new_account():
    service = FakeTwitterService(total=150)

    tweets = service.fetch_tweets("new_account", max_tweets=100)

    assert len(tweets) == 100
    assert tweets[0].status_id == "150"
    assert tweets[-1].status_id == "51"


def test_fetch_tweets_without_max_tweets_keeps_all_newer_than_cutoff():
    service = FakeTwitterService(total=150)

    tweets = service.fetch_tweets("known_account", since_status_id="140")

    assert [tweet.status_id for tweet in tweets] == [str(index) for index in range(150, 140, -1)]
