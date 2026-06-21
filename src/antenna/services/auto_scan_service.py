from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from antenna.db import db_to_dt, utcnow
from antenna.logging_util import get_logger
from antenna.services.scan_service import ScanService
from antenna.services.scheduler_service import SchedulerService


class AutoScanService:
    def __init__(self, scanner: ScanService, scheduler: SchedulerService):
        self.scanner = scanner
        self.scheduler = scheduler
        self.logger = get_logger("antenna.auto_scan")
        self._stop: asyncio.Event | None = None
        self._task: asyncio.Task[Any] | None = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._stop:
            self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        assert self._stop is not None
        while not self._stop.is_set():
            wait_seconds = self._seconds_until_next_scan()
            if wait_seconds <= 0:
                force = self._should_force_after_pause()
                self.logger.info("starting automatic scan force=%s", force)
                self.scanner.start(force=force, limit_accounts=None)
                wait_seconds = 5
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait_seconds)
            except TimeoutError:
                continue

    def _seconds_until_next_scan(self) -> float:
        now = utcnow()
        pause_until = self.scheduler.twitter_pause_until()
        if pause_until and pause_until > now:
            return max(0.0, (pause_until - now).total_seconds())
        if self.scanner.is_running():
            return 5.0

        latest = self.scheduler.db.get_latest_scan()
        interval = timedelta(minutes=self.scheduler.config.auto_scan_interval_minutes)
        next_scan_at = self._next_scan_at(latest, interval)
        return max(0.0, (next_scan_at - now).total_seconds())

    def _next_scan_at(self, latest: dict[str, Any] | None, interval: timedelta) -> datetime:
        if latest is None:
            return utcnow()
        started_at = db_to_dt(latest.get("started_at"))
        if started_at is None:
            return utcnow()
        if latest.get("status") == "paused":
            pause_until = self.scheduler.twitter_pause_until()
            if pause_until:
                return pause_until
            return utcnow()
        return started_at + interval

    def _should_force_after_pause(self) -> bool:
        latest = self.scheduler.db.get_latest_scan()
        if latest is None or latest.get("status") != "paused":
            return False
        pause_until = self.scheduler.twitter_pause_until()
        return pause_until is None or pause_until <= utcnow()
