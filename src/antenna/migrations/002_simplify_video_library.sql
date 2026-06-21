PRAGMA foreign_keys = OFF;

ALTER TABLE account_scan_state ADD COLUMN last_status_id TEXT;

UPDATE account_scan_state
SET last_status_id = (
    SELECT twitter.status_id
    FROM twitter
    WHERE twitter.user_screen_name = account_scan_state.user_screen_name
    ORDER BY twitter.created_at DESC
    LIMIT 1
)
WHERE last_status_id IS NULL;

DROP INDEX IF EXISTS idx_youtube_library_state_start_at;
DROP INDEX IF EXISTS idx_youtube_library_state_sort_at;
DROP INDEX IF EXISTS idx_youtube_video_id;

CREATE TABLE youtube_migrated (
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

INSERT INTO youtube_migrated (
    url, video_id, title, channel_id, channel_name, start_at, media_type,
    status, library_state, thumbnail_path, created_at, updated_at
)
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
FROM youtube;

DROP TABLE youtube;
ALTER TABLE youtube_migrated RENAME TO youtube;

CREATE INDEX IF NOT EXISTS idx_youtube_library_state_sort_at
ON youtube (library_state, COALESCE(start_at, created_at) DESC);

DROP TABLE IF EXISTS tweet_urls;
DROP TABLE IF EXISTS urls;
DROP TABLE IF EXISTS twitter;

PRAGMA foreign_keys = ON;
