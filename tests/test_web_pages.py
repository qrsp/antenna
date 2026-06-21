from datetime import timedelta

from fastapi.testclient import TestClient

from antenna.app import create_app
from antenna.config import AppConfig, ListsConfig, Settings
from antenna.db import dt_to_db, utcnow
from antenna.models import YoutubeMetadata


def make_app(tmp_path):
    settings = Settings(
        lists=ListsConfig(),
        app=AppConfig(
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            thumbnail_dir=str(tmp_path / "thumbnails"),
        ),
    )
    return create_app(settings)


def test_dashboard_latest_scan_uses_taipei_time(tmp_path):
    app = make_app(tmp_path)
    client = TestClient(app)
    scan_id = app.state.db.create_scan()
    app.state.db.finish_scan(scan_id, "success", None, {})

    response = client.get("/")

    assert response.status_code == 200
    assert "台灣時間" in response.text


def test_checked_page_paginates_and_check_all_updates_review_queue(tmp_path):
    app = make_app(tmp_path)
    client = TestClient(app)

    for index in range(25):
        video_id = f"video{index}"
        app.state.db.save_youtube(
            YoutubeMetadata(
                url=f"https://www.youtube.com/watch?v={video_id}",
                video_id=video_id,
                title=f"Video {index}",
                channel_id=None,
                channel_name=None,
                start_at=utcnow() - timedelta(minutes=index),
                media_type=None,
                status="public",
                thumbnail_url=None,
                metadata_json="{}",
            ),
            None,
        )

    check_all = client.post("/videos/check-all", follow_redirects=False)
    assert check_all.status_code == 303
    assert app.state.db.count_videos("uncheck") == 0
    assert app.state.db.count_videos("checked") == 25

    page = client.get("/videos?process=checked&page=2")
    assert page.status_code == 200
    assert "Page 2 / 2" in page.text


def test_review_page_paginates_and_times_use_taipei(tmp_path):
    app = make_app(tmp_path)
    client = TestClient(app)

    for index in range(25):
        video_id = f"review{index}"
        app.state.db.save_youtube(
            YoutubeMetadata(
                url=f"https://www.youtube.com/watch?v={video_id}",
                video_id=video_id,
                title=f"Review {index}",
                channel_id=None,
                channel_name=None,
                start_at=utcnow() - timedelta(minutes=index),
                media_type=None,
                status="public",
                thumbnail_url=None,
                metadata_json="{}",
            ),
            None,
        )

    page = client.get("/videos?process=uncheck&page=2")

    assert page.status_code == 200
    assert "Page 2 / 2" in page.text
    assert "台灣時間" in page.text


def test_settings_rate_limit_pause_uses_taipei_time(tmp_path):
    app = make_app(tmp_path)
    client = TestClient(app)
    pause_until = utcnow() + timedelta(hours=1)
    app.state.db.set_runtime_value("twitter_pause_until", dt_to_db(pause_until))

    response = client.get("/settings")

    assert response.status_code == 200
    assert "台灣時間" in response.text
    assert "Pause until" in response.text
