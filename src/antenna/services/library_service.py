from __future__ import annotations

from antenna.db import Database
from antenna.models import VALID_LIBRARY_STATES


class LibraryService:
    def __init__(self, db: Database):
        self.db = db

    def list_videos(self, state: str, *, limit: int | None = None, offset: int = 0) -> list[dict]:
        if state not in VALID_LIBRARY_STATES:
            raise ValueError("state must be new or archived")
        return self.db.list_videos(state, limit=limit, offset=offset)

    def update_state(self, urls: list[str], state: str) -> int:
        if state not in VALID_LIBRARY_STATES:
            raise ValueError("state must be new or archived")
        return self.db.update_video_state(urls, state)

    def update_all(self, from_state: str, to_state: str) -> int:
        if from_state not in VALID_LIBRARY_STATES or to_state not in VALID_LIBRARY_STATES:
            raise ValueError("state must be new or archived")
        return self.db.update_all_video_state(from_state, to_state)
