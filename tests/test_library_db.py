from antenna.config import SchedulerConfig
from antenna.db import Database, dt_to_db, utcnow
from antenna.models import YoutubeMetadata


class DummySettings:
    def __init__(self, path):
        class App:
            database_path = path

        self.app = App()
        self.scheduler = SchedulerConfig()


def test_youtube_library_state_is_limited_to_new_and_archived(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()
    db.save_youtube(
        YoutubeMetadata(
            url="https://www.youtube.com/watch?v=abc123",
            video_id="abc123",
            title="Example",
            channel_id=None,
            channel_name=None,
            start_at=None,
            media_type=None,
            status="public",
            thumbnail_url=None,
        ),
        None,
    )

    rows = db.list_videos("new")
    assert len(rows) == 1
    assert db.update_video_state(["https://www.youtube.com/watch?v=abc123"], "archived") == 1

    try:
        db.update_video_state(["https://www.youtube.com/watch?v=abc123"], "waiting")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid library state should fail")


def test_legacy_youtube_process_migrates_to_library_state(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    now = dt_to_db(utcnow())
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE urls (
                url TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                PRIMARY KEY (url)
            );
            CREATE TABLE youtube (
                url TEXT NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT,
                channel_id TEXT,
                channel_name TEXT,
                start_at TIMESTAMP,
                media_type TEXT,
                status TEXT NOT NULL,
                process TEXT NOT NULL DEFAULT 'uncheck',
                thumbnail_path TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                PRIMARY KEY (url),
                FOREIGN KEY (url)
                    REFERENCES urls (url)
                    ON DELETE CASCADE
                    ON UPDATE CASCADE,
                CHECK (process IN ('checked', 'uncheck'))
            );
            """
        )
        conn.execute(
            "INSERT INTO urls (url, created_at) VALUES (?, ?)",
            ("https://www.youtube.com/watch?v=oldnew", now),
        )
        conn.execute(
            "INSERT INTO urls (url, created_at) VALUES (?, ?)",
            ("https://www.youtube.com/watch?v=oldarchived", now),
        )
        conn.execute(
            """
            INSERT INTO youtube (
                url, video_id, status, process, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, 'public', 'uncheck', '{}', ?, ?)
            """,
            ("https://www.youtube.com/watch?v=oldnew", "oldnew", now, now),
        )
        conn.execute(
            """
            INSERT INTO youtube (
                url, video_id, status, process, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, 'public', 'checked', '{}', ?, ?)
            """,
            ("https://www.youtube.com/watch?v=oldarchived", "oldarchived", now, now),
        )

    db.initialize()

    columns = db.connect()
    with columns as conn:
        column_names = {row["name"] for row in conn.execute("PRAGMA table_info(youtube)").fetchall()}
    assert "library_state" in column_names
    assert "process" not in column_names
    assert "metadata_json" not in column_names
    assert [row["video_id"] for row in db.list_videos("new")] == ["oldnew"]
    assert [row["video_id"] for row in db.list_videos("archived")] == ["oldarchived"]


def test_account_scan_state_schema_drops_updated_at(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()

    with db.connect() as conn:
        column_names = {row["name"] for row in conn.execute("PRAGMA table_info(account_scan_state)").fetchall()}

    assert "updated_at" not in column_names
    assert "last_status_id" in column_names


def test_twitter_history_migrates_to_account_scan_cursor(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    older = dt_to_db(utcnow())
    newer = dt_to_db(utcnow())
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE urls (
                url TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                PRIMARY KEY (url)
            );
            CREATE TABLE twitter (
                status_id TEXT NOT NULL,
                user_screen_name TEXT NOT NULL,
                in_timeline INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                PRIMARY KEY (status_id)
            );
            CREATE TABLE tweet_urls (
                status_id TEXT NOT NULL,
                url TEXT NOT NULL,
                relation TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                PRIMARY KEY (status_id, url, relation)
            );
            CREATE TABLE youtube (
                url TEXT NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT,
                channel_id TEXT,
                channel_name TEXT,
                start_at TIMESTAMP,
                media_type TEXT,
                status TEXT NOT NULL,
                library_state TEXT NOT NULL DEFAULT 'new',
                thumbnail_path TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                PRIMARY KEY (url),
                CHECK (library_state IN ('archived', 'new'))
            );
            CREATE TABLE account_scan_state (
                user_screen_name TEXT NOT NULL,
                last_scan_at TIMESTAMP,
                last_tweet_at TIMESTAMP,
                last_status TEXT,
                last_error TEXT,
                updated_at TIMESTAMP NOT NULL,
                PRIMARY KEY (user_screen_name)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO account_scan_state (
                user_screen_name, last_scan_at, last_tweet_at, last_status, updated_at
            )
            VALUES ('example', ?, ?, 'success', ?)
            """,
            (older, older, older),
        )
        conn.execute(
            """
            INSERT INTO twitter (status_id, user_screen_name, in_timeline, created_at)
            VALUES ('100', 'example', 1, ?)
            """,
            (older,),
        )
        conn.execute(
            """
            INSERT INTO twitter (status_id, user_screen_name, in_timeline, created_at)
            VALUES ('200', 'example', 1, ?)
            """,
            (newer,),
        )

    db.initialize()

    assert db.get_latest_tweet_id("example") == "200"
    with db.connect() as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "twitter" not in tables
    assert "tweet_urls" not in tables
    assert "urls" not in tables
