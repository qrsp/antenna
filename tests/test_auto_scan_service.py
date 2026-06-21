import asyncio
from datetime import timedelta

from antenna.config import SchedulerConfig
from antenna.db import Database, dt_to_db, utcnow
from antenna.services.auto_scan_service import AutoScanService
from antenna.services.scheduler_service import SchedulerService


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
