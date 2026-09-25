"""SQLite persistence — dịch 1-1 từ docs/schemas.md (xem docs/adr/0001-sqlite-for-prototype.md
cho lý do). Không dùng ORM. JSONB/mảng của Postgres → cột TEXT chứa JSON, parse ở tầng
Python (session_store.py, retrieval.py)."""

import math
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS project (
    project_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    developer       TEXT,
    district        TEXT NOT NULL,
    ward            TEXT,
    lat             REAL NOT NULL,
    lng             REAL NOT NULL,
    geo_source      TEXT NOT NULL DEFAULT 'geocoded'
                    CHECK (geo_source IN ('listing_field','geocoded','manual','ward_centroid')),
    handover_date   TEXT,                               -- ISO date; NULL = đã bàn giao
    amenities       TEXT NOT NULL DEFAULT '[]',          -- JSON array
    is_synthetic    INTEGER NOT NULL DEFAULT 0,
    CHECK (lat BETWEEN 20.5 AND 21.5 AND lng BETWEEN 105.3 AND 106.2)
);

CREATE TABLE IF NOT EXISTS unit (
    unit_id         TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES project(project_id),
    block           TEXT,
    floor           INTEGER NOT NULL CHECK (floor >= 1),
    total_floors    INTEGER NOT NULL CHECK (total_floors >= 1),
    area_sqm        REAL NOT NULL CHECK (area_sqm > 0),
    bedrooms        INTEGER NOT NULL CHECK (bedrooms BETWEEN 0 AND 6),
    bathrooms       INTEGER NOT NULL DEFAULT 1,
    balcony_dir     TEXT CHECK (balcony_dir IN ('N','NE','E','SE','S','SW','W','NW')),
    n_open_sides    INTEGER CHECK (n_open_sides BETWEEN 1 AND 3),
    is_corner       INTEGER,
    view_type       TEXT CHECK (view_type IN ('lake','park','river','city','internal','blocked')),
    furnishing      TEXT CHECK (furnishing IN ('bare','basic','full')),
    price_vnd       INTEGER NOT NULL CHECK (price_vnd > 0),
    status          TEXT NOT NULL DEFAULT 'available'
                    CHECK (status IN ('available','reserved','sold')),
    raw_description TEXT,
    canonical_text  TEXT,
    provenance      TEXT NOT NULL DEFAULT '{}',          -- JSON object
    source_url      TEXT,
    is_synthetic    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    CHECK (floor <= total_floors)
);
CREATE INDEX IF NOT EXISTS idx_unit_hard_filter ON unit (status, bedrooms, price_vnd);
CREATE INDEX IF NOT EXISTS idx_unit_project ON unit (project_id);

CREATE TABLE IF NOT EXISTS unit_business (
    unit_id             TEXT PRIMARY KEY REFERENCES unit(unit_id),
    days_on_market      INTEGER NOT NULL DEFAULT 0,
    business_priority   REAL NOT NULL DEFAULT 0 CHECK (business_priority BETWEEN 0 AND 1),
    discount_pct        REAL,
    commission_pct      REAL,
    policy_note         TEXT
);

CREATE TABLE IF NOT EXISTS poi (
    poi_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL CHECK (type IN
                ('school_primary','school_secondary','school_high','kindergarten',
                 'park','lake','hospital','supermarket','bus_stop','landmark')),
    name        TEXT NOT NULL,
    lat         REAL NOT NULL,
    lng         REAL NOT NULL,
    osm_id      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_poi_type ON poi (type);

CREATE TABLE IF NOT EXISTS project_poi_distance (
    project_id  TEXT NOT NULL REFERENCES project(project_id),
    poi_id      INTEGER NOT NULL REFERENCES poi(poi_id),
    distance_m  INTEGER NOT NULL,
    PRIMARY KEY (project_id, poi_id)
);
CREATE INDEX IF NOT EXISTS idx_ppd_poi ON project_poi_distance (poi_id, distance_m);

CREATE TABLE IF NOT EXISTS app_user (
    user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    role            TEXT NOT NULL CHECK (role IN ('customer','sale')),
    display_name    TEXT NOT NULL,
    phone_masked    TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session (
    session_id          TEXT PRIMARY KEY,
    customer_id         INTEGER NOT NULL REFERENCES app_user(user_id),
    assigned_sale_id    INTEGER REFERENCES app_user(user_id),
    state               TEXT NOT NULL DEFAULT 'draft' CHECK (state IN
                        ('draft','awaiting_review','under_review','rerank_requested','approved','sent')),
    criteria            TEXT,                            -- JSON: CriteriaSchema
    completeness        REAL NOT NULL DEFAULT 0,
    envelope            TEXT,                             -- JSON: Envelope
    income_bucket       TEXT,
    finance_purged_at   TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    sent_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_queue ON session (state, created_at);

CREATE TABLE IF NOT EXISTS message (
    message_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('customer','agent','system')),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_message_session ON message (session_id, created_at);

CREATE TABLE IF NOT EXISTS shortlist_item (
    session_id      TEXT NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    unit_id         TEXT NOT NULL REFERENCES unit(unit_id),
    rank            INTEGER NOT NULL,
    match_score     REAL NOT NULL,
    reasons         TEXT NOT NULL DEFAULT '[]',
    tradeoffs       TEXT NOT NULL DEFAULT '[]',
    what_if         TEXT,
    origin          TEXT NOT NULL DEFAULT 'system' CHECK (origin IN ('system','sale_added')),
    is_removed      INTEGER NOT NULL DEFAULT 0,
    over_envelope   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, unit_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL REFERENCES session(session_id),
    actor_id            INTEGER NOT NULL REFERENCES app_user(user_id),
    action              TEXT NOT NULL CHECK (action IN
                        ('view','remove_unit','add_unit','update_criteria',
                         'override_rank','edit_explanation','approve_and_send')),
    unit_id             TEXT REFERENCES unit(unit_id),
    from_rank           INTEGER,
    to_rank             INTEGER,
    old_value           TEXT,
    new_value           TEXT,
    match_score         REAL,
    business_priority   REAL,
    days_on_market      INTEGER,
    reason_code         TEXT,
    note                TEXT,
    created_at          TEXT NOT NULL,
    CHECK (action NOT IN ('override_rank','add_unit') OR (reason_code IS NOT NULL AND note IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log (session_id, created_at);

CREATE TABLE IF NOT EXISTS feedback (
    session_id  TEXT NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    unit_id     TEXT NOT NULL REFERENCES unit(unit_id),
    intent      TEXT NOT NULL CHECK (intent IN ('want_visit','rejected')),
    reason_tag  TEXT CHECK (reason_tag IN ('price','direction_floor','location','handover','other')),
    note        TEXT,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, unit_id),
    CHECK (intent = 'want_visit' OR reason_tag IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS llm_usage (
    usage_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT REFERENCES session(session_id) ON DELETE SET NULL,
    node        TEXT NOT NULL,
    model       TEXT NOT NULL,
    tokens_in   INTEGER NOT NULL,
    tokens_out  INTEGER NOT NULL,
    cost_usd    REAL NOT NULL,
    latency_ms  INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
