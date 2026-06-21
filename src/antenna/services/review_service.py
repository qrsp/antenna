from __future__ import annotations

from antenna.db import Database
from antenna.models import VALID_PROCESS


class ReviewService:
    def __init__(self, db: Database):
        self.db = db

    def list_videos(self, process: str, *, limit: int | None = None, offset: int = 0) -> list[dict]:
        if process not in VALID_PROCESS:
            raise ValueError("process must be checked or uncheck")
        return self.db.list_videos(process, limit=limit, offset=offset)

    def update_process(self, urls: list[str], process: str) -> int:
        if process not in VALID_PROCESS:
            raise ValueError("process must be checked or uncheck")
        return self.db.update_video_process(urls, process)

    def update_all(self, from_process: str, to_process: str) -> int:
        if from_process not in VALID_PROCESS or to_process not in VALID_PROCESS:
            raise ValueError("process must be checked or uncheck")
        return self.db.update_all_video_process(from_process, to_process)
