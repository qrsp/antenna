from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TwitterConfig:
    cookies_env: str = "ANTENNA_TWITTER_COOKIES"

    @property
    def cookies(self) -> str:
        return os.getenv(self.cookies_env, "")

    @property
    def has_cookies(self) -> bool:
        return bool(self.cookies)


@dataclass(frozen=True)
class ListsConfig:
    follow: list[str] = field(default_factory=list)
    blackurls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SchedulerConfig:
    minimum_scan_interval_minutes: int = 60
    active_account_interval_minutes: int = 180
    inactive_account_interval_minutes: int = 1440
    inactive_after_days: int = 30
    rate_limit_pause_minutes: int = 900

    def validate(self) -> None:
        intervals = [
            self.minimum_scan_interval_minutes,
            self.active_account_interval_minutes,
            self.inactive_account_interval_minutes,
            self.rate_limit_pause_minutes,
        ]
        if any(value <= 0 for value in intervals):
            raise ValueError("scheduler intervals must be positive")
        if self.inactive_after_days <= 0:
            raise ValueError("scheduler.inactive_after_days must be positive")
        if self.minimum_scan_interval_minutes > self.active_account_interval_minutes:
            raise ValueError("minimum_scan_interval_minutes cannot exceed active_account_interval_minutes")
        if self.minimum_scan_interval_minutes > self.inactive_account_interval_minutes:
            raise ValueError("minimum_scan_interval_minutes cannot exceed inactive_account_interval_minutes")


@dataclass(frozen=True)
class AppConfig:
    database_url: str = "sqlite:///data/antenna.db"
    thumbnail_dir: str = "src/antenna/static/thumbnails"
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def database_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("only sqlite:/// database URLs are supported")
        raw_path = self.database_url.removeprefix("sqlite:///")
        path = Path(raw_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def thumbnail_path(self) -> Path:
        path = Path(self.thumbnail_dir)
        return path if path.is_absolute() else ROOT_DIR / path


@dataclass(frozen=True)
class Settings:
    twitter: TwitterConfig = field(default_factory=TwitterConfig)
    lists: ListsConfig = field(default_factory=ListsConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    app: AppConfig = field(default_factory=AppConfig)

    def ensure_directories(self) -> None:
        self.app.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.app.thumbnail_path.mkdir(parents=True, exist_ok=True)
        (ROOT_DIR / "log").mkdir(parents=True, exist_ok=True)


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_settings(config_path: Path | None = None) -> Settings:
    _load_env(ROOT_DIR / ".env")
    path = config_path or ROOT_DIR / "config.toml"
    data = {}
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))

    settings = Settings(
        twitter=TwitterConfig(**data.get("twitter", {})),
        lists=ListsConfig(**data.get("lists", {})),
        scheduler=SchedulerConfig(**data.get("scheduler", {})),
        app=AppConfig(**data.get("app", {})),
    )
    settings.scheduler.validate()
    settings.ensure_directories()
    return settings
