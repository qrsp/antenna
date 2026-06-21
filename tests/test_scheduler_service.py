from datetime import timedelta

from antenna.config import SchedulerConfig
from antenna.db import Database, utcnow
from antenna.services.scheduler_service import SchedulerService


class DummySettings:
    def __init__(self, path):
        class App:
            database_path = path

        self.app = App()


def test_scheduler_defers_inactive_account_longer(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()
    config = SchedulerConfig(
        minimum_scan_interval_minutes=60,
        active_account_interval_minutes=120,
        inactive_account_interval_minutes=1440,
        inactive_after_days=30,
        rate_limit_pause_minutes=900,
    )
    scheduler = SchedulerService(db, config)
    now = utcnow()
    old_tweet_at = now - timedelta(days=45)

    db.upsert_account_state(
        "quiet_account",
        last_scan_at=now - timedelta(hours=3),
        last_tweet_at=old_tweet_at,
        last_status="success",
    )

    decision = scheduler.decide_account("quiet_account", now=now)

    assert decision.should_scan is False
    assert decision.reason == "activity_interval"
    assert decision.deferred_until == now - timedelta(hours=3) + timedelta(minutes=1440)


def test_scheduler_reports_later_activity_interval_when_minimum_interval_is_also_pending(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()
    config = SchedulerConfig(
        minimum_scan_interval_minutes=1440,
        active_account_interval_minutes=1440,
        inactive_account_interval_minutes=7200,
        inactive_after_days=7,
        rate_limit_pause_minutes=15,
    )
    scheduler = SchedulerService(db, config)
    now = utcnow()
    last_scan_at = now - timedelta(hours=10)

    db.upsert_account_state(
        "quiet_account",
        last_scan_at=last_scan_at,
        last_tweet_at=now - timedelta(days=404),
        last_status="success",
    )

    decision = scheduler.decide_account("quiet_account", now=now)

    assert decision.should_scan is False
    assert decision.reason == "activity_interval"
    assert decision.deferred_until == last_scan_at + timedelta(minutes=7200)


def test_scheduler_rate_limit_pause(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()
    scheduler = SchedulerService(db, SchedulerConfig())

    pause_until = scheduler.pause_for_rate_limit()

    assert pause_until > utcnow()
    assert scheduler.is_twitter_paused()
