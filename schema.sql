-- LifeOS Agents 数据表（SQLite）

CREATE TABLE IF NOT EXISTS goals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL,
    description   TEXT    NOT NULL DEFAULT '',
    domain        TEXT    NOT NULL CHECK (domain IN ('学习', '健康', '其他')),
    target_date   TEXT,                          -- YYYY-MM-DD
    weekly_hours  REAL    NOT NULL DEFAULT 5,
    status        TEXT    NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'archived')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS daily_plans (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT    NOT NULL UNIQUE,   -- YYYY-MM-DD
    orchestrator_json TEXT    NOT NULL DEFAULT '{}',
    created_at        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id      INTEGER NOT NULL REFERENCES daily_plans(id) ON DELETE CASCADE,
    goal_id      INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    title        TEXT    NOT NULL,
    detail       TEXT    NOT NULL DEFAULT '',
    est_minutes  INTEGER NOT NULL DEFAULT 30,
    priority     TEXT    NOT NULL DEFAULT 'mid'
                         CHECK (priority IN ('high', 'mid', 'low')),
    type         TEXT    NOT NULL DEFAULT 'study'
                         CHECK (type IN ('study', 'life')),
    status       TEXT    NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'done', 'partial', 'skipped')),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS checkins (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    date            TEXT    NOT NULL,            -- YYYY-MM-DD
    status          TEXT    NOT NULL
                            CHECK (status IN ('done', 'partial', 'skipped')),
    note            TEXT    NOT NULL DEFAULT '',
    actual_minutes  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name      TEXT    NOT NULL,
    date            TEXT    NOT NULL,            -- YYYY-MM-DD
    input_summary   TEXT    NOT NULL DEFAULT '',
    output_summary  TEXT    NOT NULL DEFAULT '',
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    token_estimate  INTEGER NOT NULL DEFAULT 0,
    success         INTEGER NOT NULL DEFAULT 1,  -- 1=成功 0=失败
    error_msg       TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS weekly_reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start   TEXT    NOT NULL UNIQUE,        -- 该周周一 YYYY-MM-DD
    review_json  TEXT    NOT NULL DEFAULT '{}',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
