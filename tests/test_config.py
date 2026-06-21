import pytest

from antenna.config import load_settings


def test_load_settings_reads_twitter_cookies_from_dotenv(tmp_path):
    config_path = tmp_path / "config.toml"
    env_path = tmp_path / ".env"
    config_path.write_text("", encoding="utf-8")
    env_path.write_text('ANTENNA_TWITTER_COOKIES="cookie-value"\n', encoding="utf-8")

    settings = load_settings(config_path, env_file=env_path)

    assert settings.twitter.cookies == "cookie-value"
    assert settings.twitter.has_cookies is True


def test_load_settings_rejects_custom_twitter_cookies_env_name(tmp_path):
    config_path = tmp_path / "config.toml"
    env_path = tmp_path / ".env"
    config_path.write_text('[twitter]\ncookies_env = "CUSTOM_TWITTER_COOKIES"\n', encoding="utf-8")
    env_path.write_text("CUSTOM_TWITTER_COOKIES=custom-cookie\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid settings"):
        load_settings(config_path, env_file=env_path)


def test_load_settings_rejects_invalid_scheduler_interval(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [scheduler]
        minimum_scan_interval_minutes = 120
        active_account_interval_minutes = 60
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid settings"):
        load_settings(config_path, env_file=tmp_path / ".env")
