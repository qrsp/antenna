from __future__ import annotations

from datetime import datetime

from markupsafe import Markup, escape
from zoneinfo import ZoneInfo


UTC_TZ = ZoneInfo("UTC")


def _parse_time(value: datetime | str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC_TZ)
    return parsed.astimezone(UTC_TZ)


def local_time(value: datetime | str | None) -> Markup | str:
    if not value:
        return ""
    parsed = _parse_time(value)
    iso_value = escape(parsed.isoformat())
    fallback = escape(parsed.strftime("%Y-%m-%d %H:%M:%S"))
    return Markup(f'<time datetime="{iso_value}" data-local-time>{fallback}</time>')
