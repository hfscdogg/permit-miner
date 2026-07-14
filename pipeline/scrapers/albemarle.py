"""
albemarle.py — Albemarle County permit scraper.

Thin wrapper over the shared EnerGov Playwright driver (energov.py).
Covers the Charlottesville-metro territory ZIPs 22901, 22911, 22947 —
those are Albemarle County addresses with Charlottesville postal names;
the City of Charlottesville's own systems don't cover them.
"""
import config
from pipeline.scrapers import energov


def fetch_permits(since_days: int = 14) -> list[dict]:
    return energov.fetch_permits_for("Albemarle", config.ALBEMARLE_ZIPS, since_days)
