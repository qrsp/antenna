from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from antenna import __version__
from antenna.config import Settings, load_settings
from antenna.db import Database
from antenna.models import LIBRARY_ARCHIVED, LIBRARY_NEW
from antenna.presentation import local_time
from antenna.routers import health, scans, settings as settings_router, videos
from antenna.services.auto_scan_service import AutoScanService
from antenna.services.library_service import LibraryService
from antenna.services.scan_service import ScanService
from antenna.services.scheduler_service import SchedulerService
from antenna.services.thumbnail_service import ThumbnailService
from antenna.services.twitter_service import TwitterService
from antenna.services.youtube_service import YoutubeService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings)
    db.initialize()

    scheduler = SchedulerService(db, settings.scheduler)
    youtube = YoutubeService()
    thumbnails = ThumbnailService(settings)
    twitter = TwitterService(settings.twitter)
    library = LibraryService(db)
    scanner = ScanService(settings, db, scheduler, twitter, youtube, thumbnails)
    auto_scanner = AutoScanService(scanner, scheduler)
    scanner.set_schedule_changed_callback(auto_scanner.wake)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        auto_scanner.start()
        try:
            yield
        finally:
            await auto_scanner.stop()

    app = FastAPI(title="Antenna", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.scheduler = scheduler
    app.state.library = library
    app.state.scanner = scanner
    app.state.auto_scanner = auto_scanner
    package_dir = Path(__file__).resolve().parent
    app.state.templates = Jinja2Templates(directory=str(package_dir / "templates"))
    app.state.templates.env.filters["local_time"] = local_time

    app.mount("/static", StaticFiles(directory=str(package_dir / "static")), name="static")

    app.include_router(health.router)
    app.include_router(scans.router)
    app.include_router(scans.page_router)
    app.include_router(videos.router)
    app.include_router(settings_router.router)

    @app.get("/")
    def dashboard(request: Request):
        latest_scan = db.get_latest_scan()
        next_scan_at = auto_scanner.next_scan_at()
        return app.state.templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "new_count": db.count_videos(LIBRARY_NEW),
                "archived_count": db.count_videos(LIBRARY_ARCHIVED),
                "latest_scan": latest_scan,
                "next_scan_at": next_scan_at,
                "settings": settings,
            },
        )

    return app
