from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

import bs4
from dateutil import parser as date_parser

from antenna.config import TWITTER_COOKIES_ENV, TwitterConfig
from antenna.models import TweetRecord


class TwitterRateLimitError(RuntimeError):
    pass


class TwitterService:
    _tweety_patch_applied = False

    def __init__(self, config: TwitterConfig):
        self.config = config

    def fetch_tweets(
        self,
        username: str,
        *,
        since_status_id: str | None = None,
        max_tweets: int | None = None,
    ) -> list[TweetRecord]:
        if max_tweets is not None and max_tweets <= 0:
            return []

        try:
            app = self._create_app()
            records = self._run_async(
                self._fetch_tweets_async(
                    app,
                    username,
                    since_status_id=since_status_id,
                    max_tweets=max_tweets,
                )
            )
        except Exception as exc:
            if "rate" in str(exc).lower() and "limit" in str(exc).lower():
                raise TwitterRateLimitError(str(exc)) from exc
            raise
        return records

    def _run_async(self, coroutine):
        if sys.platform == "win32":
            loop = asyncio.SelectorEventLoop()
            try:
                return loop.run_until_complete(coroutine)
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
        return asyncio.run(coroutine)

    async def _fetch_tweets_async(
        self,
        app: Any,
        username: str,
        *,
        since_status_id: str | None,
        max_tweets: int | None,
    ) -> list[TweetRecord]:
        raw_pages = app.iter_tweets(username, pages=50, wait_time=0)
        records: list[TweetRecord] = []
        try:
            async for item in raw_pages:
                for raw in self._extract_page_items(item):
                    record = self._to_record(username, raw)
                    if record is None:
                        continue
                    if since_status_id and self._is_at_or_before_cutoff(record.status_id, since_status_id):
                        return records
                    records.append(record)
                    if max_tweets is not None and len(records) >= max_tweets:
                        return records
        finally:
            if hasattr(raw_pages, "aclose"):
                await raw_pages.aclose()
        return records

    def _create_app(self):
        if not self.config.has_cookies:
            raise RuntimeError(f"{TWITTER_COOKIES_ENV} is not configured")
        try:
            from tweety import Twitter
        except ImportError as exc:
            raise RuntimeError("tweety-ns is required to fetch Twitter timelines") from exc

        self._patch_tweety_home_html()
        app = Twitter("session")
        app.load_cookies(self.config.cookies)
        return app

    def _patch_tweety_home_html(self) -> None:
        if TwitterService._tweety_patch_applied:
            return
        try:
            from tweety.http import Request
        except ImportError:
            return

        original_get_home_html = Request.get_home_html

        async def get_home_html_with_responsive_web_fallback(request):
            headers = request._get_request_headers()
            headers.pop("authorization", None)
            try:
                response = await request._session.request(method="GET", url="https://x.com/home", headers=headers)
                home_page = bs4.BeautifulSoup(response.content, "lxml")
                text = str(home_page)
                if (
                    response.status_code in range(200, 300)
                    and "ondemand.s" in text
                    and "twitter-site-verification" in text
                    and "loading-x-anim" in text
                ):
                    return home_page
            except Exception:
                pass
            return await original_get_home_html(request)

        Request.get_home_html = get_home_html_with_responsive_web_fallback
        TwitterService._tweety_patch_applied = True

    def _extract_page_items(self, item: Any) -> list[Any]:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], list):
            return item[1]
        if isinstance(item, list):
            return item
        return [item]

    def _is_at_or_before_cutoff(self, status_id: str, cutoff: str) -> bool:
        if status_id.isdigit() and cutoff.isdigit():
            return int(status_id) <= int(cutoff)
        return status_id <= cutoff

    def _to_record(self, username: str, raw: Any) -> TweetRecord | None:
        status_id = str(getattr(raw, "id", "") or getattr(raw, "status_id", ""))
        if not status_id:
            return None
        created_at = self._created_at(getattr(raw, "created_on", None) or getattr(raw, "created_at", None))
        urls = self._extract_urls(raw)
        return TweetRecord(
            status_id=status_id,
            user_screen_name=username,
            created_at=created_at,
            in_timeline=True,
            urls=urls,
        )

    def _created_at(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value
        if value:
            try:
                parsed = date_parser.parse(str(value))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed
            except ValueError:
                pass
        return datetime.now(UTC)

    def _extract_urls(self, raw: Any) -> list[str]:
        urls: list[str] = []
        for item in self._walk(raw, max_depth=3):
            value = getattr(item, "expanded_url", None) or getattr(item, "url", None)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(value)
        return sorted(set(urls))

    def _walk(self, value: Any, *, max_depth: int) -> list[Any]:
        if max_depth < 0 or value is None:
            return []
        items = [value]
        if isinstance(value, dict):
            for nested in value.values():
                items.extend(self._walk(nested, max_depth=max_depth - 1))
        elif isinstance(value, list | tuple | set):
            for nested in value:
                items.extend(self._walk(nested, max_depth=max_depth - 1))
        else:
            for attr in ("urls", "entities", "quote", "quoted_tweet", "retweeted_tweet", "retweeted_status"):
                if hasattr(value, attr):
                    items.extend(self._walk(getattr(value, attr), max_depth=max_depth - 1))
        return items
