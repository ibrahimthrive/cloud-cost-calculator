"""Currency conversion with a live exchange-rate API and a SQLite-backed
cache so the app stays usable offline or when the API is rate-limited."""

from datetime import datetime, timedelta, timezone

import requests

import database

SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "NGN", "CAD", "AUD", "INR", "ZAR"]

# Static fallback rates (USD base) used when no internet/API access is available.
FALLBACK_RATES = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 156.0,
    "NGN": 1550.0,
    "CAD": 1.36,
    "AUD": 1.52,
    "INR": 83.5,
    "ZAR": 18.4,
}

API_URL = "https://api.exchangerate.host/latest"
CACHE_TTL = timedelta(hours=1)


def get_rate(target: str, base: str = "USD") -> tuple[float, str]:
    """Return (rate, source) where source is 'live', 'cache' or 'fallback'."""
    if target == base:
        return 1.0, "live"

    cached = database.get_cached_rate(base, target)
    if cached:
        fetched_at = datetime.fromisoformat(cached["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < CACHE_TTL:
            return cached["rate"], "cache"

    try:
        resp = requests.get(API_URL, params={"base": base, "symbols": target}, timeout=4)
        resp.raise_for_status()
        rate = float(resp.json()["rates"][target])
        database.upsert_rate(base, target, rate, datetime.now(timezone.utc).isoformat())
        return rate, "live"
    except Exception:
        if cached:
            return cached["rate"], "cache"
        return FALLBACK_RATES.get(target, 1.0), "fallback"


def convert(amount_usd: float, target: str) -> tuple[float, str]:
    rate, source = get_rate(target)
    return amount_usd * rate, source
