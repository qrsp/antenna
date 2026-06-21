from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from antenna import __version__
from antenna.config import Settings, load_settings
from antenna.db import Database
from antenna.routers import health, scans, settings as settings_router, videos
from antenna.services.review_service import ReviewService
from antenna.services.scan_service import ScanService
from antenna.services.scheduler_service import SchedulerService
from antenna.services.thumbnail_service import ThumbnailService
from antenna.services.twitter_service import TwitterService
from antenna.services.youtube_service import YoutubeService


def create_app() -> FastAPI:
    settings = load_settings()
    db = Database(settings)
    db.initialize()

    scheduler = SchedulerService(db, settings.scheduler)
    youtube = YoutubeService()
    thumbnails = ThumbnailService(settings)
    twitter = TwitterService(settings.twitter)
    review = ReviewService(db)
    scanner = ScanService(settings, db, scheduler, twitter, youtube, thumbnails)

    app = FastAPI(title="Antenna", version=__version__)
    app.state.settings = settings
    app.state.db = db
    app.state.scheduler = scheduler
    app.state.review = review
    app.state.scanner = scanner
    package_dir = Path(__file__).resolve().parent
    app.state.templates = Jinja2Templates(directory=str(package_dir / "templates"))

    app.mount("/static", StaticFiles(directory=str(package_dir / "static")), name="static")

    app.include_router(health.router)
    app.include_router(scans.router)
    app.include_router(scans.page_router)
    app.include_router(videos.router)
    app.include_router(settings_router.router)

    @app.get("/")
    def dashboard(request: Request):
        pause_until = scheduler.twitter_pause_until()
        latest_scan = db.get_latest_scan()
        return app.state.templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "unchecked_count": db.count_videos("uncheck"),
                "checked_count": db.count_videos("checked"),
                "latest_scan": latest_scan,
                "pause_until": pause_until,
                "settings": settings,
            },
        )

    return app
