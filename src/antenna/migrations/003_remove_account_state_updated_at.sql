PRAGMA foreign_keys = OFF;

CREATE TABLE account_scan_state_migrated (
    user_screen_name TEXT NOT NULL,
    last_scan_at TIMESTAMP,
    last_tweet_at TIMESTAMP,
    last_status TEXT,
    last_error TEXT,
    last_status_id TEXT,
    PRIMARY KEY (user_screen_name)
);

INSERT INTO account_scan_state_migrated (
    user_screen_name, last_scan_at, last_tweet_at, last_status, last_error, last_status_id
)
SELECT
    user_screen_name,
    last_scan_at,
    last_tweet_at,
    last_status,
    last_error,
    last_status_id
FROM account_scan_state;

DROP TABLE account_scan_state;
ALTER TABLE account_scan_state_migrated RENAME TO account_scan_state;

PRAGMA foreign_keys = ON;
