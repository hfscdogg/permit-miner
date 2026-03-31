"""
hanover.py — Hanover County permit scraper (STUB).

Portal research needed. Hanover County permit portal options:
- Accela ACA (common for mid-size VA counties)
- Available via the Virginia statewide CSV (data.virginia.gov)

ZIPs: 23005, 23116

TODO: Research https://www.hanovercounty.gov/ for permit portal URL.
If no portal, Virginia state CSV is the fallback.
"""
import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)


def fetch_permits(since_days: int = 14) -> list[dict]:
    """
    Returns empty list until portal is identified.
    Virginia state CSV (virginia_state.py) covers these ZIPs as fallback.
    """
    log.info(
        "Hanover scraper: stub — ZIPs 23005/23116 covered by Virginia state CSV."
    )
    return []
