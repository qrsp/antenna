from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from antenna.config import SchedulerConfig
from antenna.db import Database, db_to_dt, dt_to_db, utcnow


TWITTER_PAUSE_KEY = "twitter_pause_until"


@dataclass(frozen=True)
class AccountDecision:
    username: str
    should_scan: bool
    reason: str
    next_scan_after: datetime | None = None


class SchedulerService:
    def __init__(self, db: Database, config: SchedulerConfig):
        self.db = db
        self.config = config

    def twitter_pause_until(self) -> datetime | None:
        return db_to_dt(self.db.get_runtime_value(TWITTER_PAUSE_KEY))

    def is_twitter_paused(self, now: datetime | None = None) -> bool:
        pause_until = self.twitter_pause_until()
        return bool(pause_until and pause_until > (now or utcnow()))

    def pause_for_rate_limit(self, now: datetime | None = None) -> datetime:
        base = now or utcnow()
        pause_until = base + timedelta(minutes=self.config.rate_limit_pause_minutes)
        self.db.set_runtime_value(TWITTER_PAUSE_KEY, dt_to_db(pause_until))
        return pause_until

    def decide_account(self, username: str, *, force: bool = False, now: datetime | None = None) -> AccountDecision:
        current = now or utcnow()
        state = self.db.get_account_state(username)
        if state is None:
            return AccountDecision(username=username, should_scan=True, reason="never_scanned")

        last_scan_at = db_to_dt(state.get("last_scan_at"))
        last_tweet_at = db_to_dt(state.get("last_tweet_at"))
        next_scan_after = db_to_dt(state.get("next_scan_after"))

        if force:
            return AccountDecision(username=username, should_scan=True, reason="forced", next_scan_after=next_scan_after)

        if last_scan_at:
            minimum_after = last_scan_at + timedelta(minutes=self.config.minimum_scan_interval_minutes)
            if minimum_after > current:
                return AccountDecision(username, False, "minimum_interval", minimum_after)

        if next_scan_after and next_scan_after > current:
            return AccountDecision(username, False, "next_scan_after", next_scan_after)

        next_after = self.compute_next_scan_after(last_scan_at or current, last_tweet_at)
        if next_after > current:
            return AccountDecision(username, False, "activity_interval", next_after)

        return AccountDecision(username=username, should_scan=True, reason="due", next_scan_after=next_after)

    def due_accounts(
        self,
        accounts: list[str],
        *,
        force: bool = False,
        limit_accounts: list[str] | None = None,
    ) -> tuple[list[str], list[AccountDecision]]:
        allowed = set(limit_accounts or accounts)
        decisions = [
            self.decide_account(account, force=force)
            for account in accounts
            if account in allowed
        ]
        return [item.username for item in decisions if item.should_scan], decisions

    def compute_next_scan_after(self, last_scan_at: datetime, last_tweet_at: datetime | None) -> datetime:
        if last_tweet_at is None:
            minutes = self.config.active_account_interval_minutes
        else:
            current = utcnow()
            inactive_after = timedelta(days=self.config.inactive_after_days)
            if current - last_tweet_at.astimezone(timezone.utc) >= inactive_after:
                minutes = self.config.inactive_account_interval_minutes
            else:
                minutes = self.config.active_account_interval_minutes
        minutes = max(minutes, self.config.minimum_scan_interval_minutes)
        return last_scan_at + timedelta(minutes=minutes)
