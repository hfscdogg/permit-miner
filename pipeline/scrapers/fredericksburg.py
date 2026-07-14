"""
fredericksburg.py — City of Fredericksburg permit scraper.

Thin wrapper over the shared EnerGov Playwright driver (energov.py).
The city portal covers city limits only (ZIP 22401). The territory's
22406 is the Stafford County side of Fredericksburg postal addresses
and is not reachable through this portal.
"""
import config
from pipeline.scrapers import energov


def fetch_permits(since_days: int = 14) -> list[dict]:
    return energov.fetch_permits_for("Fredericksburg", config.FREDERICKSBURG_ZIPS, since_days)
