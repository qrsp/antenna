from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from antenna.config import Settings
from antenna.models import LIBRARY_NEW, VALID_LIBRARY_STATES, TweetRecord, YoutubeMetadata


def utcnow() -> datetime:
    return datetime.now(UTC)


def dt_to_db(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


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
        migration_dir = Path(__file__).resolve().parent / "migrations"
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name TEXT NOT NULL,
                    applied_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (name)
                )
                """
            )
            applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations").fetchall()}
            for migration_path in sorted(migration_dir.glob("*.sql")):
                if migration_path.name in applied:
                    continue
                conn.executescript(migration_path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                    (migration_path.name, dt_to_db(utcnow())),
                )

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

    def update_scan(self, scan_id: int, *, message: str | None, stats: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE scans
                SET message = ?, stats_json = ?
                WHERE id = ? AND status = 'running'
                """,
                (message, json.dumps(stats, ensure_ascii=False), scan_id),
            )

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

    def cleanup_stale_running_scans(self) -> list[int]:
        message = "Scan interrupted by application restart"
        cleaned: list[int] = []
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, stats_json
                FROM scans
                WHERE status = 'running'
                ORDER BY id
                """
            ).fetchall()
            for row in rows:
                stats = json.loads(row["stats_json"] or "{}")
                stats["current_account"] = None
                conn.execute(
                    """
                    UPDATE scans
                    SET status = 'failed', finished_at = ?, message = ?, stats_json = ?
                    WHERE id = ? AND status = 'running'
                    """,
                    (dt_to_db(utcnow()), message, json.dumps(stats, ensure_ascii=False), row["id"]),
                )
                cleaned.append(int(row["id"]))
        return cleaned

    def get_scan(self, scan_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return self._scan_row(row)

    def get_latest_scan(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
        return self._scan_row(row)

    def get_running_scan(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM scans WHERE status = 'running' ORDER BY id DESC LIMIT 1",
            ).fetchone()
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

    def create_scan_resume(
        self,
        *,
        source_scan_id: int,
        force: bool,
        limit_accounts: list[str],
        failed_account: str,
    ) -> int:
        now = dt_to_db(utcnow())
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE scan_resume_state
                SET status = 'cancelled'
                WHERE status = 'pending'
                """
            )
            cursor = conn.execute(
                """
                INSERT INTO scan_resume_state (
                    source_scan_id, reason, force, limit_accounts_json,
                    failed_account, status, created_at
                )
                VALUES (?, 'rate_limited', ?, ?, ?, 'pending', ?)
                """,
                (
                    source_scan_id,
                    1 if force else 0,
                    json.dumps(limit_accounts, ensure_ascii=False),
                    failed_account,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def get_pending_scan_resume(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM scan_resume_state
                WHERE status = 'pending'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return self._scan_resume_row(row)

    def consume_scan_resume(self, resume_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE scan_resume_state
                SET status = 'consumed', consumed_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (dt_to_db(utcnow()), resume_id),
            )

    def _scan_resume_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["force"] = bool(data["force"])
        data["limit_accounts"] = json.loads(data.pop("limit_accounts_json") or "[]")
        return data

    def get_account_state(self, username: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM account_scan_state WHERE user_screen_name = ?",
                (username,),
            ).fetchone()
        return None if row is None else dict(row)

    def list_account_states(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM account_scan_state
                ORDER BY user_screen_name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_account_state(
        self,
        username: str,
        *,
        last_scan_at: datetime | None,
        last_tweet_at: datetime | None,
        last_status: str,
        last_error: str | None = None,
        last_status_id: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO account_scan_state (
                    user_screen_name, last_scan_at, last_tweet_at, last_status_id,
                    last_status, last_error
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_screen_name) DO UPDATE SET
                    last_scan_at = excluded.last_scan_at,
                    last_tweet_at = excluded.last_tweet_at,
                    last_status_id = COALESCE(excluded.last_status_id, account_scan_state.last_status_id),
                    last_status = excluded.last_status,
                    last_error = excluded.last_error
                """,
                (
                    username,
                    dt_to_db(last_scan_at),
                    dt_to_db(last_tweet_at),
                    last_status_id,
                    last_status,
                    last_error,
                ),
            )

    def get_latest_tweet_id(self, username: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT last_status_id
                FROM account_scan_state
                WHERE user_screen_name = ?
                """,
                (username,),
            ).fetchone()
        return None if row is None else row["last_status_id"]

    def save_tweets(self, tweets: list[TweetRecord]) -> int:
        return len(tweets)

    def save_youtube(self, item: YoutubeMetadata, thumbnail_path: str | None) -> None:
        now = dt_to_db(utcnow())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO youtube (
                    url, video_id, title, channel_id, channel_name, start_at, media_type,
                    status, library_state, thumbnail_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    video_id = excluded.video_id,
                    title = excluded.title,
                    channel_id = excluded.channel_id,
                    channel_name = excluded.channel_name,
                    start_at = excluded.start_at,
                    media_type = excluded.media_type,
                    status = excluded.status,
                    thumbnail_path = COALESCE(excluded.thumbnail_path, youtube.thumbnail_path),
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
                    LIBRARY_NEW,
                    thumbnail_path,
                    now,
                    now,
                ),
            )

    def list_videos(
        self,
        state: str = LIBRARY_NEW,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if state not in VALID_LIBRARY_STATES:
            raise ValueError("invalid library state")
        params: list[Any] = [state]
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    url,
                    video_id,
                    title,
                    channel_id,
                    channel_name,
                    start_at,
                    media_type,
                    status,
                    library_state,
                    thumbnail_path,
                    created_at,
                    updated_at
                FROM youtube
                WHERE library_state = ?
                ORDER BY COALESCE(start_at, created_at) DESC
                {limit_clause}
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def count_videos(self, state: str) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM youtube WHERE library_state = ?", (state,)).fetchone()
        return int(row["count"])

    def update_video_state(self, urls: list[str], state: str) -> int:
        if state not in VALID_LIBRARY_STATES:
            raise ValueError("invalid library state")
        if not urls:
            return 0
        now = dt_to_db(utcnow())
        with self.connect() as conn:
            count = 0
            for url in urls:
                cursor = conn.execute(
                    "UPDATE youtube SET library_state = ?, updated_at = ? WHERE url = ?",
                    (state, now, url),
                )
                count += cursor.rowcount
        return count

    def update_all_video_state(self, from_state: str, to_state: str) -> int:
        if from_state not in VALID_LIBRARY_STATES or to_state not in VALID_LIBRARY_STATES:
            raise ValueError("invalid library state")
        now = dt_to_db(utcnow())
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE youtube SET library_state = ?, updated_at = ? WHERE library_state = ?",
                (to_state, now, from_state),
            )
            return cursor.rowcount
