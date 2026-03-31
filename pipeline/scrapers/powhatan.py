"""
powhatan.py — Powhatan County permit scraper (STUB).

Portal research needed. Powhatan is a small county; permits may be:
- An EnerGov install (common for smaller VA counties)
- A custom county web portal
- Available via the Virginia statewide CSV (data.virginia.gov)

ZIPs: 23120, 23139, 23153

TODO: Research https://www.powhatanva.gov/ for permit portal URL.
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
        "Powhatan scraper: stub — ZIPs 23120/23139/23153 covered by Virginia state CSV."
    )
    return []
