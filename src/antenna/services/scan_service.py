from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable

from antenna.config import Settings
from antenna.db import Database, db_to_dt, utcnow
from antenna.logging_util import get_logger
from antenna.services.scheduler_service import SchedulerService
from antenna.services.thumbnail_service import ThumbnailService
from antenna.services.twitter_service import TwitterRateLimitError, TwitterService
from antenna.services.youtube_service import YoutubeMetadataUnavailable, YoutubeService


class ScanService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        scheduler: SchedulerService,
        twitter: TwitterService,
        youtube: YoutubeService,
        thumbnails: ThumbnailService,
    ):
        self.settings = settings
        self.db = db
        self.scheduler = scheduler
        self.twitter = twitter
        self.youtube = youtube
        self.thumbnails = thumbnails
        self.logger = get_logger("antenna.scan")
        self._lock = threading.Lock()
        self._schedule_changed: Callable[[], None] | None = None

    def set_schedule_changed_callback(self, callback: Callable[[], None]) -> None:
        self._schedule_changed = callback

    def start(self, *, force: bool = False, limit_accounts: list[str] | None = None) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            running = self.db.get_running_scan()
            if running is not None:
                return running
            return {"id": 0, "status": "running", "message": "scan already running", "stats": {}}

        scan_id = self.db.create_scan()
        thread = threading.Thread(
            target=self._run_with_acquired_lock,
            kwargs={"scan_id": scan_id, "force": force, "limit_accounts": limit_accounts},
            daemon=True,
        )
        thread.start()
        return self.db.get_scan(scan_id) or {"id": scan_id, "status": "running", "stats": {}}

    def run(self, *, force: bool = False, limit_accounts: list[str] | None = None) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            running = self.db.get_running_scan()
            if running is not None:
                return running
            return {"id": 0, "status": "running", "message": "scan already running", "stats": {}}
        scan_id = self.db.create_scan()
        return self._run_with_acquired_lock(scan_id=scan_id, force=force, limit_accounts=limit_accounts)

    def is_running(self) -> bool:
        return self._lock.locked()

    def _run_with_acquired_lock(self, *, scan_id: int, force: bool, limit_accounts: list[str] | None) -> dict[str, Any]:
        try:
            return self._run_existing(scan_id=scan_id, force=force, limit_accounts=limit_accounts)
        finally:
            self._lock.release()

    def _run_existing(self, *, scan_id: int, force: bool, limit_accounts: list[str] | None) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "accounts_considered": 0,
            "accounts_scanned": 0,
            "tweets_saved": 0,
            "urls_seen": 0,
            "youtube_saved": 0,
            "errors": 0,
            "deferred_accounts": 0,
            "current_account": None,
            "accounts_total": 0,
        }
        try:
            pause_until = self.scheduler.twitter_pause_until()
            if pause_until and pause_until > utcnow():
                message = f"Twitter scanning paused until {pause_until.isoformat()}"
                self.db.finish_scan(scan_id, "paused", message, stats)
                return {"id": scan_id, "status": "paused", "message": message, "stats": stats}

            accounts, decisions = self.scheduler.due_accounts(
                self.settings.lists.follow,
                force=force,
                limit_accounts=limit_accounts,
            )
            stats["accounts_considered"] = len(decisions)
            stats["deferred_accounts"] = len([item for item in decisions if not item.should_scan])
            stats["accounts_total"] = len(accounts)
            self.db.update_scan(scan_id, message="Scan queued accounts", stats=stats)
            for decision in decisions:
                if not decision.should_scan:
                    self.logger.info(
                        "account %s deferred: %s until %s",
                        decision.username,
                        decision.reason,
                        decision.deferred_until,
                    )

            for username in accounts:
                stats["current_account"] = username
                self.db.update_scan(scan_id, message=f"Scanning {username}", stats=stats)
                try:
                    self._scan_account(username, stats)
                    stats["accounts_scanned"] += 1
                    self.db.update_scan(scan_id, message=f"Finished {username}", stats=stats)
                except TwitterRateLimitError as exc:
                    pause_until = self.scheduler.pause_for_rate_limit()
                    self.db.create_scan_resume(
                        source_scan_id=scan_id,
                        force=force,
                        limit_accounts=self._remaining_accounts(accounts, username),
                        failed_account=username,
                    )
                    if self._schedule_changed:
                        self._schedule_changed()
                    state = self.db.get_account_state(username) or {}
                    self.db.upsert_account_state(
                        username,
                        last_scan_at=db_to_dt(state.get("last_scan_at")),
                        last_tweet_at=db_to_dt(state.get("last_tweet_at")),
                        last_status="rate_limited",
                        last_error=str(exc),
                    )
                    message = f"Twitter rate limit reached; paused until {pause_until.isoformat()}"
                    self.logger.warning(message)
                    self.db.finish_scan(scan_id, "paused", message, stats)
                    return {"id": scan_id, "status": "paused", "message": message, "stats": stats}
                except Exception as exc:
                    stats["errors"] += 1
                    self.logger.exception("account %s failed", username)
                    state = self.db.get_account_state(username) or {}
                    last_tweet_at = db_to_dt(state.get("last_tweet_at"))
                    self.db.upsert_account_state(
                        username,
                        last_scan_at=utcnow(),
                        last_tweet_at=last_tweet_at,
                        last_status="failed",
                        last_error=str(exc),
                    )
                    self.db.update_scan(scan_id, message=f"Failed {username}", stats=stats)

            stats["current_account"] = None
            status = "failed" if stats["errors"] and not stats["accounts_scanned"] else "success"
            message = None if status == "success" else "all account scans failed"
            self.db.finish_scan(scan_id, status, message, stats)
            return {"id": scan_id, "status": status, "message": message, "stats": stats}
        except Exception as exc:
            stats["errors"] += 1
            self.logger.exception("scan %s failed", scan_id)
            self.db.finish_scan(scan_id, "failed", str(exc), stats)
            return {"id": scan_id, "status": "failed", "message": str(exc), "stats": stats}

    def _scan_account(self, username: str, stats: dict[str, Any]) -> None:
        since_status_id = self.db.get_latest_tweet_id(username)
        max_tweets = None if since_status_id else self.settings.scheduler.new_account_max_tweets
        tweets = self.twitter.fetch_tweets(
            username,
            since_status_id=since_status_id,
            max_tweets=max_tweets,
        )
        if max_tweets is not None and len(tweets) >= max_tweets:
            self.logger.info("new account %s scan stopped at %s tweets", username, max_tweets)
        stats["tweets_saved"] += self.db.save_tweets(tweets)

        urls = sorted({url for tweet in tweets for url in tweet.urls})
        stats["urls_seen"] += len(urls)
        youtube_urls = self.youtube.filter_urls(urls, self.settings.lists.blackurls)
        for url in youtube_urls:
            try:
                metadata = self.youtube.fetch_metadata(url)
                thumbnail_path = self.thumbnails.download(metadata.video_id, metadata.thumbnail_url)
                self.db.save_youtube(metadata, thumbnail_path)
                stats["youtube_saved"] += 1
            except YoutubeMetadataUnavailable as exc:
                stats["errors"] += 1
                self.logger.warning("youtube metadata unavailable for %s: %s", url, exc.status)
            except Exception:
                stats["errors"] += 1
                self.logger.exception("youtube metadata failed for %s", url)

        state = self.db.get_account_state(username) or {}
        last_tweet_at = self._latest_tweet_time(tweets) or db_to_dt(state.get("last_tweet_at"))
        last_status_id = self._latest_status_id(tweets)
        now = utcnow()
        self.db.upsert_account_state(
            username,
            last_scan_at=now,
            last_tweet_at=last_tweet_at,
            last_status_id=last_status_id,
            last_status="success",
        )

    def _latest_tweet_time(self, tweets: list) -> datetime | None:
        if not tweets:
            return None
        return max(tweet.created_at for tweet in tweets)

    def _latest_status_id(self, tweets: list) -> str | None:
        if not tweets:
            return None
        if all(tweet.status_id.isdigit() for tweet in tweets):
            return max(tweets, key=lambda tweet: int(tweet.status_id)).status_id
        return max(tweets, key=lambda tweet: tweet.status_id).status_id

    def _remaining_accounts(self, accounts: list[str], username: str) -> list[str]:
        try:
            index = accounts.index(username)
        except ValueError:
            return [username]
        return accounts[index:]
