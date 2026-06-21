import asyncio
from datetime import UTC, datetime, timedelta

from antenna.config import SchedulerConfig
from antenna.db import Database, dt_to_db, utcnow
from antenna.services import auto_scan_service
from antenna.services.auto_scan_service import AutoScanService
from antenna.services.scan_service import ScanService
from antenna.services.scheduler_service import SchedulerService
from antenna.services.twitter_service import TwitterRateLimitError


class DummySettings:
    def __init__(self, path):
        class App:
            database_path = path

        self.app = App()


class FakeScanner:
    def __init__(self):
        self.starts = []
        self.on_start = None

    def is_running(self):
        return False

    def start(self, *, force=False, limit_accounts=None):
        self.starts.append({"force": force, "limit_accounts": limit_accounts})
        if self.on_start:
            self.on_start()


class EmptyTwitter:
    def __init__(self):
        self.calls = []

    def fetch_tweets(self, username, *, since_status_id=None, max_tweets=None):
        self.calls.append(
            {
                "username": username,
                "since_status_id": since_status_id,
                "max_tweets": max_tweets,
            }
        )
        return []


class RateLimitOnTwitter:
    def __init__(self, rate_limited_username):
        self.rate_limited_username = rate_limited_username
        self.calls = []

    def fetch_tweets(self, username, *, since_status_id=None, max_tweets=None):
        self.calls.append(username)
        if username == self.rate_limited_username:
            raise TwitterRateLimitError("rate limited")
        return []


class NullYoutube:
    def filter_urls(self, urls):
        return []


class NullThumbnails:
    pass


class ScanSettings:
    def __init__(self, path, scheduler_config, follow):
        class App:
            database_path = path

        class Lists:
            def __init__(self, accounts):
                self.follow = accounts

        self.app = App()
        self.scheduler = scheduler_config
        self.lists = Lists(follow)


def set_scan_started_at(db, scan_id, started_at):
    with db.connect() as conn:
        conn.execute(
            "UPDATE scans SET started_at = ? WHERE id = ?",
            (dt_to_db(started_at), scan_id),
        )


def test_auto_scan_waits_during_rate_limit_pause(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()
    scheduler = SchedulerService(db, SchedulerConfig())
    service = AutoScanService(FakeScanner(), scheduler)
    scan_id = db.create_scan()
    pause_until = utcnow() + timedelta(minutes=10)
    db.finish_scan(scan_id, "paused", "paused", {})
    db.set_runtime_value("twitter_pause_until", dt_to_db(pause_until))

    assert service._seconds_until_next_scan() > 0


def test_auto_scan_runs_without_force_after_rate_limit_pause_expires(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()
    scheduler = SchedulerService(db, SchedulerConfig())
    scanner = FakeScanner()
    service = AutoScanService(scanner, scheduler)
    scan_id = db.create_scan()
    pause_until = utcnow() - timedelta(seconds=1)
    db.finish_scan(scan_id, "paused", "paused", {})
    db.set_runtime_value("twitter_pause_until", dt_to_db(pause_until))

    assert service._seconds_until_next_scan() == 0

    async def run_once():
        service._stop = asyncio.Event()
        scanner.on_start = service._stop.set
        await service._run()

    asyncio.run(run_once())

    assert scanner.starts == [{"force": False, "limit_accounts": None}]


def test_auto_scan_wakes_and_recalculates_when_pause_changes(tmp_path, monkeypatch):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()
    config = SchedulerConfig(auto_scan_interval_minutes=60, rate_limit_pause_minutes=15)
    scheduler = SchedulerService(db, config)
    scanner = FakeScanner()
    service = AutoScanService(scanner, scheduler)
    base = datetime(2026, 6, 19, 9, 3, 9, tzinfo=UTC)
    current = base + timedelta(minutes=1)

    scan_id = db.create_scan()
    set_scan_started_at(db, scan_id, base)
    db.finish_scan(scan_id, "success", None, {})

    monkeypatch.setattr(auto_scan_service, "utcnow", lambda: current)

    async def run_check():
        service._stop = asyncio.Event()
        scanner.on_start = service._stop.set
        run_task = asyncio.create_task(service._run())
        await asyncio.sleep(0.05)

        assert scanner.starts == []

        paused_scan_id = db.create_scan()
        set_scan_started_at(db, paused_scan_id, base + timedelta(minutes=10))
        pause_until = base + timedelta(minutes=16)
        db.finish_scan(paused_scan_id, "paused", "paused", {})
        db.set_runtime_value("twitter_pause_until", dt_to_db(pause_until))
        db.create_scan_resume(
            source_scan_id=paused_scan_id,
            force=True,
            limit_accounts=["limited_account", "after_account"],
            failed_account="limited_account",
        )
        service.wake()
        await asyncio.sleep(0.05)

        assert scanner.starts == []

        nonlocal current
        current = base + timedelta(minutes=17)
        service.wake()

        await asyncio.wait_for(run_task, timeout=1)

    asyncio.run(run_check())

    assert scanner.starts == [
        {
            "force": True,
            "limit_accounts": ["limited_account", "after_account"],
        }
    ]
    assert db.get_pending_scan_resume() is None


def test_scan_rate_limit_persists_resume_state_and_notifies_schedule_changed(tmp_path):
    config = SchedulerConfig(rate_limit_pause_minutes=15)
    settings = ScanSettings(tmp_path / "test.db", config, ["first_account", "limited_account", "after_account"])
    db = Database(settings)
    db.initialize()
    scheduler = SchedulerService(db, config)
    twitter = RateLimitOnTwitter("limited_account")
    scanner = ScanService(settings, db, scheduler, twitter, NullYoutube(), NullThumbnails())
    notifications = []
    scanner.set_schedule_changed_callback(lambda: notifications.append("changed"))

    result = scanner.run(force=True, limit_accounts=None)
    resume = db.get_pending_scan_resume()

    assert result["status"] == "paused"
    assert notifications == ["changed"]
    assert resume is not None
    assert resume["source_scan_id"] == result["id"]
    assert resume["force"] is True
    assert resume["failed_account"] == "limited_account"
    assert resume["limit_accounts"] == ["limited_account", "after_account"]
    assert twitter.calls == ["first_account", "limited_account"]
    assert scheduler.twitter_pause_until() is not None


def test_scan_after_expired_pause_can_defer_all_accounts_by_minimum_interval(tmp_path):
    config = SchedulerConfig(
        auto_scan_interval_minutes=60,
        minimum_scan_interval_minutes=1440,
        active_account_interval_minutes=1440,
        inactive_account_interval_minutes=7200,
        inactive_after_days=7,
        rate_limit_pause_minutes=15,
    )
    accounts = ["recent_one", "recent_two"]
    settings = ScanSettings(tmp_path / "test.db", config, accounts)
    db = Database(settings)
    db.initialize()
    scheduler = SchedulerService(db, config)
    twitter = EmptyTwitter()
    scanner = ScanService(settings, db, scheduler, twitter, NullYoutube(), NullThumbnails())
    now = utcnow()

    for account in accounts:
        db.upsert_account_state(
            account,
            last_scan_at=now - timedelta(minutes=30),
            last_tweet_at=now - timedelta(minutes=10),
            last_status="success",
        )

    scan_id = db.create_scan()
    db.finish_scan(scan_id, "paused", "paused", {})
    db.set_runtime_value("twitter_pause_until", dt_to_db(now - timedelta(seconds=1)))

    result = scanner.run(force=False, limit_accounts=None)

    assert result["status"] == "success"
    assert result["stats"]["accounts_considered"] == 2
    assert result["stats"]["accounts_total"] == 0
    assert result["stats"]["deferred_accounts"] == 2
    assert result["stats"]["accounts_scanned"] == 0
    assert twitter.calls == []
