PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS urls (
    url TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (url)
);

CREATE TABLE IF NOT EXISTS twitter (
    status_id TEXT NOT NULL,
    user_screen_name TEXT NOT NULL,
    in_timeline INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (status_id)
);

CREATE TABLE IF NOT EXISTS tweet_urls (
    status_id TEXT NOT NULL,
    url TEXT NOT NULL,
    relation TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (status_id, url, relation),
    FOREIGN KEY (status_id)
        REFERENCES twitter (status_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    FOREIGN KEY (url)
        REFERENCES urls (url)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS youtube (
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

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    message TEXT,
    stats_json TEXT
);

CREATE TABLE IF NOT EXISTS account_scan_state (
    user_screen_name TEXT NOT NULL,
    last_scan_at TIMESTAMP,
    last_tweet_at TIMESTAMP,
    last_status TEXT,
    last_error TEXT,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (user_screen_name)
);

CREATE TABLE IF NOT EXISTS runtime_state (
    key TEXT NOT NULL,
    value TEXT,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (key)
);

CREATE TABLE IF NOT EXISTS scan_resume_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_scan_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    force INTEGER NOT NULL,
    limit_accounts_json TEXT NOT NULL,
    failed_account TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    consumed_at TIMESTAMP,
    FOREIGN KEY (source_scan_id)
        REFERENCES scans (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CHECK (reason IN ('rate_limited')),
    CHECK (force IN (0, 1)),
    CHECK (status IN ('pending', 'consumed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_youtube_process_start_at
ON youtube (process, start_at DESC);

CREATE INDEX IF NOT EXISTS idx_youtube_process_sort_at
ON youtube (process, COALESCE(start_at, created_at) DESC);

CREATE INDEX IF NOT EXISTS idx_youtube_video_id
ON youtube (video_id);

CREATE INDEX IF NOT EXISTS idx_twitter_user_created_at
ON twitter (user_screen_name, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_scan_resume_pending
ON scan_resume_state (status)
WHERE status = 'pending';
