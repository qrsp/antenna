from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
UTC_TZ = ZoneInfo("UTC")


def taipei_time(value: datetime | str | None) -> str:
    if not value:
        return ""
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC_TZ)
    return parsed.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")
