"""
james_city.py — James City County permit scraper.

Thin wrapper over the shared EnerGov Playwright driver (energov.py).
The county's "PermitLink" portal is Tyler CSS on tylerhost — same
platform as Albemarle. Covers the Williamsburg-area territory ZIPs
23168 (Toano) and 23188 (Williamsburg / Norge).
"""
import config
from pipeline.scrapers import energov


def fetch_permits(since_days: int = 14) -> list[dict]:
    return energov.fetch_permits_for("James City", config.JAMES_CITY_ZIPS, since_days)
