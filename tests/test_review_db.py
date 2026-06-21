from antenna.config import SchedulerConfig
from antenna.db import Database
from antenna.models import YoutubeMetadata


class DummySettings:
    def __init__(self, path):
        class App:
            database_path = path

        self.app = App()
        self.scheduler = SchedulerConfig()


def test_youtube_process_is_limited_to_checked_and_uncheck(tmp_path):
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
            metadata_json="{}",
        ),
        None,
    )

    rows = db.list_videos("uncheck")
    assert len(rows) == 1
    assert db.update_video_process(["https://www.youtube.com/watch?v=abc123"], "checked") == 1

    try:
        db.update_video_process(["https://www.youtube.com/watch?v=abc123"], "waiting")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid process state should fail")
