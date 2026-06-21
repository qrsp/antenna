from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationError,
    computed_field,
    create_model,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
TWITTER_COOKIES_ENV = "ANTENNA_TWITTER_COOKIES"


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TwitterConfig(ConfigModel):
    cookies: str = Field(default="", repr=False)

    @property
    def has_cookies(self) -> bool:
        return bool(self.cookies)


class ListsConfig(ConfigModel):
    follow: list[str] = Field(default_factory=list)

    @field_validator("follow")
    @classmethod
    def normalize_follow_list(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class SchedulerConfig(ConfigModel):
    auto_scan_interval_minutes: PositiveInt = 60
    minimum_scan_interval_minutes: PositiveInt = 60
    active_account_interval_minutes: PositiveInt = 180
    inactive_account_interval_minutes: PositiveInt = 1440
    inactive_after_days: PositiveInt = 30
    rate_limit_pause_minutes: PositiveInt = 900
    new_account_max_tweets: PositiveInt = 10

    @model_validator(mode="after")
    def validate_intervals(self) -> Self:
        if self.minimum_scan_interval_minutes > self.active_account_interval_minutes:
            raise ValueError("minimum_scan_interval_minutes cannot exceed active_account_interval_minutes")
        if self.minimum_scan_interval_minutes > self.inactive_account_interval_minutes:
            raise ValueError("minimum_scan_interval_minutes cannot exceed inactive_account_interval_minutes")
        return self


class AppConfig(ConfigModel):
    database_url: str = Field(default="sqlite:///data/antenna.db", min_length=11)
    thumbnail_dir: str = "src/antenna/static/thumbnails"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("sqlite:///"):
            raise ValueError("only sqlite:/// database URLs are supported")
        return value

    @field_validator("host", "thumbnail_dir")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @computed_field
    @property
    def database_path(self) -> Path:
        raw_path = self.database_url.removeprefix("sqlite:///")
        path = Path(raw_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @computed_field
    @property
    def thumbnail_path(self) -> Path:
        path = Path(self.thumbnail_dir)
        return path if path.is_absolute() else ROOT_DIR / path


class Settings(ConfigModel):
    twitter: TwitterConfig = Field(default_factory=TwitterConfig)
    lists: ListsConfig = Field(default_factory=ListsConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    app: AppConfig = Field(default_factory=AppConfig)

    def ensure_directories(self) -> None:
        self.app.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.app.thumbnail_path.mkdir(parents=True, exist_ok=True)
        (ROOT_DIR / "log").mkdir(parents=True, exist_ok=True)


class _EnvBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _load_env_value(name: str, env_file: Path | None = None) -> str:
    env_settings_type = create_model(
        "EnvValueSettings",
        value=(str, Field(default="", validation_alias=name)),
        __base__=_EnvBaseSettings,
    )
    return env_settings_type(_env_file=env_file or ROOT_DIR / ".env").value


def load_settings(config_path: Path | None = None, env_file: Path | None = None) -> Settings:
    path = config_path or ROOT_DIR / "config.toml"
    data = {}
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))

    try:
        settings = Settings.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid settings in {path}: {exc}") from exc

    cookies = _load_env_value(TWITTER_COOKIES_ENV, env_file)
    if cookies:
        settings = settings.model_copy(
            update={"twitter": settings.twitter.model_copy(update={"cookies": cookies})},
        )
    settings.ensure_directories()
    return settings
