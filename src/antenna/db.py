from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from antenna.config import Settings
from antenna.models import PROCESS_UNCHECK, VALID_PROCESS, TweetRecord, YoutubeMetadata


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def dt_to_db(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def db_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.app.database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        migration_path = Path(__file__).resolve().parent / "migrations" / "001_init.sql"
        with self.connect() as conn:
            conn.executescript(migration_path.read_text(encoding="utf-8"))

    def ping(self) -> bool:
        with self.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True

    def create_scan(self) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO scans (status, started_at, stats_json) VALUES (?, ?, ?)",
                ("running", dt_to_db(utcnow()), "{}"),
            )
            return int(cursor.lastrowid)

    def finish_scan(self, scan_id: int, status: str, message: str | None, stats: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE scans
                SET status = ?, finished_at = ?, message = ?, stats_json = ?
                WHERE id = ?
                """,
                (status, dt_to_db(utcnow()), message, json.dumps(stats, ensure_ascii=False), scan_id),
            )

    def get_scan(self, scan_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return self._scan_row(row)

    def get_latest_scan(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        return self._scan_row(row)

    def _scan_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["stats"] = json.loads(data.pop("stats_json") or "{}")
        return data

    def get_runtime_value(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM runtime_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["value"]

    def set_runtime_value(self, key: str, value: str | None) -> None:
        now = dt_to_db(utcnow())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )

    def get_account_state(self, username: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM account_scan_state WHERE user_screen_name = ?",
                (username,),
            ).fetchone()
        return None if row is None else dict(row)

    def upsert_account_state(
        self,
        username: str,
        *,
        last_scan_at: datetime | None,
        last_tweet_at: datetime | None,
        next_scan_after: datetime | None,
        last_status: str,
        last_error: str | None = None,
    ) -> None:
        now = dt_to_db(utcnow())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO account_scan_state (
                    user_screen_name, last_scan_at, last_tweet_at, next_scan_after,
                    last_status, last_error, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_screen_name) DO UPDATE SET
                    last_scan_at = excluded.last_scan_at,
                    last_tweet_at = excluded.last_tweet_at,
                    next_scan_after = excluded.next_scan_after,
                    last_status = excluded.last_status,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    username,
                    dt_to_db(last_scan_at),
                    dt_to_db(last_tweet_at),
                    dt_to_db(next_scan_after),
                    last_status,
                    last_error,
                    now,
                ),
            )

    def get_latest_tweet_id(self, username: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT status_id FROM twitter
                WHERE user_screen_name = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (username,),
            ).fetchone()
        return None if row is None else row["status_id"]

    def save_tweets(self, tweets: list[TweetRecord]) -> int:
        now = dt_to_db(utcnow())
        count = 0
        with self.connect() as conn:
            for tweet in tweets:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO twitter (
                        status_id, user_screen_name, in_timeline, created_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        tweet.status_id,
                        tweet.user_screen_name,
                        1 if tweet.in_timeline else 0,
                        dt_to_db(tweet.created_at),
                    ),
                )
                count += cursor.rowcount
                for url in tweet.urls:
                    conn.execute(
                        "INSERT OR IGNORE INTO urls (url, created_at) VALUES (?, ?)",
                        (url, now),
                    )
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO tweet_urls (status_id, url, relation, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (tweet.status_id, url, tweet.relation, now),
                    )
        return count

    def save_url(self, url: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO urls (url, created_at) VALUES (?, ?)",
                (url, dt_to_db(utcnow())),
            )

    def save_youtube(self, item: YoutubeMetadata, thumbnail_path: str | None) -> None:
        self.save_url(item.url)
        now = dt_to_db(utcnow())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO youtube (
                    url, video_id, title, channel_id, channel_name, start_at, media_type,
                    status, process, thumbnail_path, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    video_id = excluded.video_id,
                    title = excluded.title,
                    channel_id = excluded.channel_id,
                    channel_name = excluded.channel_name,
                    start_at = excluded.start_at,
                    media_type = excluded.media_type,
                    status = excluded.status,
                    thumbnail_path = COALESCE(excluded.thumbnail_path, youtube.thumbnail_path),
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    item.url,
                    item.video_id,
                    item.title,
                    item.channel_id,
                    item.channel_name,
                    dt_to_db(item.start_at),
                    item.media_type,
                    item.status,
                    PROCESS_UNCHECK,
                    thumbnail_path,
                    item.metadata_json,
                    now,
                    now,
                ),
            )

    def list_videos(self, process: str = PROCESS_UNCHECK, *, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        if process not in VALID_PROCESS:
            raise ValueError("invalid process")
        params: list[Any] = [process]
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM youtube
                WHERE process = ?
                ORDER BY COALESCE(start_at, created_at) DESC
                {limit_clause}
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def count_videos(self, process: str) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM youtube WHERE process = ?", (process,)).fetchone()
        return int(row["count"])

    def update_video_process(self, urls: list[str], process: str) -> int:
        if process not in VALID_PROCESS:
            raise ValueError("invalid process")
        if not urls:
            return 0
        now = dt_to_db(utcnow())
        with self.connect() as conn:
            count = 0
            for url in urls:
                cursor = conn.execute(
                    "UPDATE youtube SET process = ?, updated_at = ? WHERE url = ?",
                    (process, now, url),
                )
                count += cursor.rowcount
        return count

    def update_all_video_process(self, from_process: str, to_process: str) -> int:
        if from_process not in VALID_PROCESS or to_process not in VALID_PROCESS:
            raise ValueError("invalid process")
        now = dt_to_db(utcnow())
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE youtube SET process = ?, updated_at = ? WHERE process = ?",
                (to_process, now, from_process),
            )
            return cursor.rowcount
