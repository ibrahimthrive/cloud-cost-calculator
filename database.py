"""SQLite persistence: saved configurations, historical estimates,
a snapshot of the base pricing catalog, and the exchange-rate cache."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "cost_calculator.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    config_json TEXT NOT NULL,
    monthly_usd REAL NOT NULL,
    yearly_usd REAL NOT NULL,
    currency TEXT NOT NULL,
    monthly_converted REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_catalog (
    provider TEXT NOT NULL,
    category TEXT NOT NULL,
    item_key TEXT NOT NULL,
    label TEXT NOT NULL,
    usd_value REAL NOT NULL,
    meta_json TEXT,
    PRIMARY KEY (provider, category, item_key)
);

CREATE TABLE IF NOT EXISTS exchange_rates (
    base TEXT NOT NULL,
    target TEXT NOT NULL,
    rate REAL NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (base, target)
);
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def seed_pricing_catalog():
    """Persist the in-code pricing catalog into SQLite (idempotent)."""
    import pricing as p

    rows = []
    for provider, instances in p.COMPUTE_CATALOGS.items():
        for inst in instances:
            rows.append((provider, "compute", inst.key, inst.label, inst.hourly_usd,
                         json.dumps({"vcpu": inst.vcpu, "ram_gb": inst.ram_gb})))
    for provider, tiers in p.STORAGE_CATALOGS.items():
        for tier in tiers:
            rows.append((provider, "storage", tier.key, tier.label, tier.usd_per_gb_month, None))
    for provider, cfg in p.EGRESS_PRICING.items():
        rows.append((provider, "egress", "per_gb", f"{provider} egress", cfg["usd_per_gb"],
                     json.dumps({"free_gb": cfg["free_gb"]})))

    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO pricing_catalog (provider, category, item_key, label, usd_value, meta_json)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(provider, category, item_key) DO UPDATE SET
                 label=excluded.label, usd_value=excluded.usd_value, meta_json=excluded.meta_json""",
            rows,
        )


def save_estimate(name: str, provider: str, config: dict, monthly_usd: float, yearly_usd: float,
                   currency: str, monthly_converted: float):
    from datetime import datetime, timezone

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO estimates (name, created_at, provider, config_json, monthly_usd,
                                       yearly_usd, currency, monthly_converted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, datetime.now(timezone.utc).isoformat(), provider, json.dumps(config),
             monthly_usd, yearly_usd, currency, monthly_converted),
        )


def list_estimates(limit: int = 100):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM estimates ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def delete_estimate(estimate_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM estimates WHERE id = ?", (estimate_id,))


def get_cached_rate(base: str, target: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT rate, fetched_at FROM exchange_rates WHERE base = ? AND target = ?",
            (base, target),
        ).fetchone()
    return dict(row) if row else None


def upsert_rate(base: str, target: str, rate: float, fetched_at: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO exchange_rates (base, target, rate, fetched_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(base, target) DO UPDATE SET rate=excluded.rate, fetched_at=excluded.fetched_at""",
            (base, target, rate, fetched_at),
        )
