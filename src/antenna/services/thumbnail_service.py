from __future__ import annotations

from pathlib import Path

import requests

from antenna.config import Settings


class ThumbnailService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.directory = settings.app.thumbnail_path
        self.directory.mkdir(parents=True, exist_ok=True)

    def download(self, video_id: str, thumbnail_url: str | None) -> str | None:
        if not thumbnail_url:
            return None
        target = self.directory / f"{video_id}.jpg"
        if target.exists() and target.stat().st_size > 0:
            return self._static_path(target)
        try:
            response = requests.get(thumbnail_url, timeout=20)
            response.raise_for_status()
        except requests.RequestException:
            return None
        target.write_bytes(response.content)
        return self._static_path(target)

    def _static_path(self, path: Path) -> str:
        return f"static/thumbnails/{path.name}"
