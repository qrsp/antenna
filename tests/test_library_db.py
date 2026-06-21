from antenna.config import SchedulerConfig
from antenna.db import Database
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


def test_fresh_schema_has_only_current_tables_and_columns(tmp_path):
    db = Database(DummySettings(tmp_path / "test.db"))
    db.initialize()

    with db.connect() as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        youtube_columns = {row["name"] for row in conn.execute("PRAGMA table_info(youtube)").fetchall()}
        account_columns = {row["name"] for row in conn.execute("PRAGMA table_info(account_scan_state)").fetchall()}

    assert "twitter" not in tables
    assert "tweet_urls" not in tables
    assert "urls" not in tables
    assert "process" not in youtube_columns
    assert "metadata_json" not in youtube_columns
    assert "updated_at" not in account_columns
    assert "last_status_id" in account_columns
