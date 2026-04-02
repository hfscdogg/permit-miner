"""
db.py — SQLite schema initialization and helper functions.
All database access goes through this module.
"""
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import config


# ── Connection ─────────────────────────────────────────────────────────────────

@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA = """
-- ── permits ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS permits (
    -- Identity
    id                      TEXT PRIMARY KEY,           -- UUID, used as PURL pid
    customer_id             TEXT NOT NULL DEFAULT 'livewire',

    -- Shovels source data
    shovels_permit_id       TEXT,
    source                  TEXT DEFAULT 'Shovels',     -- 'Shovels' | 'Henrico Direct'

    -- Property
    property_address        TEXT NOT NULL,              -- UNIQUE dedup key
    property_city           TEXT,
    property_state          TEXT,
    property_zip            TEXT,
    assessed_value_cents    INTEGER,                    -- from property_assess_market_value
    shovels_address_id      TEXT,                       -- for /residents enrichment

    -- Permit
    permit_type             TEXT,
    permit_tags             TEXT,                       -- JSON array as text
    is_new_construction     INTEGER DEFAULT 0,          -- boolean 0/1
    file_date               TEXT,
    job_value_cents         INTEGER,

    -- Owner
    owner_name              TEXT,
    owner_type              TEXT,                       -- 'individual' | 'company' etc.

    -- Contractor
    contractor_id           TEXT,
    contractor_name         TEXT,
    contractor_phone        TEXT,
    contractor_email        TEXT,

    -- Contact enrichment (from /residents)
    owner_phone             TEXT,
    owner_email             TEXT,
    owner_linkedin          TEXT,
    owner_income_range      TEXT,
    owner_net_worth         TEXT,

    -- Status lifecycle
    status                  TEXT NOT NULL DEFAULT 'Queued',
    -- Valid: Queued, Excluded, Sent, Engaged, Consultation Scheduled,
    --        Drip Queued, Drip Sent, Lob Error, Converted

    -- Exclusion
    exclude_reason          TEXT,
    excluded_by             TEXT,
    excluded_at             TEXT,

    -- Lob tracking
    lob_postcard_id         TEXT,
    lob_tracking_url        TEXT,
    postcard_sent_date      TEXT,
    lob_error               TEXT,

    -- PURL / QR tracking
    purl_url                TEXT,
    qr_scanned              INTEGER DEFAULT 0,
    first_scan_date         TEXT,
    scan_count              INTEGER DEFAULT 0,

    -- Multi-touch drip
    touch_number            INTEGER DEFAULT 1,
    parent_permit_id        TEXT,                       -- FK to permits.id for drip records

    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,

    UNIQUE(customer_id, property_address)
);

-- ── exclusion_rules ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS exclusion_rules (
    id              TEXT PRIMARY KEY,
    customer_id     TEXT NOT NULL DEFAULT 'livewire',
    rule_type       TEXT NOT NULL,      -- 'Contractor' | 'Keyword' | 'Address' | 'Owner_Name'
    rule_value      TEXT NOT NULL,
    match_type      TEXT DEFAULT 'Exact',  -- 'Exact' | 'Contains'
    exclusion_count INTEGER DEFAULT 0,
    auto_generated  INTEGER DEFAULT 0,  -- 1 = created by auto-block logic
    active          INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL,

    UNIQUE(customer_id, rule_type, rule_value)
);

-- ── app_config ────────────────────────────────────────────────────────────────
-- Runtime state that persists between runs (last run date, etc.)
CREATE TABLE IF NOT EXISTS app_config (
    customer_id             TEXT PRIMARY KEY DEFAULT 'livewire',
    last_monday_run         TEXT,
    last_tuesday_run        TEXT,
    last_henrico_run        TEXT,
    last_monthly_report     TEXT
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_permits_status     ON permits(customer_id, status);
CREATE INDEX IF NOT EXISTS idx_permits_zip        ON permits(customer_id, property_zip);
CREATE INDEX IF NOT EXISTS idx_permits_file_date  ON permits(file_date);
CREATE INDEX IF NOT EXISTS idx_exclusion_rules_lookup
    ON exclusion_rules(customer_id, rule_type, active);
"""


def init_db():
    """Create tables and seed default config row if absent."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO app_config(customer_id) VALUES ('livewire')"
        )


# ── Permit helpers ─────────────────────────────────────────────────────────────

def new_id() -> str:
    return str(uuid.uuid4()).replace("-", "")[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_permit(data: dict) -> tuple[bool, str]:
    """
    Insert a permit record. If property_address already exists for this
    customer, skip (dedup). Returns (inserted: bool, id: str).
    """
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM permits WHERE customer_id=? AND property_address=?",
            (data.get("customer_id", "livewire"), data["property_address"]),
        ).fetchone()
        if existing:
            return False, existing["id"]

        permit_id = new_id()
        ts = now_iso()
        conn.execute(
            """INSERT INTO permits
               (id, customer_id, shovels_permit_id, source,
                property_address, property_city, property_state, property_zip,
                assessed_value_cents, shovels_address_id,
                permit_type, permit_tags, is_new_construction, file_date, job_value_cents,
                owner_name, owner_type,
                contractor_id, contractor_name, contractor_phone, contractor_email,
                owner_phone, owner_email, owner_linkedin, owner_income_range, owner_net_worth,
                status, purl_url, touch_number,
                created_at, updated_at)
               VALUES
               (:id, :customer_id, :shovels_permit_id, :source,
                :property_address, :property_city, :property_state, :property_zip,
                :assessed_value_cents, :shovels_address_id,
                :permit_type, :permit_tags, :is_new_construction, :file_date, :job_value_cents,
                :owner_name, :owner_type,
                :contractor_id, :contractor_name, :contractor_phone, :contractor_email,
                :owner_phone, :owner_email, :owner_linkedin, :owner_income_range, :owner_net_worth,
                :status, :purl_url, :touch_number,
                :created_at, :updated_at)""",
            {
                "id": permit_id,
                "customer_id": data.get("customer_id", "livewire"),
                "shovels_permit_id": data.get("shovels_permit_id"),
                "source": data.get("source", "Shovels"),
                "property_address": data["property_address"],
                "property_city": data.get("property_city"),
                "property_state": data.get("property_state"),
                "property_zip": data.get("property_zip"),
                "assessed_value_cents": data.get("assessed_value_cents"),
                "shovels_address_id": data.get("shovels_address_id"),
                "permit_type": data.get("permit_type"),
                "permit_tags": data.get("permit_tags"),
                "is_new_construction": 1 if data.get("is_new_construction") else 0,
                "file_date": data.get("file_date"),
                "job_value_cents": data.get("job_value_cents"),
                "owner_name": data.get("owner_name"),
                "owner_type": data.get("owner_type"),
                "contractor_id": data.get("contractor_id"),
                "contractor_name": data.get("contractor_name"),
                "contractor_phone": data.get("contractor_phone"),
                "contractor_email": data.get("contractor_email"),
                "owner_phone": data.get("owner_phone"),
                "owner_email": data.get("owner_email"),
                "owner_linkedin": data.get("owner_linkedin"),
                "owner_income_range": data.get("owner_income_range"),
                "owner_net_worth": data.get("owner_net_worth"),
                "status": data.get("status", "Queued"),
                "purl_url": data.get("purl_url"),
                "touch_number": data.get("touch_number", 1),
                "created_at": ts,
                "updated_at": ts,
            },
        )
        return True, permit_id


def set_permit_status(permit_id: str, status: str, extra: Optional[dict] = None):
    """Update permit status and optional extra fields."""
    with get_conn() as conn:
        fields = {"status": status, "updated_at": now_iso()}
        if extra:
            fields.update(extra)
        set_clause = ", ".join(f"{k}=:{k}" for k in fields)
        fields["permit_id"] = permit_id
        conn.execute(f"UPDATE permits SET {set_clause} WHERE id=:permit_id", fields)


def get_permit(permit_id: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM permits WHERE id=?", (permit_id,)).fetchone()


def get_queued_permits(customer_id: str = "livewire") -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM permits WHERE customer_id=? AND status IN ('Queued','Drip Queued') ORDER BY created_at",
            (customer_id,),
        ).fetchall()


# ── Exclusion rule helpers ──────────────────────────────────────────────────────

def is_excluded_by_rules(permit: dict, customer_id: str = "livewire") -> bool:
    """Check if a permit matches any active exclusion rule."""
    with get_conn() as conn:
        rules = conn.execute(
            "SELECT rule_type, rule_value, match_type FROM exclusion_rules "
            "WHERE customer_id=? AND active=1",
            (customer_id,),
        ).fetchall()

    for rule in rules:
        rt, rv, mt = rule["rule_type"], rule["rule_value"].lower(), rule["match_type"]
        check = {
            "Contractor":  (permit.get("contractor_name") or "").lower(),
            "Keyword":     (permit.get("permit_type") or "").lower() + " " + (permit.get("permit_tags") or "").lower(),
            "Address":     (permit.get("property_address") or "").lower(),
            "Owner_Name":  (permit.get("owner_name") or "").lower(),
        }.get(rt, "")
        if mt == "Exact" and rv == check:
            return True
        if mt == "Contains" and rv in check:
            return True
    return False


def upsert_exclusion_rule(customer_id: str, rule_type: str, rule_value: str,
                           match_type: str = "Exact", auto_generated: bool = False):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO exclusion_rules
               (id, customer_id, rule_type, rule_value, match_type,
                exclusion_count, auto_generated, active, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, 1, ?)
               ON CONFLICT(customer_id, rule_type, rule_value) DO UPDATE SET
               exclusion_count = exclusion_count + 1,
               active = 1,
               auto_generated = CASE WHEN excluded.auto_generated=1 THEN 1 ELSE excluded.auto_generated END
            """.replace("excluded.", "exclusion_rules."),
            (new_id(), customer_id, rule_type, rule_value, match_type,
             1 if auto_generated else 0, now_iso()),
        )


def get_contractor_exclusion_count(customer_id: str, contractor_name: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT exclusion_count FROM exclusion_rules "
            "WHERE customer_id=? AND rule_type='Contractor' AND rule_value=?",
            (customer_id, contractor_name),
        ).fetchone()
        return row["exclusion_count"] if row else 0


# ── App config helpers ─────────────────────────────────────────────────────────

def get_app_config(customer_id: str = "livewire") -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM app_config WHERE customer_id=?", (customer_id,)
        ).fetchone()


def set_app_config_field(field: str, value: str, customer_id: str = "livewire"):
    with get_conn() as conn:
        conn.execute(
            f"UPDATE app_config SET {field}=? WHERE customer_id=?",
            (value, customer_id),
        )


# ── JSON data file helpers ─────────────────────────────────────────────────────
# These files live in data/ and are committed to the repo.
# Zoho relays scan/exclusion events; local files are a fallback cache.

import json as _json
import os as _os

DATA_DIR = _os.path.join(_os.path.dirname(__file__), "data")


def _data_path(filename: str) -> str:
    return _os.path.join(DATA_DIR, filename)


def read_scans() -> list[dict]:
    """Return list of {pid, timestamp} scan events."""
    path = _data_path("scans.json")
    try:
        with open(path) as f:
            data = _json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, _json.JSONDecodeError):
        return []


def read_exclusions() -> list[dict]:
    """Return list of {pid, reason, timestamp} exclusion events."""
    path = _data_path("exclusions.json")
    try:
        with open(path) as f:
            data = _json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, _json.JSONDecodeError):
        return []


def write_registry(registry: dict):
    """Write permit registry {pid: {owner_name, phone, address, permit_type}} to data/."""
    path = _data_path("permit_registry.json")
    _os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w") as f:
        _json.dump(registry, f, indent=2)
