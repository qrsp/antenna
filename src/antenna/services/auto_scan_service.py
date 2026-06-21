from __future__ import annotations

import asyncio
from asyncio import AbstractEventLoop
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
        self._wake: asyncio.Event | None = None
        self._loop: AbstractEventLoop | None = None
        self._task: asyncio.Task[Any] | None = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    def wake(self) -> None:
        if self._loop and self._wake:
            self._loop.call_soon_threadsafe(self._wake.set)

    async def stop(self) -> None:
        if self._stop:
            self._stop.set()
        self.wake()
        if self._task:
            await self._task

    async def _run(self) -> None:
        assert self._stop is not None
        self._loop = self._loop or asyncio.get_running_loop()
        self._wake = self._wake or asyncio.Event()
        while not self._stop.is_set():
            self._wake.clear()
            wait_seconds = self._seconds_until_next_scan()
            if wait_seconds <= 0:
                force, limit_accounts = self._consume_next_scan_args()
                self.logger.info("starting automatic scan force=%s", force)
                self.scanner.start(force=force, limit_accounts=limit_accounts)
                wait_seconds = 5
            await self._wait_for_signal(wait_seconds)

    def _consume_next_scan_args(self) -> tuple[bool, list[str] | None]:
        resume = self.scheduler.db.get_pending_scan_resume()
        if resume:
            self.scheduler.db.consume_scan_resume(resume["id"])
            return resume["force"], resume["limit_accounts"]
        return False, None

    async def _wait_for_signal(self, timeout: float) -> None:
        assert self._stop is not None
        assert self._wake is not None
        stop_task = asyncio.create_task(self._stop.wait())
        wake_task = asyncio.create_task(self._wake.wait())
        done, pending = await asyncio.wait(
            {stop_task, wake_task},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if wake_task in done:
            self._wake.clear()

    def _seconds_until_next_scan(self) -> float:
        now = utcnow()
        next_scan_at = self.next_scan_at(now=now)
        return max(0.0, (next_scan_at - now).total_seconds())

    def next_scan_at(self, now: datetime | None = None) -> datetime:
        now = now or utcnow()
        pause_until = self.scheduler.twitter_pause_until()
        if pause_until and pause_until > now:
            return pause_until
        if self.scanner.is_running():
            return now + timedelta(seconds=5)
        if self.scheduler.db.get_pending_scan_resume():
            return now

        latest = self.scheduler.db.get_latest_scan()
        interval = timedelta(minutes=self.scheduler.config.auto_scan_interval_minutes)
        return self._next_scan_at(latest, interval)

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

