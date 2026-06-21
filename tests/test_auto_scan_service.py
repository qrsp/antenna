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
    def is_running(self):
        return False


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
    assert service._should_force_after_pause() is False


def test_auto_scan_forces_scan_after_rate_limit_pause_expires(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()
    scheduler = SchedulerService(db, SchedulerConfig())
    service = AutoScanService(FakeScanner(), scheduler)
    scan_id = db.create_scan()
    pause_until = utcnow() - timedelta(seconds=1)
    db.finish_scan(scan_id, "paused", "paused", {})
    db.set_runtime_value("twitter_pause_until", dt_to_db(pause_until))

    assert service._seconds_until_next_scan() == 0
    assert service._should_force_after_pause() is True
