from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    trust_level INTEGER NOT NULL DEFAULT 3,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_signals (
    id INTEGER PRIMARY KEY,
    source_id INTEGER,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    published_at TEXT,
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT,
    FOREIGN KEY(source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS trend_events (
    id INTEGER PRIMARY KEY,
    canonical_topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'detected',
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    score_total INTEGER NOT NULL DEFAULT 0,
    score_json TEXT NOT NULL DEFAULT '{}',
    risk_flags TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS event_sources (
    event_id INTEGER NOT NULL,
    signal_id INTEGER NOT NULL,
    PRIMARY KEY(event_id, signal_id),
    FOREIGN KEY(event_id) REFERENCES trend_events(id),
    FOREIGN KEY(signal_id) REFERENCES raw_signals(id)
);

CREATE TABLE IF NOT EXISTS offers (
    offer_id TEXT PRIMARY KEY,
    network TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '[]',
    problem_tags TEXT NOT NULL DEFAULT '[]',
    event_tags TEXT NOT NULL DEFAULT '[]',
    affiliate_url TEXT NOT NULL DEFAULT '',
    landing_url TEXT NOT NULL DEFAULT '',
    reward_type TEXT NOT NULL DEFAULT '',
    reward_value REAL NOT NULL DEFAULT 0,
    allowed_media TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'research',
    last_verified_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS event_offer_matches (
    event_id INTEGER NOT NULL,
    offer_id TEXT NOT NULL,
    match_score INTEGER NOT NULL,
    reasons TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY(event_id, offer_id),
    FOREIGN KEY(event_id) REFERENCES trend_events(id),
    FOREIGN KEY(offer_id) REFERENCES offers(offer_id)
);

CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    generator TEXT NOT NULL DEFAULT 'local',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, content_type),
    FOREIGN KEY(event_id) REFERENCES trend_events(id)
);

CREATE TABLE IF NOT EXISTS social_posts (
    id INTEGER PRIMARY KEY,
    content_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    variant_key TEXT NOT NULL,
    post_text TEXT NOT NULL,
    target_url TEXT NOT NULL DEFAULT '',
    media_json TEXT NOT NULL DEFAULT '{}',
    fingerprint TEXT NOT NULL UNIQUE,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    approval_status TEXT NOT NULL DEFAULT 'pending',
    external_id TEXT NOT NULL DEFAULT '',
    permalink TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(content_id, platform, variant_key),
    FOREIGN KEY(content_id) REFERENCES content_items(id)
);

CREATE TABLE IF NOT EXISTS social_post_attempts (
    id INTEGER PRIMARY KEY,
    social_post_id INTEGER NOT NULL,
    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    response_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(social_post_id) REFERENCES social_posts(id)
);

CREATE TABLE IF NOT EXISTS social_metrics (
    id INTEGER PRIMARY KEY,
    social_post_id INTEGER NOT NULL,
    measured_at TEXT NOT NULL,
    impressions INTEGER NOT NULL DEFAULT 0,
    likes INTEGER NOT NULL DEFAULT 0,
    replies INTEGER NOT NULL DEFAULT 0,
    reposts INTEGER NOT NULL DEFAULT 0,
    saves INTEGER NOT NULL DEFAULT 0,
    link_clicks INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manual',
    UNIQUE(social_post_id, measured_at, source),
    FOREIGN KEY(social_post_id) REFERENCES social_posts(id)
);

CREATE TABLE IF NOT EXISTS compliance_reports (
    id INTEGER PRIMARY KEY,
    content_id INTEGER NOT NULL,
    factual_score INTEGER NOT NULL,
    trust_score INTEGER NOT NULL,
    dark_pattern_score INTEGER NOT NULL,
    decision TEXT NOT NULL,
    issues TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(content_id) REFERENCES content_items(id)
);

CREATE TABLE IF NOT EXISTS bot_runs (
    id INTEGER PRIMARY KEY,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    counters TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS metrics_hourly (
    id INTEGER PRIMARY KEY,
    content_id INTEGER,
    measured_at TEXT NOT NULL,
    sessions INTEGER NOT NULL DEFAULT 0,
    outbound_clicks INTEGER NOT NULL DEFAULT 0,
    conversions INTEGER NOT NULL DEFAULT 0,
    revenue REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manual',
    UNIQUE(content_id, measured_at, source),
    FOREIGN KEY(content_id) REFERENCES content_items(id)
);

CREATE TABLE IF NOT EXISTS conversions (
    id INTEGER PRIMARY KEY,
    transaction_id TEXT NOT NULL UNIQUE,
    network TEXT NOT NULL,
    offer_id TEXT,
    occurred_at TEXT NOT NULL,
    status TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    content_slug TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(offer_id) REFERENCES offers(offer_id)
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    row_count INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_slot_state (
    offer_id TEXT PRIMARY KEY,
    current_product_url TEXT NOT NULL DEFAULT '',
    activated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_decision TEXT NOT NULL DEFAULT 'initialized',
    last_score REAL NOT NULL DEFAULT 0,
    FOREIGN KEY(offer_id) REFERENCES offers(offer_id)
);

CREATE TABLE IF NOT EXISTS product_operation_runs (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    checked_count INTEGER NOT NULL DEFAULT 0,
    kept_count INTEGER NOT NULL DEFAULT 0,
    replaced_count INTEGER NOT NULL DEFAULT 0,
    issue_count INTEGER NOT NULL DEFAULT 0,
    report_path TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS product_decisions (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    offer_id TEXT NOT NULL,
    page_slug TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL,
    current_url TEXT NOT NULL DEFAULT '',
    candidate_url TEXT NOT NULL DEFAULT '',
    current_score REAL NOT NULL DEFAULT 0,
    candidate_score REAL NOT NULL DEFAULT 0,
    reasons TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(run_id) REFERENCES product_operation_runs(id)
);

CREATE TABLE IF NOT EXISTS affiliate_metrics_daily (
    id INTEGER PRIMARY KEY,
    measured_date TEXT NOT NULL,
    page_slug TEXT NOT NULL,
    offer_id TEXT NOT NULL,
    page_views INTEGER NOT NULL DEFAULT 0,
    affiliate_clicks INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'ga4_csv',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(measured_date, page_slug, offer_id, source)
);

CREATE TABLE IF NOT EXISTS trend_observations (
    id INTEGER PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    country_code TEXT NOT NULL,
    country_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    approx_traffic TEXT NOT NULL DEFAULT '',
    entity TEXT NOT NULL DEFAULT '',
    news_title TEXT NOT NULL DEFAULT '',
    news_url TEXT NOT NULL DEFAULT '',
    news_source TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_rank_snapshots (
    id INTEGER PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    network TEXT NOT NULL,
    genre_id TEXT NOT NULL DEFAULT '',
    genre_name TEXT NOT NULL DEFAULT '',
    period TEXT NOT NULL DEFAULT 'realtime',
    rank INTEGER NOT NULL DEFAULT 0,
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL,
    price INTEGER NOT NULL DEFAULT 0,
    affiliate_url TEXT NOT NULL DEFAULT '',
    item_url TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    review_count INTEGER NOT NULL DEFAULT 0,
    review_average REAL NOT NULL DEFAULT 0,
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trend_opportunities (
    id INTEGER PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    observation_id INTEGER,
    rank_snapshot_id INTEGER,
    rule_id TEXT NOT NULL,
    category TEXT NOT NULL,
    page_slug TEXT NOT NULL,
    country_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    entity TEXT NOT NULL DEFAULT '',
    audience TEXT NOT NULL DEFAULT '',
    why_trending TEXT NOT NULL DEFAULT '',
    evidence_label TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'screened',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(observation_id) REFERENCES trend_observations(id),
    FOREIGN KEY(rank_snapshot_id) REFERENCES market_rank_snapshots(id)
);

CREATE TABLE IF NOT EXISTS human_reviews (
    id INTEGER PRIMARY KEY,
    object_type TEXT NOT NULL,
    object_id INTEGER NOT NULL,
    decision TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_signals_processed ON raw_signals(processed_at);
CREATE INDEX IF NOT EXISTS idx_events_status_score ON trend_events(status, score_total DESC);
CREATE INDEX IF NOT EXISTS idx_content_status ON content_items(status);
CREATE INDEX IF NOT EXISTS idx_social_due ON social_posts(status, approval_status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_social_platform ON social_posts(platform, published_at);
CREATE INDEX IF NOT EXISTS idx_conversions_occurred ON conversions(occurred_at);
CREATE INDEX IF NOT EXISTS idx_product_decisions_run ON product_decisions(run_id, decision);
CREATE INDEX IF NOT EXISTS idx_affiliate_metrics_offer ON affiliate_metrics_daily(offer_id, measured_date);
CREATE INDEX IF NOT EXISTS idx_trend_observations_country ON trend_observations(country_code, collected_at);
CREATE INDEX IF NOT EXISTS idx_market_rank_item ON market_rank_snapshots(item_code, captured_at);
CREATE INDEX IF NOT EXISTS idx_trend_opportunities_score ON trend_opportunities(status, score DESC, created_at);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def transaction(path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
