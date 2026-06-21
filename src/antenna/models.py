from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


LIBRARY_ARCHIVED = "archived"
LIBRARY_NEW = "new"
VALID_LIBRARY_STATES = {LIBRARY_ARCHIVED, LIBRARY_NEW}


@dataclass(frozen=True)
class TweetRecord:
    status_id: str
    user_screen_name: str
    created_at: datetime
    in_timeline: bool
    urls: list[str]
    relation: str = "tweet"


@dataclass(frozen=True)
class YoutubeMetadata:
    url: str
    video_id: str
    title: str | None
    channel_id: str | None
    channel_name: str | None
    start_at: datetime | None
    media_type: str | None
    status: str
    thumbnail_url: str | None
    metadata_json: str
