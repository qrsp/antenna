from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from dateutil import parser as date_parser

from antenna.models import YoutubeMetadata


class YoutubeMetadataUnavailable(RuntimeError):
    def __init__(self, url: str, status: str, message: str):
        self.url = url
        self.status = status
        super().__init__(message)


class _QuietYtdlpLogger:
    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


class YoutubeService:
    def canonicalize(self, url: str) -> tuple[str, str] | None:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return None
        hostname = hostname.lower()

        video_id: str | None = None
        if hostname == "youtu.be":
            video_id = parsed.path.strip("/").split("/", 1)[0] or None
        elif hostname.endswith("youtube.com") or hostname.endswith("youtube-nocookie.com"):
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [None])[0]
            elif parsed.path.startswith("/live/"):
                video_id = parsed.path.removeprefix("/live/").split("/", 1)[0] or None

        if not video_id:
            return None
        return f"https://www.youtube.com/watch?v={video_id}", video_id

    def filter_urls(self, urls: list[str]) -> list[str]:
        result: list[str] = []
        for url in urls:
            canonical = self.canonicalize(url)
            if canonical:
                result.append(canonical[0])
        return sorted(set(result))

    def fetch_metadata(self, url: str) -> YoutubeMetadata:
        canonical = self.canonicalize(url)
        if canonical is None:
            raise ValueError(f"not a supported YouTube URL: {url}")
        canonical_url, video_id = canonical
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError("yt-dlp is required to fetch YouTube metadata") from exc

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "logger": _QuietYtdlpLogger(),
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
        except Exception as exc:
            status = self._status_from_error(str(exc))
            raise YoutubeMetadataUnavailable(canonical_url, status, str(exc)) from exc

        status = str(info.get("availability") or "unknown")
        start_at = self._parse_time(info)
        return YoutubeMetadata(
            url=canonical_url,
            video_id=str(info.get("id") or video_id),
            title=info.get("title"),
            channel_id=info.get("channel_id") or info.get("uploader_id"),
            channel_name=info.get("channel") or info.get("uploader"),
            start_at=start_at,
            media_type=info.get("live_status") or info.get("media_type") or info.get("_type"),
            status=status,
            thumbnail_url=info.get("thumbnail"),
        )

    def _parse_time(self, info: dict) -> datetime | None:
        for key in ("timestamp", "release_timestamp", "upload_date", "modified_timestamp"):
            value = info.get(key)
            if value is None:
                continue
            if isinstance(value, int | float):
                return datetime.fromtimestamp(value, tz=timezone.utc)
            if isinstance(value, str):
                try:
                    if len(value) == 8 and value.isdigit():
                        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
                    parsed = date_parser.parse(value)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed
                except (ValueError, TypeError):
                    continue
        return None

    def _status_from_error(self, message: str) -> str:
        lowered = message.lower()
        if "private video" in lowered:
            return "private"
        if "members-only" in lowered or "join this channel" in lowered:
            return "members"
        if "removed" in lowered:
            return "removed"
        if "unavailable" in lowered:
            return "unavailable"
        return "unknown"
