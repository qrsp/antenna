PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS youtube (
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
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (url),
    CHECK (library_state IN ('archived', 'new'))
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
    last_status_id TEXT,
    PRIMARY KEY (user_screen_name)
);

CREATE TABLE IF NOT EXISTS runtime_state (
    key TEXT NOT NULL,
    value TEXT,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (key)
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT NOT NULL,
    applied_at TIMESTAMP NOT NULL,
    PRIMARY KEY (name)
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

CREATE INDEX IF NOT EXISTS idx_youtube_library_state_start_at
ON youtube (library_state, start_at DESC);

CREATE INDEX IF NOT EXISTS idx_youtube_library_state_sort_at
ON youtube (library_state, COALESCE(start_at, created_at) DESC);

CREATE INDEX IF NOT EXISTS idx_youtube_video_id
ON youtube (video_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_scan_resume_pending
ON scan_resume_state (status)
WHERE status = 'pending';
