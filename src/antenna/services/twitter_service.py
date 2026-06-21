from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser

from antenna.config import TwitterConfig
from antenna.models import TweetRecord


class TwitterRateLimitError(RuntimeError):
    pass


class TwitterService:
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

        records: list[TweetRecord] = []
        try:
            for raw in self._iter_raw_tweets(username):
                record = self._to_record(username, raw)
                if record is None:
                    continue
                if since_status_id and self._is_at_or_before_cutoff(record.status_id, since_status_id):
                    break
                records.append(record)
                if max_tweets is not None and len(records) >= max_tweets:
                    break
        except Exception as exc:
            if "rate" in str(exc).lower() and "limit" in str(exc).lower():
                raise TwitterRateLimitError(str(exc)) from exc
            raise
        return records

    def _iter_raw_tweets(self, username: str):
        if not self.config.has_cookies:
            raise RuntimeError(f"{self.config.cookies_env} is not configured")
        try:
            from tweety import Twitter
        except ImportError as exc:
            raise RuntimeError("tweety-ns is required to fetch Twitter timelines") from exc

        app = Twitter("session")
        app.load_cookies(self.config.cookies)
        return app.iter_tweets(username, pages=50)

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
                return value.replace(tzinfo=timezone.utc)
            return value
        if value:
            try:
                parsed = date_parser.parse(str(value))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                pass
        return datetime.now(timezone.utc)

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
