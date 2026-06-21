from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from dateutil import parser as date_parser

from antenna.models import YoutubeMetadata


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

    def filter_urls(self, urls: list[str], blackurls: list[str]) -> list[str]:
        result: list[str] = []
        for url in urls:
            if self._is_blacklisted(url, blackurls):
                continue
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
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(canonical_url, download=False)

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
            metadata_json=json.dumps(info, ensure_ascii=False, default=str),
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

    def _is_blacklisted(self, url: str, blackurls: list[str]) -> bool:
        host = urlparse(url).hostname or ""
        text = url.lower()
        host = host.lower()
        return any(rule.lower() in host or rule.lower() in text for rule in blackurls)
